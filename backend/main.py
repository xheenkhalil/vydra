# vydra/backend_api/main.py

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import yt_dlp
import logging
import httpx
from fastapi.responses import StreamingResponse
import re

# --- Configuration & Setup ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vydra Downloader API",
    description="A metadata-only API for Vydra PWA using yt-dlp.",
    version="3.0.0" # Version bump!
)

origins = [
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REFACTOR: Pydantic Models ---

class FormatInfo(BaseModel):
    """
    REFACTOR: This is our new, intelligent format model.
    """
    quality: str      # The pretty display name (e.g., "720p" or "Premium HD (1440p)")
    ext: str          # The file extension (e.g., "mp4")
    size_mb: float | None
    is_premium: bool  # Is this a locked format?
    format_id: str    # The *actual* ID yt-dlp uses (e.g., "303")
    
class AnalyzeResponse(BaseModel):
    title: str
    thumbnail: str | None
    formats: list[FormatInfo]
    original_url: HttpUrl

class AnalyzeRequest(BaseModel):
    """
    Minimal request model for /api/analyze.
    """
    url: HttpUrl

# --- Helper Functions ---

def sanitize_filename(name: str):
    if not name: return "untitled"
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    if sanitized.lstrip().startswith('.'):
        sanitized = "file" + sanitized
    if not sanitized: return "download"
    return sanitized[:200]

# --- REFACTOR: New Format Filtering Logic ---
def get_clean_formats(info: dict) -> list[FormatInfo]:
    """
    This is our new "intelligent" filter.
    It loops through all formats and buckets them
    into the free/premium tiers you specified.
    """
    cleaned_formats = []
    seen_qualities = set() # To prevent duplicates (e.g., 720p webm and 720p mp4)

    # Define our free tiers
    # We use height for video, and extension for audio
    FREE_VIDEO_HEIGHTS = {240, 360, 720, 1080}
    FREE_AUDIO_EXTS = {"mp3", "m4a"}

    for f in info.get('formats', []):
        # We must have a format_id, url, and extension to continue
        if not all(f.get(k) for k in ['format_id', 'url', 'ext']):
            continue

        format_id = f.get('format_id')
        ext = f.get('ext')
        filesize = f.get('filesize') or f.get('filesize_approx')
        size_mb = round(filesize / (1024 * 1024), 2) if filesize else None
        
        quality_label = None
        is_premium = False

        # --- Check Audio Formats ---
        # 'vcodec' == 'none' is a reliable way to check for audio-only
        if f.get('vcodec') == 'none' and ext in FREE_AUDIO_EXTS:
            quality_label = f"Audio ({ext.upper()})"
        
        # --- Check Video Formats ---
        elif f.get('height'):
            height = f.get('height')
            
            if height in FREE_VIDEO_HEIGHTS:
                # It's a free video format
                is_premium = False
                quality_label = f"{height}p"
                if height == 1080:
                    quality_label = "1080p (HD)"
            
            elif height > 1080:
                # It's a premium video format
                is_premium = True
                quality_label = f"Premium HD ({height}p)"
                if height == 2160:
                     quality_label = f"Premium 4K ({height}p)"
            
            # (We ignore formats below 240p)

        # --- Add to our list ---
        if quality_label and quality_label not in seen_qualities:
            seen_qualities.add(quality_label)
            cleaned_formats.append(FormatInfo(
                quality=quality_label,
                ext=ext,
                size_mb=size_mb,
                is_premium=is_premium,
                format_id=format_id # Pass the real ID
            ))

    # Sort the list to be logical: Audio first, then video from low to high
    def sort_key(f: FormatInfo):
        if "Audio" in f.quality:
            return 0
        if "Premium" in f.quality:
            return 2000 # Put premium at the end
        # Extract the number (e.g., 720) from "720p"
        p_val = int(re.sub(r'[^0-9]', '', f.quality))
        return p_val

    cleaned_formats.sort(key=sort_key)
    return cleaned_formats


# --- API Endpoints ---

@app.get("/", tags=["General"])
def read_root():
    return {"status": "Vydra API is running!"}


@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["Core"])
def analyze_url(request: AnalyzeRequest):
    """
    REFACTOR: This endpoint now uses our intelligent filtering logic.
    """
    logger.info(f"Received analysis request for URL: {request.url}")
    
    # We use 'bestvideo+bestaudio/best' to ensure we get all formats
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'quiet': True, 
        'no_warnings': True, 
        'skip_download': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(str(request.url), download=False)
            
            title = info.get('title', 'Untitled')
            thumbnail = info.get('thumbnail')

            # --- REFACTOR: Call our new function ---
            cleaned_formats = get_clean_formats(info)
            
            if not cleaned_formats:
                logger.warning(f"No downloadable formats found for {request.url}")
                raise HTTPException(status_code=404, detail="No downloadable media found at this URL.")

            logger.info(f"Successfully processed {request.url}. Found {len(cleaned_formats)} formats.")
            
            return AnalyzeResponse(
                title=title,
                thumbnail=thumbnail,
                formats=cleaned_formats,
                original_url=request.url
            )

    except Exception as e:
        logger.error(f"Generic server error for {request.url}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/download", tags=["Core"])
async def download_proxy(
    url: HttpUrl, 
    # REFACTOR: We now use 'format_id' for a precise match
    format_id: str, 
    title: str, 
    ext: str,
    quality: str, # Get the quality label for the filename
    request: Request
):
    """
    REFACTOR: This proxy now downloads a *specific* format_id.
    """
    logger.info(f"Received download request for: {title} ({format_id})")

    # We tell yt-dlp to *only* find the format we want
    ydl_opts = {
        'format': format_id,
        'quiet': True, 
        'no_warnings': True, 
        'skip_download': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(str(url), download=False)
            
            # 'info' will be the *specific format* we requested
            # If 'formats' exists, it's a merged format
            if 'formats' in info:
                download_url = info['url'] # Merged format URL
            else:
                download_url = info.get('url') # Single format URL
            
            if not download_url:
                logger.error(f"Could not find URL for format_id {format_id}")
                raise HTTPException(status_code=404, detail="Format not found.")

            logger.info(f"Found matching URL for {format_id}")
            
            client = httpx.AsyncClient(timeout=30.0)
            stream_request = client.build_request("GET", download_url)
            stream_response = await client.send(stream_request, stream=True)
            
            safe_title = sanitize_filename(title)
            # Use the 'quality' label for a clean filename
            filename = f"{safe_title} ({quality}).{ext}"
            
            headers = {
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Type": "application/octet-stream",
            }

            async def event_generator():
                async for chunk in stream_response.aiter_bytes():
                    if await request.is_disconnected():
                        logger.warning("Client disconnected, closing stream.")
                        await client.aclose()
                        break
                    yield chunk
                await client.aclose()
                logger.info("Stream finished.")

            return StreamingResponse(event_generator(), headers=headers)

    except Exception as e:
        logger.error(f"Download proxy error: {e}")
        return "An error occurred while trying to download your file."


# --- Run the Server ---
if __name__ == "__main__":
    print("Starting Vydra API server (v3.0 - Format Filtering) on http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)