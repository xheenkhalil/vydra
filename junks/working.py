from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx # Not directly used in the current version, but good to keep if you plan async http calls
from pydantic import BaseModel
from typing import List, Optional
from yt_dlp import YoutubeDL
import os
import re
import traceback # Ensure traceback is imported for logging errors

app = FastAPI()

# --- CORS Configuration ---
# Use environment variable for frontend URL for flexibility
# Ensure no trailing slash on fixed URLs if FRONTEND_URL also doesn't have one
origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://vydra.onrender.com",           # Your Render backend's own URL
    os.getenv("FRONTEND_URL", "https://vydra-downloader.vercel.app"), # Your Vercel frontend production URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic models ---
class AnalyzeRequest(BaseModel):
    url: str

class FormatInfo(BaseModel):
    format_id: str
    ext: str
    quality: str
    size_mb: Optional[float] = None
    is_premium: bool = False

class AnalyzeResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    original_url: str
    formats: List[FormatInfo]

# --- Utility to sanitize filenames ---
def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[\\/:*?"<>|]', '', filename)
    filename = filename.replace(' ', '_')
    return filename[:100]

# --- Global function to get YDL options with proxy ---
def get_ydl_opts(is_download: bool = False, format_id: str = None, ext: str = None, output_template: str = None):
    # Retrieve proxy URL from environment variable
    proxy_url = os.getenv('YT_DLP_PROXY')

    # Base options for yt-dlp
    ydl_opts = {
        'cachedir': False,      # Do not use cache
        'noplaylist': True,     # Do not process playlists (only single video)
        'quiet': True,          # Suppress console output
        'force_ipv4': True,     # Force IPv4
        'simulate': not is_download, # Simulate (don't download) for analyze, actual download for download
        'dump_single_json': not is_download, # Dump info as JSON for analyze
        'extract_flat': not is_download, # Extract info without deep processing for analyze
        'geo_bypass': True,     # Attempt to bypass geo-restrictions using proxy
        'retries': 5,           # Number of retries for network errors
        'continuedl': True,     # Continue downloading if interrupted
        'fragment_retries': 5,  # Retries for fragments (for segmented downloads)
        'socket_timeout': 10,   # Timeout for socket operations (can be adjusted)
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36', # Spoof a common user-agent
    }

    # Add proxy if available
    if proxy_url:
        print(f"Using proxy: {proxy_url[:30]}...") # Log part of the proxy URL for debugging (hide credentials)
        ydl_opts['proxy'] = proxy_url
    else:
        print("No proxy configured for YT_DLP_PROXY.")

    # Specific options for analyze endpoint
    if not is_download:
        # Default format to get enough info for analysis
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    # Specific options for download endpoint
    if is_download:
        ydl_opts['format'] = format_id
        ydl_opts['outtmpl'] = output_template
        ydl_opts['merge_output_format'] = ext

    return ydl_opts


# --- API Routes ---

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_link(request: AnalyzeRequest):
    try:
        # Get YDL options including the proxy settings
        ydl_opts = get_ydl_opts(is_download=False)
        
        with YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to analyze URL: {request.url}")
            info_dict = ydl.extract_info(request.url, download=False)
            print(f"Analysis successful for: {info_dict.get('title', 'N/A')}")

        title = info_dict.get('title', 'Unknown Title')
        thumbnail = info_dict.get('thumbnail')
        original_url = info_dict.get('webpage_url', request.url)

        formats_list = []
        # Logic to extract and sort formats
        if 'formats' in info_dict:
            # Sort by quality (height for video, abr for audio), then filesize
            sorted_formats = sorted(
                info_dict['formats'],
                key=lambda f: (
                    f.get('height') if f.get('height') is not None else 0,  # Ensure height is always int
                    f.get('tbr') if f.get('tbr') is not None else 0,        # Ensure tbr is always int
                    # Robustly ensure filesize is always an int for comparison
                    (f.get('filesize') if f.get('filesize') is not None else 0) or 
                    (f.get('filesize_approx') if f.get('filesize_approx') is not None else 0) or 0
                ),
                reverse=True # Highest quality first
            )

            seen_qualities = set()
            for f in sorted_formats:
                format_id = f.get('format_id')
                ext = f.get('ext')
                # Filter out unwanted extensions or formats without an extension/id
                if not ext or not format_id or (ext not in ['mp4', 'm4a', 'webm', 'ogg', 'mov', 'flv', 'avi']):
                    continue

                quality_label = None
                is_premium = False

                # Handle video and audio formats
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none': # Video with audio
                    if f.get('height'):
                        quality_label = f"{f['height']}p"
                        if f['height'] >= 1080: # Mark 1080p and above as premium
                            is_premium = True
                    elif f.get('tbr'):
                        quality_label = f"{int(f['tbr'])}kbps"
                elif f.get('vcodec') == 'none' and f.get('acodec') != 'none': # Audio only
                    if f.get('abr'):
                        quality_label = f"Audio {int(f['abr'])}kbps"
                    else:
                        quality_label = "Audio"
                    is_premium = True # Mark audio-only as premium
                elif f.get('acodec') == 'none' and f.get('vcodec') != 'none': # Video only (no audio)
                     if f.get('height'):
                        quality_label = f"Video {f['height']}p (no audio)"
                        is_premium = True # Mark video-only as premium

                # Prevent duplicate quality labels (e.g., multiple 720p options)
                if not quality_label or quality_label in seen_qualities:
                    continue

                filesize = f.get('filesize') or f.get('filesize_approx')
                size_mb = round(filesize / (1024 * 1024), 2) if filesize else None

                formats_list.append(FormatInfo(
                    format_id=format_id,
                    ext=ext,
                    quality=quality_label,
                    size_mb=size_mb,
                    is_premium=is_premium
                ))
                seen_qualities.add(quality_label)
        
        # Fallback for simple direct links where formats list might be empty but a direct URL exists
        elif 'url' in info_dict and 'ext' in info_dict and not formats_list:
            default_ext = info_dict['ext']
            default_quality = "Original"
            default_filesize = info_dict.get('filesize') or info_dict.get('filesize_approx')
            default_size_mb = round(default_filesize / (1024 * 1024), 2) if default_filesize else None

            formats_list.append(FormatInfo(
                format_id="best", # Use "best" for simple direct downloads
                ext=default_ext,
                quality=default_quality,
                size_mb=default_size_mb,
                is_premium=False
            ))

        return AnalyzeResponse(
            title=title,
            thumbnail=thumbnail,
            original_url=original_url,
            formats=formats_list
        )
    except Exception as e:
        print(f"Error analyzing link: {e}")
        # Log the full exception traceback for better debugging on Render
        traceback.print_exc() 
        # Provide a more user-friendly error detail if it's a known YT-DLP error
        if "Sign in to confirm you’re not a bot" in str(e) or "geo-restricted" in str(e):
             raise HTTPException(status_code=400, detail="Video requires login, is age-restricted, or geo-restricted. Try a different video or ensure proxy is working.")
        elif "not a valid URL" in str(e):
             raise HTTPException(status_code=400, detail=f"Invalid URL provided. Please check the link: {request.url}")
        else:
            raise HTTPException(status_code=400, detail=f"Could not analyze link: {e}. Please try again later.")

@app.get("/api/download")
async def download_media(
    url: str,
    format_id: str,
    title: str,
    ext: str,
    quality: str,
    response: Response
):
    try:
        sanitized_title = sanitize_filename(title)
        # Ensure unique output template for concurrent downloads
        # yt-dlp might replace %(ext)s with a merged extension (e.g., .mp4 even if original was .webm)
        # It's safest to make the base filename unique and let yt-dlp determine the final extension.
        base_filename_unique = f"{sanitized_title}_{os.urandom(4).hex()}"
        output_template = os.path.join('/tmp', f'{base_filename_unique}.%(ext)s')

        # Get YDL options including the proxy settings
        ydl_opts = get_ydl_opts(is_download=True, format_id=format_id, ext=ext, output_template=output_template)

        os.makedirs('/tmp', exist_ok=True) # Ensure /tmp exists

        with YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to download {title} ({format_id}) from {url}")
            info_dict = ydl.extract_info(url, download=True)
            
            # The most reliable way to get the final downloaded file path after yt-dlp has finished,
            # especially with merges and post-processing, is typically from the returned info_dict.
            downloaded_file = info_dict.get('filepath') or info_dict.get('_filename')
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                # Fallback if the direct path isn't immediately available or correct.
                # Use glob to find the file based on our unique base_filename.
                print(f"Warning: Direct filepath not found or incorrect for {title}. Attempting to locate via glob.")
                import glob
                # Search for files starting with our unique base filename and any extension
                potential_files = glob.glob(os.path.join('/tmp', f'{base_filename_unique}.*'))
                if potential_files:
                    downloaded_file = potential_files[0] # Take the first one found
                    print(f"Located downloaded file: {downloaded_file}")
                else:
                    raise FileNotFoundError(f"Downloaded file not found for title '{sanitized_title}' in /tmp after download.")


        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Downloaded file not found at {downloaded_file}")

        # Stream the file to prevent large files from eating RAM
        def file_iterator(file_path):
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192): # Read in 8KB chunks
                    yield chunk
            os.remove(file_path) # Delete after sending

        # Determine the final file's extension for Content-Type and Content-Disposition
        final_ext = os.path.splitext(downloaded_file)[1].lstrip('.')
        # Use the provided 'ext' from the frontend if it's reliable, otherwise use actual final_ext
        response_ext = ext if ext else final_ext 

        # Set headers for the response
        response.headers["Content-Disposition"] = f"attachment; filename=\"{sanitized_title}.{response_ext}\""
        response.headers["Content-Type"] = f"application/{response_ext}" # Use generic application type
        response.headers["X-File-Name"] = f"{sanitized_title}.{response_ext}"

        return Response(content=file_iterator(downloaded_file), media_type=f"application/{response_ext}")

    except FileNotFoundError as fnf_e:
        print(f"File not found error: {fnf_e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: Downloaded file not found. It might have been deleted or never created. {fnf_e}")
    except Exception as e:
        print(f"Error during download: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Download failed: {e}. Please try again later.")