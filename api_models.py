from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class JobStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'

class DownloadRequest(BaseModel):
    spotify_url: str
    output_path: Optional[str] = './downloads'
    prefer_flac: bool = False
    token: Optional[str] = None
    filename_format: Optional[str] = 'title_artist'  # title_artist, artist_title, title_only
    use_track_numbers: bool = True
    use_artist_subfolders: bool = False
    use_album_subfolders: bool = False

class DownloadResponse(BaseModel):
    job_id: str
    status: str
    message: str
    track_count: Optional[int] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int  # 0-100
    current_track: Optional[str] = None
    total_tracks: int
    completed_tracks: int
    failed_tracks: int
    skipped_tracks: int
    error_message: Optional[str] = None
    download_path: Optional[str] = None
    downloaded_files: List[str] = []  # Track all downloaded file paths

class TrackInfo(BaseModel):
    id: str
    title: str
    artists: str
    album: str
    track_number: int
    duration_ms: int
    isrc: str = ""
    image_url: str = ""
    release_date: str = ""

class MetadataResponse(BaseModel):
    type: str  # track, album, playlist
    name: str
    artist: Optional[str] = None
    tracks: List[TrackInfo]
    total_tracks: int
    image_url: Optional[str] = None