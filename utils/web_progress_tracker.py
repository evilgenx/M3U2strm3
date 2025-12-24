"""
Web-compatible progress tracker that integrates with the existing ProgressTracker.
"""

import asyncio
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager
import logging

from progress_tracker import ProgressTracker, ProgressPhase, VerbosityLevel, PhaseProgress, ProcessingStats
from api.models import ProgressUpdate

logger = logging.getLogger(__name__)


class WebProgressPhase(Enum):
    """Web-specific progress phases."""
    IDLE = "Idle"
    UPLOADING = "Uploading File"
    CONFIGURING = "Configuring"
    PROCESSING = "Processing"
    SCANNING_LOCAL = "Scanning Local Media"
    PARSING_M3U = "Parsing M3U Playlist"
    FILTERING_TMDB = "TMDb Filtering"
    CREATING_STRM = "Creating STRM Files"
    CLEANUP = "Cleanup & Finalization"
    COMPLETE = "Complete"
    ERROR = "Error"


@dataclass
class WebPhaseProgress:
    """Web-specific phase progress tracking."""
    phase: WebProgressPhase
    progress: float = 0.0
    processed: int = 0
    total: int = 0
    current_item: str = ""
    items_per_second: float = 0.0
    elapsed_time: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None


class WebProgressTracker:
    """Web-compatible progress tracker that wraps the existing ProgressTracker."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._web_phases: Dict[WebProgressPhase, WebPhaseProgress] = {}
        self._current_web_phase: WebProgressPhase = WebProgressPhase.IDLE
        self._stats = ProcessingStats()
        self._start_time = time.time()
        self._callbacks: List[Callable[[Any], None]] = []
        self._websocket_clients: List[asyncio.Queue] = []
        self._shutdown_flag = threading.Event()
        
        # Bridge to existing ProgressTracker
        self._core_tracker: Optional[ProgressTracker] = None
        self._core_phase_mapping = {
            ProgressPhase.SCANNING_LOCAL: WebProgressPhase.SCANNING_LOCAL,
            ProgressPhase.PARSING_M3U: WebProgressPhase.PARSING_M3U,
            ProgressPhase.FILTERING_TMDB: WebProgressPhase.FILTERING_TMDB,
            ProgressPhase.CREATING_STRM: WebProgressPhase.CREATING_STRM,
            ProgressPhase.CLEANUP: WebProgressPhase.CLEANUP,
        }
        
        # Initialize web phases
        for phase in WebProgressPhase:
            self._web_phases[phase] = WebPhaseProgress(phase=phase)
    
    def set_core_tracker(self, tracker: ProgressTracker):
        """Set the core ProgressTracker to bridge with."""
        self._core_tracker = tracker
        if tracker:
            # Register callback to receive updates from core tracker
            tracker.register_callback(self._on_core_progress_update)
    
    def _on_core_progress_update(self, tracker: ProgressTracker):
        """Callback from core ProgressTracker."""
        try:
            current_phase = tracker.get_current_phase()
            if current_phase:
                # Map core phase to web phase
                web_phase = self._core_phase_mapping.get(current_phase.phase)
                if web_phase:
                    self._update_web_phase(
                        web_phase,
                        progress=current_phase.progress_percent,
                        processed=current_phase.processed,
                        total=current_phase.total,
                        current_item=current_phase.current_item,
                        items_per_second=current_phase.items_per_second,
                        elapsed_time=current_phase.elapsed_time
                    )
            
            # Update stats
            stats = tracker.get_stats()
            self._stats = stats
            
            # Broadcast update
            self._broadcast_update()
            
        except Exception as e:
            logger.error(f"Error in core progress update callback: {e}")
    
    def start_web_phase(self, phase: WebProgressPhase, total_items: int = 0):
        """Start a web-specific phase."""
        with self._lock:
            self._current_web_phase = phase
            web_phase = self._web_phases[phase]
            web_phase.started_at = time.time()
            web_phase.total = total_items
            web_phase.processed = 0
            web_phase.progress = 0.0
            web_phase.error_message = None
            
            logger.info(f"Starting web phase: {phase.value}")
            self._broadcast_update()
    
    def update_web_phase(self, phase: WebProgressPhase, progress: float = None, 
                        processed: int = None, total: int = None, 
                        current_item: str = "", items_per_second: float = None):
        """Update a web-specific phase."""
        with self._lock:
            web_phase = self._web_phases[phase]
            
            if progress is not None:
                web_phase.progress = min(100.0, max(0.0, progress))
            if processed is not None:
                web_phase.processed = processed
            if total is not None:
                web_phase.total = total
            if current_item:
                web_phase.current_item = current_item[:100]
            if items_per_second is not None:
                web_phase.items_per_second = items_per_second
            
            # Update elapsed time
            if web_phase.started_at:
                web_phase.elapsed_time = time.time() - web_phase.started_at
            
            self._broadcast_update()
    
    def complete_web_phase(self, phase: WebProgressPhase, success: bool = True, error_message: str = None):
        """Complete a web-specific phase."""
        with self._lock:
            web_phase = self._web_phases[phase]
            web_phase.completed_at = time.time()
            web_phase.progress = 100.0
            web_phase.error_message = error_message
            
            if success:
                logger.info(f"Completed web phase: {phase.value}")
            else:
                logger.error(f"Failed web phase: {phase.value} - {error_message}")
            
            self._broadcast_update()
    
    def set_error(self, error_message: str):
        """Set an error state."""
        with self._lock:
            self._current_web_phase = WebProgressPhase.ERROR
            for phase in self._web_phases.values():
                phase.error_message = error_message
            self._broadcast_update()
    
    def get_web_progress(self) -> Dict[str, Any]:
        """Get current web progress as a dictionary."""
        with self._lock:
            current_phase = self._web_phases[self._current_web_phase]
            
            # Calculate overall progress
            overall_progress = self._calculate_overall_progress()
            
            return {
                "current_phase": self._current_web_phase.value,
                "phase_progress": current_phase.progress,
                "overall_progress": overall_progress,
                "processed": current_phase.processed,
                "total": current_phase.total,
                "current_item": current_phase.current_item,
                "items_per_second": current_phase.items_per_second,
                "elapsed_time": current_phase.elapsed_time,
                "stats": {
                    "movies_found": self._stats.movies_found,
                    "movies_allowed": self._stats.movies_allowed,
                    "movies_excluded": self._stats.movies_excluded,
                    "tv_episodes_found": self._stats.tv_episodes_found,
                    "tv_episodes_allowed": self._stats.tv_episodes_allowed,
                    "tv_episodes_excluded": self._stats.tv_episodes_excluded,
                    "documentaries_found": self._stats.documentaries_found,
                    "documentaries_allowed": self._stats.documentaries_allowed,
                    "documentaries_excluded": self._stats.documentaries_excluded,
                    "strm_created": self._stats.strm_created,
                    "strm_skipped": self._stats.strm_skipped,
                    "strm_orphaned": self._stats.strm_orphaned,
                    "errors": self._stats.errors[-10:]  # Last 10 errors
                },
                "error_message": current_phase.error_message,
                "is_complete": self._current_web_phase == WebProgressPhase.COMPLETE,
                "is_error": self._current_web_phase == WebProgressPhase.ERROR
            }
    
    def _calculate_overall_progress(self) -> float:
        """Calculate overall progress across all phases."""
        if not self._web_phases:
            return 0.0
        
        # Weight different phases
        phase_weights = {
            WebProgressPhase.UPLOADING: 5.0,
            WebProgressPhase.CONFIGURING: 5.0,
            WebProgressPhase.SCANNING_LOCAL: 15.0,
            WebProgressPhase.PARSING_M3U: 20.0,
            WebProgressPhase.FILTERING_TMDB: 25.0,
            WebProgressPhase.CREATING_STRM: 25.0,
            WebProgressPhase.CLEANUP: 5.0,
        }
        
        total_weight = sum(phase_weights.values())
        weighted_progress = 0.0
        
        for phase, progress in self._web_phases.items():
            weight = phase_weights.get(phase, 1.0)
            if progress.completed_at:
                weighted_progress += weight
            elif progress.started_at:
                weighted_progress += (progress.progress / 100.0) * weight
        
        return min(100.0, (weighted_progress / total_weight) * 100.0)
    
    def register_callback(self, callback: Callable[[Any], None]):
        """Register a callback for progress updates."""
        with self._lock:
            self._callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notify registered callbacks."""
        callbacks_to_notify = []
        with self._lock:
            callbacks_to_notify = self._callbacks.copy()
        
        for callback in callbacks_to_notify:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in callback: {e}")
    
    def _broadcast_update(self):
        """Broadcast progress update to WebSocket clients."""
        progress_data = self.get_web_progress()
        
        # Notify callbacks
        self._notify_callbacks()
        
        # Broadcast to WebSocket clients (non-blocking)
        for client_queue in self._websocket_clients[:]:
            try:
                # Use asyncio.run_coroutine_threadsafe for thread safety
                loop = asyncio.get_event_loop()
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        client_queue.put(progress_data), 
                        loop
                    )
            except Exception as e:
                logger.debug(f"Error broadcasting to WebSocket client: {e}")
                # Remove dead client
                if client_queue in self._websocket_clients:
                    self._websocket_clients.remove(client_queue)
    
    def add_websocket_client(self, client_queue: asyncio.Queue):
        """Add a WebSocket client for progress updates."""
        with self._lock:
            self._websocket_clients.append(client_queue)
    
    def remove_websocket_client(self, client_queue: asyncio.Queue):
        """Remove a WebSocket client."""
        with self._lock:
            if client_queue in self._websocket_clients:
                self._websocket_clients.remove(client_queue)
    
    def reset(self):
        """Reset progress tracker."""
        with self._lock:
            self._current_web_phase = WebProgressPhase.IDLE
            self._stats = ProcessingStats()
            self._start_time = time.time()
            
            for phase in self._web_phases.values():
                phase.progress = 0.0
                phase.processed = 0
                phase.total = 0
                phase.current_item = ""
                phase.items_per_second = 0.0
                phase.elapsed_time = 0.0
                phase.started_at = None
                phase.completed_at = None
                phase.error_message = None
            
            self._broadcast_update()
    
    def shutdown(self):
        """Shutdown the progress tracker."""
        self._shutdown_flag.set()
        with self._lock:
            self._websocket_clients.clear()
