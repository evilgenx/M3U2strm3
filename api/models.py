"""
Pydantic models for M3U2strm3 Web Interface API.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class ProcessingConfig(BaseModel):
    """Configuration model for M3U2strm3 processing."""
    
    # Basic paths
    m3u: str = Field(..., description="Path to M3U playlist file")
    sqlite_cache_file: str = Field(..., description="Path to SQLite cache file")
    log_file: str = Field(..., description="Path to log file")
    output_dir: str = Field(..., description="Output directory for STRM files")
    
    # Media directories
    existing_media_dirs: List[str] = Field(..., description="List of existing media directories")
    
    # API keys
    tmdb_api: str = Field(..., description="TMDb API key")
    emby_api_url: Optional[str] = Field(None, description="Emby API URL")
    emby_api_key: Optional[str] = Field(None, description="Emby API key")
    
    # Processing options
    dry_run: bool = Field(False, description="Dry run mode")
    max_workers: Optional[int] = Field(None, description="Maximum worker threads")
    verbosity: str = Field("normal", description="Logging verbosity level")
    
    # Filtering options
    allowed_movie_countries: List[str] = Field(["US", "GB", "CA"], description="Allowed movie countries")
    allowed_tv_countries: List[str] = Field(["US", "GB", "CA"], description="Allowed TV countries")
    write_non_us_report: bool = Field(True, description="Write non-US report")
    
    # Content classification
    tv_group_keywords: List[str] = Field([], description="TV group keywords")
    doc_group_keywords: List[str] = Field([], description="Documentary group keywords")
    movie_group_keywords: List[str] = Field([], description="Movie group keywords")
    replay_group_keywords: List[str] = Field([], description="Replay group keywords")
    
    # Keyword filtering
    ignore_keywords: Dict[str, List[str]] = Field({}, description="Keywords to ignore")
    
    @validator('verbosity')
    def validate_verbosity(cls, v):
        valid_levels = ['quiet', 'normal', 'verbose', 'debug']
        if v not in valid_levels:
            raise ValueError(f"Verbosity must be one of: {', '.join(valid_levels)}")
        return v
    
    @validator('max_workers')
    def validate_max_workers(cls, v):
        if v is not None and v < 1:
            raise ValueError("max_workers must be positive")
        return v


class ProcessingStatus(BaseModel):
    """Status model for processing jobs."""
    
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    progress: float = Field(0.0, description="Progress percentage")
    current_phase: str = Field("", description="Current processing phase")
    processed_items: int = Field(0, description="Number of items processed")
    total_items: int = Field(0, description="Total items to process")
    start_time: Optional[datetime] = Field(None, description="Job start time")
    end_time: Optional[datetime] = Field(None, description="Job end time")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class ProcessingResult(BaseModel):
    """Result model for completed processing jobs."""
    
    job_id: str = Field(..., description="Job identifier")
    success: bool = Field(..., description="Whether processing succeeded")
    message: str = Field(..., description="Result message")
    stats: Dict[str, Any] = Field({}, description="Processing statistics")
    output_files: List[str] = Field([], description="List of created output files")
    duration: float = Field(0.0, description="Processing duration in seconds")


class FileUploadResponse(BaseModel):
    """Response model for file uploads."""
    
    filename: str = Field(..., description="Original filename")
    size: int = Field(..., description="File size in bytes")
    path: str = Field(..., description="Server path to uploaded file")
    message: str = Field(..., description="Upload result message")


class SystemStatus(BaseModel):
    """System status model."""
    
    status: str = Field(..., description="System status")
    current_job: Optional[ProcessingStatus] = Field(None, description="Current processing job")
    queue_length: int = Field(0, description="Number of jobs in queue")
    system_info: Dict[str, Any] = Field({}, description="System information")


class LogEntry(BaseModel):
    """Log entry model."""
    
    timestamp: datetime = Field(..., description="Log entry timestamp")
    level: str = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    source: Optional[str] = Field(None, description="Source component")


class ProgressUpdate(BaseModel):
    """Progress update model for WebSocket."""
    
    phase: str = Field(..., description="Current processing phase")
    progress: float = Field(..., description="Progress percentage")
    processed: int = Field(..., description="Items processed")
    total: int = Field(..., description="Total items")
    current_item: str = Field("", description="Current item being processed")
    items_per_second: float = Field(0.0, description="Processing speed")
    elapsed_time: float = Field(0.0, description="Elapsed time in seconds")
    stats: Dict[str, int] = Field({}, description="Current statistics")
    errors: List[str] = Field([], description="Current errors")
