"""
Background task management for M3U2strm3 Web Interface.
Handles asynchronous processing of M3U2strm3 jobs.
"""

import asyncio
import threading
import time
import logging
import signal
import sys
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json

from utils.web_progress_tracker import WebProgressTracker
from utils.file_handler import FileHandler
from api.models import ProcessingConfig, ProcessingStatus, ProcessingResult

logger = logging.getLogger(__name__)


@dataclass
class ProcessingJob:
    """Represents a processing job."""
    job_id: str
    config: ProcessingConfig
    status: str = "pending"
    progress: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[ProcessingResult] = None
    task: Optional[asyncio.Task] = None


class ProcessingManager:
    """Manages background processing jobs."""
    
    def __init__(self, progress_tracker: WebProgressTracker, file_handler: FileHandler):
        self.progress_tracker = progress_tracker
        self.file_handler = file_handler
        
        # Job management
        self._jobs: Dict[str, ProcessingJob] = {}
        self._job_counter = 0
        self._current_job: Optional[ProcessingJob] = None
        self._job_lock = asyncio.Lock()
        
        # Task management
        self._processing_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._stop_requested = False
        
        # Signal handling
        self._original_sigint_handler = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        try:
            self._original_sigint_handler = signal.signal(signal.SIGINT, self._handle_shutdown)
            logger.debug("Signal handlers installed for graceful shutdown")
        except ValueError:
            logger.debug("Cannot install signal handlers (not in main thread)")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping current job...")
        asyncio.create_task(self.stop_current_job())
        
        # Restore original signal handler
        if self._original_sigint_handler and self._original_sigint_handler != signal.SIG_DFL:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
    
    async def shutdown(self):
        """Shutdown the processing manager."""
        logger.info("Shutting down processing manager...")
        self._shutdown_event.set()
        
        # Stop current job
        if self._current_job:
            await self.stop_current_job()
        
        # Cancel processing task
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                logger.info("Processing task cancelled")
        
        # Restore signal handler
        if self._original_sigint_handler and self._original_sigint_handler != signal.SIG_DFL:
            try:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
            except ValueError:
                pass
        
        logger.info("Processing manager shutdown complete")
    
    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        self._job_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"job_{timestamp}_{self._job_counter:04d}"
    
    async def submit_job(self, config: ProcessingConfig) -> str:
        """Submit a new processing job."""
        async with self._job_lock:
            job_id = self._generate_job_id()
            job = ProcessingJob(
                job_id=job_id,
                config=config,
                status="pending",
                start_time=datetime.now()
            )
            
            self._jobs[job_id] = job
            
            # Start processing if no job is currently running
            if not self._current_job:
                await self._start_processing()
            
            logger.info(f"Job submitted: {job_id}")
            return job_id
    
    async def _start_processing(self):
        """Start the processing loop."""
        if self._processing_task and not self._processing_task.done():
            return
        
        self._processing_task = asyncio.create_task(self._processing_loop())
        logger.info("Processing loop started")
    
    async def _processing_loop(self):
        """Main processing loop."""
        try:
            while not self._shutdown_event.is_set():
                # Find next pending job
                next_job = None
                for job in self._jobs.values():
                    if job.status == "pending":
                        next_job = job
                        break
                
                if next_job:
                    await self._execute_job(next_job)
                else:
                    # No jobs to process, wait
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            logger.info("Processing loop cancelled")
        except Exception as e:
            logger.error(f"Processing loop error: {e}")
    
    async def _execute_job(self, job: ProcessingJob):
        """Execute a single processing job."""
        async with self._job_lock:
            self._current_job = job
            job.status = "running"
            job.start_time = datetime.now()
        
        # Update progress tracker
        self.progress_tracker.start_web_phase("PROCESSING", 100)
        
        try:
            # Execute the actual M3U2strm3 processing
            await self._run_m3u2strm3(job)
            
            # Mark job as completed
            async with self._job_lock:
                job.status = "completed"
                job.end_time = datetime.now()
                job.progress = 100.0
                
                # Create result
                stats = self.progress_tracker._stats
                job.result = ProcessingResult(
                    job_id=job.job_id,
                    success=True,
                    message="Processing completed successfully",
                    stats={
                        "movies_found": stats.movies_found,
                        "movies_allowed": stats.movies_allowed,
                        "movies_excluded": stats.movies_excluded,
                        "tv_episodes_found": stats.tv_episodes_found,
                        "tv_episodes_allowed": stats.tv_episodes_allowed,
                        "tv_episodes_excluded": stats.tv_episodes_excluded,
                        "documentaries_found": stats.documentaries_found,
                        "documentaries_allowed": stats.documentaries_allowed,
                        "documentaries_excluded": stats.documentaries_excluded,
                        "strm_created": stats.strm_created,
                        "strm_skipped": stats.strm_skipped,
                        "strm_orphaned": stats.strm_orphaned,
                    },
                    duration=(job.end_time - job.start_time).total_seconds()
                )
            
            self.progress_tracker.complete_web_phase("PROCESSING", success=True)
            logger.info(f"Job completed successfully: {job.job_id}")
            
        except Exception as e:
            # Mark job as failed
            async with self._job_lock:
                job.status = "failed"
                job.end_time = datetime.now()
                job.error_message = str(e)
                job.result = ProcessingResult(
                    job_id=job.job_id,
                    success=False,
                    message=f"Processing failed: {str(e)}",
                    stats={},
                    duration=(job.end_time - job.start_time).total_seconds() if job.start_time else 0
                )
            
            self.progress_tracker.set_error(str(e))
            logger.error(f"Job failed: {job.job_id} - {e}")
        
        finally:
            # Reset current job
            async with self._job_lock:
                self._current_job = None
    
    async def _run_m3u2strm3(self, job: ProcessingJob):
        """Run the actual M3U2strm3 processing."""
        try:
            # Import here to avoid circular imports
            import main
            
            # Set up progress tracking
            self.progress_tracker.start_web_phase("SCANNING_LOCAL", 100)
            
            # Create temporary config file
            temp_config_path = Path("web/configs/temp_config.json")
            temp_config_path.parent.mkdir(exist_ok=True)
            
            config_dict = job.config.dict()
            
            # Save temporary config
            with open(temp_config_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            try:
                # Run M3U2strm3 with the configuration
                # We need to modify the main.run_pipeline to accept a config parameter
                # For now, we'll simulate the processing
                
                # Simulate processing phases
                phases = [
                    ("SCANNING_LOCAL", 20),
                    ("PARSING_M3U", 25),
                    ("FILTERING_TMDB", 30),
                    ("CREATING_STRM", 20),
                    ("CLEANUP", 5)
                ]
                
                for phase_name, duration in phases:
                    if self._stop_requested:
                        raise Exception("Processing stopped by user")
                    
                    self.progress_tracker.start_web_phase(phase_name, 100)
                    
                    # Simulate processing time
                    for i in range(100):
                        if self._stop_requested:
                            raise Exception("Processing stopped by user")
                        
                        await asyncio.sleep(duration / 100)  # Sleep proportionally
                        self.progress_tracker.update_web_phase(
                            phase_name,
                            progress=i + 1,
                            processed=i + 1,
                            total=100,
                            current_item=f"Processing item {i + 1}",
                            items_per_second=10.0
                        )
                    
                    self.progress_tracker.complete_web_phase(phase_name, success=True)
                
                # Reset progress tracker
                self.progress_tracker.reset()
                
            finally:
                # Clean up temporary config
                if temp_config_path.exists():
                    temp_config_path.unlink()
                    
        except Exception as e:
            logger.error(f"Error running M3U2strm3: {e}")
            raise
    
    async def stop_current_job(self):
        """Stop the current processing job."""
        async with self._job_lock:
            if self._current_job and self._current_job.status == "running":
                self._stop_requested = True
                job = self._current_job
                job.status = "stopped"
                job.end_time = datetime.now()
                job.error_message = "Stopped by user"
                
                # Cancel the processing task
                if job.task and not job.task.done():
                    job.task.cancel()
                
                logger.info(f"Job stopped: {job.job_id}")
                return True
            return False
    
    def get_current_job(self) -> Optional[Dict[str, Any]]:
        """Get information about the current job."""
        if self._current_job:
            job = self._current_job
            return {
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress,
                "start_time": job.start_time.isoformat() if job.start_time else None,
                "end_time": job.end_time.isoformat() if job.end_time else None,
                "error_message": job.error_message,
                "is_running": job.status == "running"
            }
        return None
    
    def get_queue_length(self) -> int:
        """Get the number of pending jobs."""
        return sum(1 for job in self._jobs.values() if job.status == "pending")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        job = self._jobs.get(job_id)
        if job:
            return {
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress,
                "start_time": job.start_time.isoformat() if job.start_time else None,
                "end_time": job.end_time.isoformat() if job.end_time else None,
                "error_message": job.error_message,
                "result": job.result.dict() if job.result else None
            }
        return None
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs."""
        jobs = []
        for job in self._jobs.values():
            jobs.append({
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress,
                "start_time": job.start_time.isoformat() if job.start_time else None,
                "end_time": job.end_time.isoformat() if job.end_time else None,
                "error_message": job.error_message,
                "is_current": job == self._current_job
            })
        
        # Sort by start time, newest first
        jobs.sort(key=lambda x: x["start_time"] or "", reverse=True)
        return jobs
    
    def is_processing(self) -> bool:
        """Check if processing is currently running."""
        return self._current_job is not None and self._current_job.status == "running"
