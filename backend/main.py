from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from yt_dlp import YoutubeDL
import os
import re
import traceback
import glob

# --- FastAPI App Initialization ---
app = FastAPI()

# --- CORS Configuration ---
# Get frontend URL from environment variable for CORS.
# Defaults to localhost and a common Vercel URL if not set.
frontend_url_env = os.getenv("FRONTEND_URL")
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://vydra-downloader.vercel.app"
    "https://vydra.onrender.com",  # Your deployed frontend, if it's on Render
]

if frontend_url_env:
    # Ensure no trailing slash for consistent matching
    if frontend_url_env.endswith('/'):
        frontend_url_env = frontend_url_env.rstrip('/')
    origins.append(frontend_url_env)
    print(f"Allowed frontend URL from env: {frontend_url_env}")
else:
    default_vercel_url = "https://vydra-downloader.vercel.app" # Default Vercel frontend URL
    origins.append(default_vercel_url)
    print(f"FRONTEND_URL env var not set, using default: {default_vercel_url}")

print(f"Configuring CORS with allowed origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models for API Request/Response Validation ---

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
    description: Optional[str] = None

# --- Utility Functions ---

def sanitize_filename(filename: str) -> str:
    """Sanitizes a string to be safe for use as a filename."""
    # Remove invalid characters for filenames
    filename = re.sub(r'[\\/:*?"<>|]', '', filename)
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    # Truncate to a reasonable length to avoid OS limits
    return filename[:100]

def get_ydl_opts(is_download: bool = False, format_id: Optional[str] = None, 
                 ext: Optional[str] = None, output_template: Optional[str] = None) -> dict:
    """
    Constructs and returns options dictionary for YoutubeDL.
    Includes proxy support from environment variables.
    """
    ydl_opts = {
        'cachedir': False,          # Do not use cache directory
        'noplaylist': True,         # Do not download playlists
        'quiet': True,              # Suppress standard output
        'force_ipv4': True,         # Force IPv4
        'simulate': not is_download, # Simulate (don't download) if not in download mode
        'dump_single_json': not is_download, # Dump info as JSON if simulating
        'extract_flat': not is_download,     # Extract flat info if simulating
        'geo_bypass': True,         # Bypass geographic restrictions
        'retries': 5,               # Number of retries for downloads
        'continuedl': True,         # Continue interrupted downloads
        'fragment_retries': 5,      # Number of retries for fragments
        'socket_timeout': 10,       # Socket timeout in seconds
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36',
    }

    # --- Proxy Configuration ---
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        ydl_opts['proxy'] = proxy_url
        print(f"Using proxy: {proxy_url}")
    else:
        print("No proxy configured.")

    # Specific options for analysis vs. download
    if not is_download:
        # Prioritize MP4 and M4A, then best available MP4/general best
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else: # is_download == True
        # Use the specific format_id, output template, and merge format for download
        ydl_opts['format'] = format_id
        ydl_opts['outtmpl'] = output_template
        ydl_opts['merge_output_format'] = ext # For merging video+audio if needed

    return ydl_opts

# --- API Endpoints ---

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_link(request: AnalyzeRequest):
    """
    Analyzes a given URL to extract video metadata and available formats.
    """
    try:
        ydl_opts = get_ydl_opts(is_download=False)
        
        with YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to analyze URL: {request.url}")
            info_dict = ydl.extract_info(request.url, download=False)
            print(f"Analysis successful for: {info_dict.get('title', 'N/A')}")

        title = info_dict.get('title', 'Unknown Title')
        thumbnail = info_dict.get('thumbnail')
        original_url = info_dict.get('webpage_url', request.url)
        description = info_dict.get('description', 'No description available.')

        formats_list = []
        if 'formats' in info_dict:
            # Sort formats by height then bitrate, descending
            sorted_formats = sorted(
                info_dict['formats'],
                key=lambda f: (
                    f.get('height') if f.get('height') is not None else 0,
                    f.get('tbr') if f.get('tbr') is not None else 0,
                    (f.get('filesize') if f.get('filesize') is not None else 0) or 
                    (f.get('filesize_approx') if f.get('filesize_approx') is not None else 0) or 0
                ),
                reverse=True
            )

            seen_qualities = set()
            for f in sorted_formats:
                format_id = f.get('format_id')
                ext = f.get('ext')
                # Filter out invalid or unsupported formats
                if not ext or not format_id or (ext not in ['mp4', 'm4a', 'webm', 'ogg', 'mov', 'flv', 'avi']):
                    continue

                quality_label = None
                is_premium = False

                # Determine quality label and premium status
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none': # Video with audio
                    if f.get('height'):
                        quality_label = f"{f['height']}p"
                        if f['height'] >= 1080: # Mark 1080p and higher as premium
                            is_premium = True
                    elif f.get('tbr'):
                        quality_label = f"{int(f['tbr'])}kbps"
                elif f.get('vcodec') == 'none' and f.get('acodec') != 'none': # Audio only
                    if f.get('abr'):
                        quality_label = f"Audio {int(f['abr'])}kbps"
                    else:
                        quality_label = "Audio"
                    is_premium = True # Audio-only is premium
                elif f.get('acodec') == 'none' and f.get('vcodec') != 'none': # Video only (no audio)
                     if f.get('height'):
                        quality_label = f"Video {f['height']}p (no audio)"
                        is_premium = True # Video-only is premium

                # Skip if quality label couldn't be determined or already added
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
        
        # Fallback for single-format entries (e.g., direct file links)
        elif 'url' in info_dict and 'ext' in info_dict and not formats_list:
            default_ext = info_dict['ext']
            default_quality = "Original"
            default_filesize = info_dict.get('filesize') or info_dict.get('filesize_approx')
            default_size_mb = round(default_filesize / (1024 * 1024), 2) if default_filesize else None

            formats_list.append(FormatInfo(
                format_id="best", # Use "best" as a generic format_id for direct links
                ext=default_ext,
                quality=default_quality,
                size_mb=default_size_mb,
                is_premium=False
            ))

        return AnalyzeResponse(
            title=title,
            thumbnail=thumbnail,
            original_url=original_url,
            formats=formats_list,
            description=description
        )
    except Exception as e:
        print(f"Error analyzing link: {e}")
        traceback.print_exc() 
        # Provide user-friendly error messages based on common yt-dlp issues
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
    quality: str, # Not strictly used for download, but good for context/logging
):
    """
    Downloads a video from the given URL in the specified format and streams it back.
    """
    try:
        sanitized_title = sanitize_filename(title)
        # Create a unique filename for the temporary download
        base_filename_unique = f"{sanitized_title}_{os.urandom(4).hex()}"
        # Output template for yt-dlp to save files in /tmp
        output_template = os.path.join('/tmp', f'{base_filename_unique}.%(ext)s')

        ydl_opts = get_ydl_opts(is_download=True, format_id=format_id, ext=ext, output_template=output_template)

        # Ensure the /tmp directory exists
        os.makedirs('/tmp', exist_ok=True)

        with YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to download {title} ({format_id}) from {url}")
            # Download the video
            info_dict = ydl.extract_info(url, download=True)
            
            # yt-dlp's downloaded file path, or find it via glob if not directly provided
            downloaded_file = info_dict.get('filepath') or info_dict.get('_filename')
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                print(f"Warning: Direct filepath not found or incorrect for {title}. Attempting to locate via glob.")
                # Use glob to find the file based on the unique prefix
                potential_files = glob.glob(os.path.join('/tmp', f'{base_filename_unique}.*'))
                if potential_files:
                    downloaded_file = potential_files[0]
                    print(f"Located downloaded file: {downloaded_file}")
                else:
                    raise FileNotFoundError(f"Downloaded file not found for title '{sanitized_title}' in /tmp after download.")

        # Final check if the file exists after all attempts
        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Downloaded file not found at {downloaded_file}")

        def file_iterator(file_path: str):
            """
            Generator that reads a file in chunks and yields them.
            Also cleans up the file after streaming is complete.
            """
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192): # Read in 8KB chunks
                    yield chunk
            # --- File cleanup: IMPORTANT to do AFTER streaming ---
            try:
                os.remove(file_path)
                print(f"Successfully removed downloaded file: {file_path}")
            except OSError as cleanup_error:
                print(f"Error removing downloaded file {file_path}: {cleanup_error}")

        # Determine the final file extension for the response header
        final_ext = os.path.splitext(downloaded_file)[1].lstrip('.')
        response_ext = ext if ext else final_ext 

        # Set HTTP headers for file download
        headers = {
            "Content-Disposition": f"attachment; filename=\"{sanitized_title}.{response_ext}\"",
            "X-File-Name": f"{sanitized_title}.{response_ext}" # Custom header for debugging/info
        }

        # Return the file as a streaming response
        return StreamingResponse(file_iterator(downloaded_file), media_type=f"application/{response_ext}", headers=headers)

    except FileNotFoundError as fnf_e:
        print(f"File not found error: {fnf_e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: Downloaded file not found. It might have been deleted or never created. {fnf_e}")
    except Exception as e:
        print(f"Error during download: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Download failed: {e}. Please try again later.")