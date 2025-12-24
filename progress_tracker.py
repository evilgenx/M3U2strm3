import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager
import logging
import signal
import sys

class ProgressPhase(Enum):
    SCANNING_LOCAL = "Scanning Local Media"
    PARSING_M3U = "Parsing M3U Playlist"
    FILTERING_TMDB = "TMDb Filtering"
    CREATING_STRM = "Creating STRM Files"
    CLEANUP = "Cleanup & Finalization"


@dataclass
class PhaseProgress:
    phase: ProgressPhase
    total: int = 0
    processed: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    items_per_second: float = 0.0
    current_item: str = ""
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    
    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
    
    @property
    def elapsed_time(self) -> float:
        if self.started_at is None:
            return 0.0
        end_time = self.completed_at or time.time()
        return end_time - self.started_at
    
    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 100.0 if self.is_complete else 0.0
        return min(100.0, (self.processed / self.total) * 100.0)


class VerbosityLevel(Enum):
    QUIET = "quiet"      # Only completion summary
    NORMAL = "normal"    # Phase progress + summary (default)
    VERBOSE = "verbose"  # Detailed logs + progress
    DEBUG = "debug"      # All logs + progress


@dataclass
class ProcessingStats:
    movies_found: int = 0
    movies_allowed: int = 0
    movies_excluded: int = 0
    tv_episodes_found: int = 0
    tv_episodes_allowed: int = 0
    tv_episodes_excluded: int = 0
    documentaries_found: int = 0
    documentaries_allowed: int = 0
    documentaries_excluded: int = 0
    strm_created: int = 0
    strm_skipped: int = 0
    strm_orphaned: int = 0
    errors: List[str] = field(default_factory=list)
    
    @property
    def total_found(self) -> int:
        return (self.movies_found + self.tv_episodes_found + self.documentaries_found)
    
    @property
    def total_allowed(self) -> int:
        return (self.movies_allowed + self.tv_episodes_allowed + self.documentaries_allowed)
    
    @property
    def total_excluded(self) -> int:
        return (self.movies_excluded + self.tv_episodes_excluded + self.documentaries_excluded)


