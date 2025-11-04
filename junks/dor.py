from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel
from typing import List, Optional
from yt_dlp import YoutubeDL
import os
import re

app = FastAPI()

# --- CORRECTED CORS Configuration ---
# This is crucial for allowing your Vercel frontend to communicate with your Render backend.
# The 'origins' list now includes your *exact* Vercel frontend URL.
origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://vydra.onrender.com",           # Your backend's own URL (important for itself)
    "https://vydra-downloader.vercel.app",  # Your *exact* Vercel frontend production URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Important if you plan to use cookies/authorization headers
    allow_methods=["*"],     # Allows all standard HTTP methods (GET, POST, PUT, DELETE, OPTIONS)
    allow_headers=["*"],     # Allows all headers to be sent by the client
)

# Pydantic models (AnalyzeRequest, AnalyzeResponse, FormatInfo, etc.)
class AnalyzeRequest(BaseModel):
    url: str

class FormatInfo(BaseModel):
    format_id: str
    ext: str
    quality: str
    size_mb: Optional[float] = None # Size in MB, optional
    is_premium: bool = False # Added for 'premium' formats

class AnalyzeResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    original_url: str
    formats: List[FormatInfo]

# Utility to sanitize filenames
def sanitize_filename(filename: str) -> str:
    # Remove characters that are illegal in most file systems
    filename = re.sub(r'[\\/:*?"<>|]', '', filename)
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    # Limit length
    return filename[:100]


# --- API Routes ---

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_link(request: AnalyzeRequest):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'dump_single_json': True,
        'extract_flat': True, # Get information without downloading
        'cachedir': False, # No cache
        'noplaylist': True, # Do not process playlists
        'quiet': True,
        'simulate': True, # Do not download
        'force_ipv4': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(request.url, download=False)

        # Extract title and thumbnail
        title = info_dict.get('title', 'Unknown Title')
        thumbnail = info_dict.get('thumbnail')
        original_url = info_dict.get('webpage_url', request.url) # Use webpage_url if available

        formats_list = []
        if 'formats' in info_dict:
            # Sort by filesize (desc) then quality (desc)
            # Prioritize video-only and audio-only for clarity if they exist
            sorted_formats = sorted(
                info_dict['formats'],
                key=lambda f: (f.get('filesize', 0) or f.get('filesize_approx', 0), f.get('height', 0), f.get('tbr', 0)),
                reverse=True
            )

            seen_qualities = set()
            for f in sorted_formats:
                format_id = f.get('format_id')
                ext = f.get('ext')
                # Skip formats without ext or format_id, or non-mp4/m4a for now
                if not ext or not format_id or (ext not in ['mp4', 'm4a', 'webm', 'ogg', 'mov', 'flv', 'avi']):
                    continue

                quality_label = None
                is_premium = False

                # Handle combined video+audio formats
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    if f.get('height'):
                        quality_label = f"{f['height']}p"
                        if f['height'] >= 1080: # Example: consider 1080p+ as premium
                            is_premium = True
                    elif f.get('tbr'): # Total Bit Rate for audio/other if height not available
                        quality_label = f"{int(f['tbr'])}kbps"
                # Handle audio-only formats
                elif f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                    if f.get('abr'): # Average Bit Rate for audio
                        quality_label = f"Audio {int(f['abr'])}kbps"
                    else:
                        quality_label = "Audio"
                    is_premium = True # All audio-only considered premium for this example
                # Handle video-only formats (might not be directly downloadable, but good for info)
                elif f.get('acodec') == 'none' and f.get('vcodec') != 'none':
                     if f.get('height'):
                        quality_label = f"Video {f['height']}p (no audio)"
                        is_premium = True # Video-only without audio might also be premium

                if not quality_label or quality_label in seen_qualities:
                    continue # Skip if no quality label or already seen

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
        
        # Fallback for simple single files (e.g., direct image/audio links) if no formats list
        elif 'url' in info_dict and 'ext' in info_dict and not formats_list:
            default_ext = info_dict['ext']
            default_quality = "Original"
            default_filesize = info_dict.get('filesize') or info_dict.get('filesize_approx')
            default_size_mb = round(default_filesize / (1024 * 1024), 2) if default_filesize else None

            formats_list.append(FormatInfo(
                format_id="best", # Or a more appropriate default
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
        raise HTTPException(status_code=400, detail=f"Could not analyze link: {e}")

@app.get("/api/download")
async def download_media(
    url: str,
    format_id: str,
    title: str,
    ext: str,
    quality: str,
    response: Response # FastAPI's Response object
):
    try:
        # Define output template, using original filename logic
        sanitized_title = sanitize_filename(title)
        output_template = os.path.join('/tmp', f'{sanitized_title}.%(ext)s') # Download to /tmp

        ydl_opts = {
            'format': format_id,
            'outtmpl': output_template,
            'cachedir': False,
            'noplaylist': True,
            'quiet': True,
            'force_ipv4': True,
            'merge_output_format': ext, # Ensure output is merged to the requested extension
        }

        # Ensure download directory exists
        os.makedirs('/tmp', exist_ok=True)

        # Download the file
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            # Find the actual downloaded file path
            downloaded_file = ydl.prepare_filename(info_dict)
            downloaded_file = re.sub(r'\.part$', '', downloaded_file) # Remove .part if present

        # Check if the file was actually downloaded
        if not os.path.exists(downloaded_file):
            raise FileNotFoundError(f"Downloaded file not found at {downloaded_file}")

        # Stream the file back to the client
        # Important: Use Response(content=...) for streaming a file
        with open(downloaded_file, 'rb') as f:
            content = f.read()

        response.headers["Content-Disposition"] = f"attachment; filename=\"{sanitized_title}.{ext}\""
        response.headers["Content-Type"] = f"application/{ext}" # More specific content type if possible
        response.headers["X-File-Name"] = f"{sanitized_title}.{ext}" # Custom header

        # Clean up the downloaded file
        os.remove(downloaded_file)
        
        return Response(content=content, media_type=f"application/{ext}")

    except FileNotFoundError as fnf_e:
        print(f"File not found error: {fnf_e}")
        raise HTTPException(status_code=500, detail=f"Server error: Downloaded file not found. {fnf_e}")
    except Exception as e:
        print(f"Error during download: {e}")
        # Make sure to import HTTPException if not already
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")