import os
import re
import requests
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import logging

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TRCK, TSRC, COMM

from api_models import TrackInfo, JobStatus
from job_manager import job_manager
from error_translator import format_error_for_display

logger = logging.getLogger(__name__)

class DownloadService:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_formatted_filename(self, track: TrackInfo, extension: str = ".mp3", filename_format: str = "title_artist") -> str:
        """Generate filename based on format preference"""
        if filename_format == "artist_title":
            filename = f"{track.artists} - {track.title}{extension}"
        elif filename_format == "title_only":
            filename = f"{track.title}{extension}"
        else:  # title_artist (default)
            filename = f"{track.title} - {track.artists}{extension}"
        
        # Clean filename of invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', lambda m: "'" if m.group() == '"' else '_', filename)
        return filename

    def is_valid_existing_file(self, filepath: str) -> bool:
        """Check if file exists and is valid"""
        if not os.path.exists(filepath):
            return False
        
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 100000:  # Less than 100KB is suspicious
                return False
            
            # Try to load as MP3 first
            try:
                audio = MP3(filepath)
                if audio.info.length > 0:
                    return True
            except:
                # For FLAC files, just check if file size is reasonable
                if filepath.lower().endswith('.flac') and file_size > 500000:
                    return True
                
            return False
        except Exception:
            return False

    async def download_track_async(self, track: TrackInfo, outpath: str, token: str, 
                                 prefer_flac: bool = False, filename_format: str = "title_artist",
                                 use_track_numbers: bool = True) -> Tuple[bool, str]:
        """Download a single track asynchronously"""
        try:
            filename = self.get_formatted_filename(track, filename_format=filename_format)
            
            if use_track_numbers:
                filename = f"{track.track_number:02d} - {filename}"
            
            filepath = os.path.join(outpath, filename)

            # Check if file already exists and is valid
            if self.is_valid_existing_file(filepath):
                return True, "File already exists - skipped"
            
            # Remove corrupted file if exists
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    return False, f"Failed to remove corrupted file: {str(e)}"

            # Prepare API headers
            headers = {
                'Host': 'api.spotidownloader.com',
                'Referer': 'https://spotidownloader.com/',
                'Origin': 'https://spotidownloader.com',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            payload = {"id": track.id}
            
            # Make download request
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(
                    "https://api.spotidownloader.com/download",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
            )
            
            if response.status_code != 200:
                error_msg = format_error_for_display(
                    status_code=response.status_code,
                    response_text=response.text,
                    context="Download API Request"
                )
                return False, error_msg
            
            data = response.json()
            if not data.get('success'):
                error_msg = data.get('error', data.get('message', 'Unknown error'))
                return False, error_msg
            
            if not data.get('link'):
                return False, "No download link provided by API"
            
            # Check for FLAC if preferred
            download_url = data['link']
            file_extension = ".mp3"
            
            if prefer_flac:
                try:
                    flac_response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(
                            "https://api.spotidownloader.com/isFlacAvailable",
                            headers=headers,
                            json=payload,
                            timeout=10
                        )
                    )
                    
                    if flac_response.status_code == 200:
                        flac_data = flac_response.json()
                        if flac_data.get('flacAvailable', False):
                            # Get FLAC download
                            flac_payload = {"id": track.id, "lossless": True}
                            flac_download_response = await loop.run_in_executor(
                                None,
                                lambda: requests.post(
                                    "https://api.spotidownloader.com/download",
                                    headers=headers,
                                    json=flac_payload,
                                    timeout=30
                                )
                            )
                            
                            if (flac_download_response.status_code == 200 and 
                                flac_download_response.json().get('success') and 
                                flac_download_response.json().get('link')):
                                download_url = flac_download_response.json()['link']
                                file_extension = ".flac"
                                logger.info(f"FLAC download available for: {track.title}")
                except Exception as e:
                    logger.warning(f"FLAC check failed for {track.title}: {e}")
            
            # Update filename with correct extension
            filename = self.get_formatted_filename(track, file_extension, filename_format)
            if use_track_numbers:
                filename = f"{track.track_number:02d} - {filename}"
            filepath = os.path.join(outpath, filename)
            
            # Download the audio file
            host = download_url.split('//', 1)[1].split('/', 1)[0]
            download_headers = {
                'Host': host,
                'Referer': 'https://spotidownloader.com/',
                'Origin': 'https://spotidownloader.com'
            }
            
            audio_response = await loop.run_in_executor(
                None,
                lambda: requests.get(download_url, headers=download_headers, timeout=300)
            )
            
            if audio_response.status_code != 200:
                return False, f"Failed to download audio: HTTP {audio_response.status_code}"
            
            # Save file
            temp_filepath = filepath + ".tmp"
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._write_file(temp_filepath, audio_response.content)
                )
                
                if self.is_valid_existing_file(temp_filepath):
                    os.rename(temp_filepath, filepath)
                    # Only embed metadata for MP3 files
                    if file_extension == ".mp3":
                        await loop.run_in_executor(None, lambda: self.embed_metadata(filepath, track))
                    return True, filepath  # Return filepath for tracking
                else:
                    if os.path.exists(temp_filepath):
                        os.remove(temp_filepath)
                    return False, "Downloaded file appears to be corrupted"
            except Exception as e:
                if os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except:
                        pass
                raise e
            
            return True, filepath
            
        except Exception as e:
            error_msg = format_error_for_display(
                error_message=str(e),
                context="Track Download"
            )
            return False, error_msg

    def _write_file(self, filepath: str, content: bytes):
        """Helper to write file content"""
        with open(filepath, "wb") as file:
            file.write(content)

    def embed_metadata(self, filepath: str, track: TrackInfo):
        """Embed metadata into MP3 file"""
        try:
            audio = MP3(filepath, ID3=ID3)
            
            try:
                audio.add_tags()
            except:
                pass

            audio.tags.add(TIT2(encoding=3, text=track.title))
            audio.tags.add(TPE1(encoding=3, text=track.artists.split(", ")))
            audio.tags.add(TALB(encoding=3, text=track.album))
            audio.tags.add(COMM(encoding=3, lang='eng', desc='Source', text='SpotiDownloader-Server'))

            # Add release date
            if track.release_date:
                try:
                    if track.release_date.isdigit() and len(track.release_date) == 4:
                        audio.tags.add(TDRC(encoding=3, text=track.release_date))
                    else:
                        release_date = datetime.strptime(track.release_date, "%Y-%m-%d")
                        audio.tags.add(TDRC(encoding=3, text=track.release_date))
                except ValueError:
                    pass

            audio.tags.add(TRCK(encoding=3, text=str(track.track_number)))
            audio.tags.add(TSRC(encoding=3, text=track.isrc))

            # Add cover art
            if track.image_url:
                try:
                    image_headers = {
                        'Referer': 'https://spotidownloader.com/',
                        'Origin': 'https://spotidownloader.com'
                    }
                    image_data = requests.get(track.image_url, headers=image_headers, timeout=10).content
                    audio.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='',
                        data=image_data
                    ))
                except Exception as e:
                    logger.warning(f"Failed to add cover art: {e}")

            audio.save()
        except Exception as e:
            logger.warning(f"Failed to embed metadata for {track.title}: {e}")

    async def download_tracks_batch(self, job_id: str, tracks: List[TrackInfo], outpath: str, 
                                  token: str, prefer_flac: bool = False, 
                                  filename_format: str = "title_artist", use_track_numbers: bool = True,
                                  use_artist_subfolders: bool = False, use_album_subfolders: bool = False,
                                  is_playlist: bool = False):
        """Download multiple tracks with progress tracking"""
        
        # Ensure output directory exists
        Path(outpath).mkdir(parents=True, exist_ok=True)
        
        job_manager.update_job_status(job_id, JobStatus.RUNNING)
        
        completed = 0
        failed = 0
        skipped = 0
        
        for i, track in enumerate(tracks):
            try:
                # Determine output path for this track
                track_outpath = outpath
                
                if is_playlist:
                    if use_artist_subfolders:
                        artist_name = track.artists.split(', ')[0] if ', ' in track.artists else track.artists
                        artist_folder = re.sub(r'[<>:"/\\|?*]', lambda m: "'" if m.group() == '"' else '_', artist_name)
                        track_outpath = os.path.join(track_outpath, artist_folder)
                    
                    if use_album_subfolders:
                        album_folder = re.sub(r'[<>:"/\\|?*]', lambda m: "'" if m.group() == '"' else '_', track.album)
                        track_outpath = os.path.join(track_outpath, album_folder)
                    
                    Path(track_outpath).mkdir(parents=True, exist_ok=True)
                
                # Update progress
                current_track_display = f"{track.title} - {track.artists}"
                job_manager.update_job_progress(job_id, current_track_display, completed, failed, skipped)
                
                # Download track
                success, result = await self.download_track_async(
                    track, track_outpath, token, prefer_flac, filename_format, use_track_numbers
                )
                
                if success:
                    if result == "File already exists - skipped":
                        skipped += 1
                        logger.info(f"Skipped existing: {track.title}")
                    else:
                        completed += 1
                        # Track the downloaded file
                        job_manager.add_downloaded_file(job_id, result)
                        logger.info(f"Downloaded: {track.title}")
                else:
                    failed += 1
                    logger.error(f"Failed to download {track.title}: {result}")
                
                # Small delay to prevent rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                failed += 1
                logger.error(f"Exception downloading {track.title}: {e}")
        
        # Final status update
        job_manager.update_job_progress(job_id, "Completed", completed, failed, skipped)
        job_manager.update_job_status(job_id, JobStatus.COMPLETED)
        
        logger.info(f"Job {job_id} completed: {completed} successful, {failed} failed, {skipped} skipped")

# Global download service instance
download_service = DownloadService()