class ProgressTracker:
    """Thread-safe progress tracking system for M3U2strm3 operations."""
    
    def __init__(self, verbosity: VerbosityLevel = VerbosityLevel.NORMAL):
        self.verbosity = verbosity
        self._lock = threading.RLock()  # Use RLock to prevent deadlocks from nested lock acquisition
        self._phases: Dict[ProgressPhase, PhaseProgress] = {}
        self._current_phase: Optional[ProgressPhase] = None
        self._stats = ProcessingStats()
        self._start_time = time.time()
        self._callbacks: List[Callable[[Any], None]] = []
        self._shutdown_flag = threading.Event()  # Flag to signal shutdown
        self._original_sigint_handler = None  # Store original SIGINT handler
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        try:
            self._original_sigint_handler = signal.signal(signal.SIGINT, self._handle_shutdown)
            logging.debug("Signal handlers installed for graceful shutdown")
        except ValueError:
            # Signal handlers can only be set from the main thread
            logging.debug("Cannot install signal handlers (not in main thread)")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logging.info("Shutdown signal received, initiating graceful shutdown...")
        self._shutdown_flag.set()
        
        # Restore original signal handler
        if self._original_sigint_handler and self._original_sigint_handler != signal.SIG_DFL:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
        
        # Force immediate exit after cleanup
        sys.exit(0)
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_flag.is_set()
    
    def shutdown(self):
        """Initiate graceful shutdown."""
        logging.info("Initiating graceful shutdown...")
        self._shutdown_flag.set()
    
    def cleanup(self):
        """Clean up resources and finalize progress tracking."""
        # Ensure shutdown flag is set
        self._shutdown_flag.set()
        
        # Restore original signal handler if it was set
        if self._original_sigint_handler and self._original_sigint_handler != signal.SIG_DFL:
            try:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
            except ValueError:
                pass  # Can only set signal handlers from main thread
        
        logging.debug("Progress tracker cleanup completed")
        
    def set_verbosity(self, verbosity: VerbosityLevel):
        """Change verbosity level during execution."""
        with self._lock:
            self.verbosity = verbosity
    
    def start_phase(self, phase: ProgressPhase, total_items: int = 0):
        """Start a new processing phase."""
        with self._lock:
            if phase not in self._phases:
                self._phases[phase] = PhaseProgress(phase=phase, total=total_items)
            progress = self._phases[phase]
            progress.started_at = time.time()
            progress.total = total_items
            progress.processed = 0
            progress.current_item = ""
            self._current_phase = phase
            
            if self.verbosity in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
                logging.info(f"Starting phase: {phase.value} (total: {total_items})")
    
    def update_phase(self, phase: ProgressPhase, processed: int, current_item: str = "", 
                    success: bool = True, skipped: bool = False):
        """Update progress for a specific phase."""
        with self._lock:
            if phase not in self._phases:
                return
                
            progress = self._phases[phase]
            progress.processed = processed
            progress.current_item = current_item[:100]  # Limit item name length
            
            if success:
                progress.success_count += 1
            elif not skipped:
                progress.failure_count += 1
                
            if skipped:
                progress.skipped_count += 1
            
            # Calculate items per second
            if progress.started_at:
                elapsed = time.time() - progress.started_at
                if elapsed > 0:
                    progress.items_per_second = processed / elapsed
            
            # Notify callbacks
            self._notify_callbacks()
    
    def batch_update_phase(self, phase: ProgressPhase, processed: int, current_item: str = "", 
                          success_count: int = 0, failure_count: int = 0, skipped_count: int = 0):
        """Batch update progress for better performance during high-frequency updates."""
        with self._lock:
            if phase not in self._phases:
                return
                
            progress = self._phases[phase]
            progress.processed = processed
            progress.current_item = current_item[:100] if current_item else progress.current_item
            progress.success_count += success_count
            progress.failure_count += failure_count
            progress.skipped_count += skipped_count
            
            # Calculate items per second
            if progress.started_at:
                elapsed = time.time() - progress.started_at
                if elapsed > 0:
                    progress.items_per_second = processed / elapsed
            
            # Notify callbacks (less frequent for batched updates)
            self._notify_callbacks()
    
    def complete_phase(self, phase: ProgressPhase):
        """Mark a phase as complete."""
        with self._lock:
            if phase in self._phases:
                self._phases[phase].completed_at = time.time()
                if self.verbosity in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
                    progress = self._phases[phase]
                    elapsed = progress.elapsed_time
                    logging.info(f"Completed phase: {phase.value} in {elapsed:.1f}s "
                               f"({progress.processed} items, {progress.items_per_second:.1f}/s)")
    
    def update_stats(self, **kwargs):
        """Update processing statistics."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._stats, key):
                    setattr(self._stats, key, getattr(self._stats, key) + value)
            self._notify_callbacks()
    
    def add_error(self, error_msg: str):
        """Add an error to the statistics."""
        with self._lock:
            self._stats.errors.append(error_msg)
    
    def get_phase_progress(self, phase: ProgressPhase) -> Optional[PhaseProgress]:
        """Get progress information for a specific phase."""
        with self._lock:
            return self._phases.get(phase)
    
    def get_current_phase(self) -> Optional[PhaseProgress]:
        """Get progress information for the current phase."""
        with self._lock:
            if self._current_phase:
                return self._phases.get(self._current_phase)
            return None
    
    def get_overall_progress(self) -> float:
        """Calculate overall progress across all phases."""
        with self._lock:
            if not self._phases:
                return 0.0
            
            total_weight = len(self._phases)
            progress_sum = sum(p.progress_percent for p in self._phases.values())
            return progress_sum / total_weight
    
    def get_stats(self) -> ProcessingStats:
        """Get current processing statistics."""
        with self._lock:
            return self._stats
    
    def get_elapsed_time(self) -> float:
        """Get total elapsed time since start."""
        try:
            with self._lock:
                return time.time() - self._start_time
        except Exception:
            # Fallback if lock is held by another thread
            return time.time() - self._start_time
    
    def register_callback(self, callback: Callable[[Any], None]):
        """Register a callback to be notified of progress updates."""
        with self._lock:
            self._callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notify all registered callbacks of progress updates."""
        # Use a short timeout to prevent callbacks from blocking indefinitely
        callbacks_to_notify = []
        with self._lock:
            callbacks_to_notify = self._callbacks.copy()
        
        for callback in callbacks_to_notify:
            try:
                # Check if shutdown is requested before executing callback
                if self._shutdown_flag.is_set():
                    break
                    
                # Execute callback with timeout protection
                import threading
                result = [None]
                exception = [None]
                
                def callback_wrapper():
                    try:
                        result[0] = callback(self)
                    except Exception as e:
                        exception[0] = e
                
                thread = threading.Thread(target=callback_wrapper)
                thread.daemon = True
                thread.start()
                thread.join(timeout=1.0)  # 1 second timeout for callback execution
                
                if exception[0]:
                    logging.debug(f"Callback execution failed: {exception[0]}")
                elif thread.is_alive():
                    logging.debug("Callback execution timed out")
                    
            except Exception as e:
                logging.debug(f"Error in callback notification: {e}")
                # Don't let callback errors break progress tracking
                pass
    
    @contextmanager
    def phase_context(self, phase: ProgressPhase, total_items: int = 0):
        """Context manager for automatic phase tracking."""
        self.start_phase(phase, total_items)
        try:
            yield self
        finally:
            self.complete_phase(phase)
    
    def get_summary(self) -> str:
        """Generate a user-friendly summary of all operations."""
        with self._lock:
            stats = self._stats
            total_time = self.get_elapsed_time()
            
            summary = [
                "✅ Processing Complete!",
                "",
                "📊 Statistics:",
                f"   • Movies: {stats.movies_found} found, {stats.movies_allowed} allowed, {stats.movies_excluded} excluded",
                f"   • TV Shows: {stats.tv_episodes_found} episodes, {stats.tv_episodes_allowed} allowed, {stats.tv_episodes_excluded} excluded",
                f"   • Documentaries: {stats.documentaries_found} found, {stats.documentaries_allowed} allowed, {stats.documentaries_excluded} excluded",
                "",
                "📁 STRM Files:",
                f"   • Created: {stats.strm_created}",
                f"   • Skipped: {stats.strm_skipped}",
                f"   • Orphaned: {stats.strm_orphaned}",
                "",
                f"⏱️  Runtime: {total_time:.1f} seconds"
            ]
            
            if stats.errors:
                summary.extend([
                    "",
                    "⚠️  Errors:",
                    *[f"   • {error}" for error in stats.errors[-5:]]  # Show last 5 errors
                ])
            
            return "\n".join(summary)
