import asyncio
import logging
import os
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from contextlib import asynccontextmanager

from api_models import (
    DownloadRequest, DownloadResponse, JobStatusResponse, 
    MetadataResponse, TrackInfo, JobStatus
)
from job_manager import job_manager
from download_service import download_service
from getMetadata import get_filtered_data, parse_uri, SpotifyInvalidUrlException
from getToken import get_token
from error_translator import format_error_for_display

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🎵 SpotiDownloader Server starting up...")
    yield
    logger.info("🎵 SpotiDownloader Server shutting down...")

app = FastAPI(
    title="SpotiDownloader Server",
    description="REST API for downloading Spotify tracks with FLAC support",
    version="5.5-FLAC",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and serve PWA
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse('static/index.html')

@app.get("/health")
async def health_check():
    return {"status": "healthy", "active_jobs": len(job_manager.jobs)}

@app.post("/metadata", response_model=MetadataResponse)
async def get_metadata(spotify_url: str):
    """Get metadata for a Spotify URL without downloading"""
    try:
        logger.info(f"Fetching metadata for: {spotify_url}")
        
        # Parse URL and get metadata
        url_info = parse_uri(spotify_url)
        metadata = get_filtered_data(spotify_url)
        
        if "error" in metadata:
            raise HTTPException(status_code=400, detail=metadata["error"])
        
        # Convert to our TrackInfo format  
        tracks = []
        # Handle different metadata structures
        track_list = []
        if "tracks" in metadata:
            track_list = metadata["tracks"]
        elif "track" in metadata:
            track_list = [metadata["track"]]
        elif "items" in metadata:
            track_list = metadata["items"]
        
        for track_data in track_list:
            # Handle different field structures
            if isinstance(track_data.get("artists"), str):
                artists = track_data["artists"]
            elif isinstance(track_data.get("artists"), list):
                artists = ", ".join([artist["name"] for artist in track_data["artists"]])
            else:
                artists = "Unknown Artist"
            
            # Handle album info
            album_name = track_data.get("album_name", "")
            if not album_name and "album" in track_data:
                album_name = track_data["album"].get("name", "")
            
            # Handle image URL
            image_url = track_data.get("images", "")
            if not image_url and "album" in track_data and track_data["album"].get("images"):
                image_url = track_data["album"]["images"][0]["url"]
            
            # Handle release date
            release_date = track_data.get("release_date", "")
            if not release_date and "album" in track_data:
                release_date = track_data["album"].get("release_date", "")
            
            track = TrackInfo(
                id=track_data["id"],
                title=track_data["name"],
                artists=artists,
                album=album_name,
                track_number=track_data.get("track_number", 1),
                duration_ms=track_data.get("duration_ms", 0),
                isrc=track_data.get("isrc", ""),
                image_url=image_url,
                release_date=release_date
            )
            tracks.append(track)
        
        # Determine type and name
        content_type = url_info["type"]
        if content_type == "track":
            name = tracks[0].title if tracks else "Unknown Track"
            artist = tracks[0].artists if tracks else None
        elif content_type == "album":
            name = metadata.get("name", "Unknown Album")
            artist = metadata.get("artists", [{}])[0].get("name") if metadata.get("artists") else None
        else:  # playlist
            name = metadata.get("name", "Unknown Playlist")
            artist = metadata.get("owner", {}).get("display_name")
        
        response = MetadataResponse(
            type=content_type,
            name=name,
            artist=artist,
            tracks=tracks,
            total_tracks=len(tracks),
            image_url=tracks[0].image_url if tracks else None
        )
        
        logger.info(f"Retrieved metadata for {content_type}: {name} ({len(tracks)} tracks)")
        return response
        
    except SpotifyInvalidUrlException as e:
        error_msg = format_error_for_display(error_message=str(e), context="URL Validation")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = format_error_for_display(error_message=str(e), context="Metadata Retrieval")
        logger.error(f"Error fetching metadata: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/download", response_model=DownloadResponse)
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start a download job for the given Spotify URL"""
    try:
        logger.info(f"Starting download for: {request.spotify_url}")
        
        # Get token if not provided
        token = request.token
        if not token:
            logger.info("No token provided, fetching new token...")
            token = get_token()
            if not token:
                raise HTTPException(status_code=500, detail="Failed to obtain authentication token")
        
        # Get metadata first
        url_info = parse_uri(request.spotify_url)
        metadata = get_filtered_data(request.spotify_url)
        
        if "error" in metadata:
            raise HTTPException(status_code=400, detail=metadata["error"])
        
        # Convert tracks
        tracks = []
        # Handle different metadata structures
        track_list = []
        if "tracks" in metadata:
            track_list = metadata["tracks"]
        elif "track" in metadata:
            track_list = [metadata["track"]]
        elif "items" in metadata:
            track_list = metadata["items"]
        
        for track_data in track_list:
            # Handle different field structures
            if isinstance(track_data.get("artists"), str):
                artists = track_data["artists"]
            elif isinstance(track_data.get("artists"), list):
                artists = ", ".join([artist["name"] for artist in track_data["artists"]])
            else:
                artists = "Unknown Artist"
            
            # Handle album info
            album_name = track_data.get("album_name", "")
            if not album_name and "album" in track_data:
                album_name = track_data["album"].get("name", "")
            
            # Handle image URL
            image_url = track_data.get("images", "")
            if not image_url and "album" in track_data and track_data["album"].get("images"):
                image_url = track_data["album"]["images"][0]["url"]
            
            # Handle release date
            release_date = track_data.get("release_date", "")
            if not release_date and "album" in track_data:
                release_date = track_data["album"].get("release_date", "")
            track = TrackInfo(
                id=track_data["id"],
                title=track_data["name"],
                artists=artists,
                album=album_name,
                track_number=track_data.get("track_number", 1),
                duration_ms=track_data.get("duration_ms", 0),
                isrc=track_data.get("isrc", ""),
                image_url=image_url,
                release_date=release_date
            )
            tracks.append(track)
        
        if not tracks:
            raise HTTPException(status_code=400, detail="No tracks found for the given URL")
        
        # Create output directory
        output_path = Path(request.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create job
        job_id = job_manager.create_job(len(tracks), str(output_path))
        
        # Start download task
        task = asyncio.create_task(
            download_service.download_tracks_batch(
                job_id=job_id,
                tracks=tracks,
                outpath=str(output_path),
                token=token,
                prefer_flac=request.prefer_flac,
                filename_format=request.filename_format,
                use_track_numbers=request.use_track_numbers,
                use_artist_subfolders=request.use_artist_subfolders,
                use_album_subfolders=request.use_album_subfolders,
                is_playlist=(url_info["type"] == "playlist")
            )
        )
        
        job_manager.register_task(job_id, task)
        
        content_type = url_info["type"]
        if content_type == "track":
            message = f"Started downloading track: {tracks[0].title}"
        elif content_type == "album":
            message = f"Started downloading album: {metadata.get('name', 'Unknown')} ({len(tracks)} tracks)"
        else:
            message = f"Started downloading playlist: {metadata.get('name', 'Unknown')} ({len(tracks)} tracks)"
        
        logger.info(f"Created job {job_id}: {message}")
        
        return DownloadResponse(
            job_id=job_id,
            status="started",
            message=message,
            track_count=len(tracks)
        )
        
    except SpotifyInvalidUrlException as e:
        error_msg = format_error_for_display(error_message=str(e), context="URL Validation")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = format_error_for_display(error_message=str(e), context="Download Start")
        logger.error(f"Error starting download: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get the status of a download job"""
    job_status = job_manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_status

@app.get("/jobs", response_model=Dict[str, JobStatusResponse])
async def get_all_jobs():
    """Get status of all jobs"""
    return job_manager.get_all_jobs()

@app.delete("/job/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_manager.cancel_job(job_id):
        return {"message": f"Job {job_id} cancelled"}
    else:
        raise HTTPException(status_code=404, detail="Job not found or already completed")

@app.post("/token")
async def fetch_token():
    """Fetch a new authentication token"""
    try:
        logger.info("Fetching new token...")
        token = get_token()
        if token:
            return {"token": token, "message": "Token fetched successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch token")
    except Exception as e:
        error_msg = format_error_for_display(error_message=str(e), context="Token Fetch")
        logger.error(f"Error fetching token: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/download-files/{job_id}")
async def download_job_files(job_id: str):
    """Download all files from a completed job as a ZIP"""
    job_status = job_manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_status.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    if not job_status.downloaded_files:
        raise HTTPException(status_code=404, detail="No files to download")
    
    # Create a temporary ZIP file
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    try:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in job_status.downloaded_files:
                if os.path.exists(file_path):
                    # Add file to ZIP with just the filename (no path)
                    zipf.write(file_path, os.path.basename(file_path))
        
        def cleanup_zip():
            """Clean up the temporary ZIP file after sending"""
            try:
                os.unlink(temp_zip.name)
            except:
                pass
        
        # Return the ZIP file and trigger cleanup
        response = FileResponse(
            temp_zip.name,
            media_type='application/zip',
            filename=f'spotify_download_{job_id[:8]}.zip',
            background=BackgroundTasks()
        )
        response.background.add_task(cleanup_zip)
        
        # Trigger job cleanup after file is served
        response.background.add_task(job_manager.cleanup_job_files, job_id)
        
        return response
        
    except Exception as e:
        # Cleanup on error
        try:
            os.unlink(temp_zip.name)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to create download: {str(e)}")

@app.get("/download-file/{job_id}/{file_index}")
async def download_single_file(job_id: str, file_index: int):
    """Download a single file from a job"""
    job_status = job_manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job_status.downloaded_files or file_index >= len(job_status.downloaded_files):
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = job_status.downloaded_files[file_index]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File no longer exists")
    
    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type='audio/mpeg' if file_path.endswith('.mp3') else 'audio/flac'
    )

# Test endpoint for the track you wanted to test
@app.post("/test-download")
async def test_download_endpoint():
    """Test endpoint with the track you provided"""
    test_url = "https://open.spotify.com/intl-de/track/1LguH2WiuSossO7VztfTAl"
    
    request = DownloadRequest(
        spotify_url=test_url,
        output_path="./test_downloads",
        prefer_flac=True,
        filename_format="title_artist"
    )
    
    background_tasks = BackgroundTasks()
    return await start_download(request, background_tasks)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)