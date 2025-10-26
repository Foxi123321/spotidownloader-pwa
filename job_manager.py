import uuid
import asyncio
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from api_models import JobStatus, JobStatusResponse
import logging

logger = logging.getLogger(__name__)

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, JobStatusResponse] = {}
        self.job_tasks: Dict[str, asyncio.Task] = {}
    
    def create_job(self, total_tracks: int, download_path: str) -> str:
        """Create a new download job and return its ID"""
        job_id = str(uuid.uuid4())
        
        job_status = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            progress=0,
            total_tracks=total_tracks,
            completed_tracks=0,
            failed_tracks=0,
            skipped_tracks=0,
            download_path=download_path
        )
        
        self.jobs[job_id] = job_status
        logger.info(f"Created job {job_id} for {total_tracks} tracks")
        return job_id
    
    def update_job_status(self, job_id: str, status: JobStatus, error_message: Optional[str] = None):
        """Update job status"""
        if job_id in self.jobs:
            self.jobs[job_id].status = status
            if error_message:
                self.jobs[job_id].error_message = error_message
    
    def update_job_progress(self, job_id: str, current_track: str, completed: int, failed: int, skipped: int):
        """Update job progress"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.current_track = current_track
            job.completed_tracks = completed
            job.failed_tracks = failed
            job.skipped_tracks = skipped
            job.progress = int(((completed + failed + skipped) / job.total_tracks) * 100)
    
    def add_downloaded_file(self, job_id: str, file_path: str):
        """Add a downloaded file to the job's file list"""
        if job_id in self.jobs:
            self.jobs[job_id].downloaded_files.append(file_path)
    
    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get job status by ID"""
        return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> Dict[str, JobStatusResponse]:
        """Get all jobs"""
        return self.jobs.copy()
    
    def register_task(self, job_id: str, task: asyncio.Task):
        """Register asyncio task for job"""
        self.job_tasks[job_id] = task
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        if job_id in self.job_tasks:
            task = self.job_tasks[job_id]
            if not task.done():
                task.cancel()
                self.update_job_status(job_id, JobStatus.FAILED, "Job cancelled by user")
                return True
        return False
    
    def cleanup_job_files(self, job_id: str):
        """Clean up downloaded files for a specific job"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            for file_path in job.downloaded_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Cleaned up file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup file {file_path}: {e}")
            
            # Clean up empty directories
            if job.download_path and os.path.exists(job.download_path):
                try:
                    if not os.listdir(job.download_path):  # Directory is empty
                        os.rmdir(job.download_path)
                        logger.info(f"Cleaned up empty directory: {job.download_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup directory {job.download_path}: {e}")
    
    def cleanup_finished_jobs(self):
        """Remove completed/failed jobs older than 1 hour and their files"""
        cutoff_time = datetime.now() - timedelta(hours=1)
        jobs_to_remove = []
        
        for job_id, job in self.jobs.items():
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                # For now, cleanup immediately after completion for free tier efficiency
                self.cleanup_job_files(job_id)
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del self.jobs[job_id]
            if job_id in self.job_tasks:
                del self.job_tasks[job_id]
            logger.info(f"Cleaned up job {job_id}")

# Global job manager instance
job_manager = JobManager()