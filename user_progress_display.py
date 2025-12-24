import sys
import time
from typing import Optional, Dict, Any
from tqdm import tqdm
from progress_tracker import ProgressTracker, ProgressPhase, VerbosityLevel, PhaseProgress


class UserProgressDisplay:
    """User-friendly progress display using tqdm with real-time updates."""
    
    def __init__(self, tracker: ProgressTracker):
        self.tracker = tracker
        self._tqdm_bar: Optional[tqdm] = None
        self._current_phase_bar: Optional[tqdm] = None
        self._last_update_time = 0
        self._update_interval = 0.5  # Update display every 500ms
        
        # Register callback to receive progress updates
        self.tracker.register_callback(self._on_progress_update)
    
    def _on_progress_update(self, tracker: ProgressTracker):
        """Callback triggered when progress updates occur."""
        # Check if shutdown has been requested
        if self.tracker.is_shutdown_requested():
            return
            
        if self.tracker.verbosity not in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        current_time = time.time()
        if current_time - self._last_update_time < self._update_interval:
            return
            
        self._last_update_time = current_time
        self._update_display()
    
    def _update_display(self):
        """Update the progress display with current information."""
        if self.tracker.verbosity == VerbosityLevel.QUIET:
            return
            
        current_phase = self.tracker.get_current_phase()
        if current_phase is None:
            return
        
        # Update phase-specific progress bar
        if self._current_phase_bar is None or self._current_phase_bar.desc != current_phase.phase.value:
            if self._current_phase_bar:
                self._current_phase_bar.close()
            self._current_phase_bar = tqdm(
                total=current_phase.total,
                desc=f"Processing: {current_phase.phase.value}",
                unit="items",
                leave=False,
                dynamic_ncols=True,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}'
            )
        
        # Update progress
        self._current_phase_bar.n = current_phase.processed
        self._current_phase_bar.set_postfix({
            'Current': current_phase.current_item[:50] + '...' if len(current_phase.current_item) > 50 else current_phase.current_item,
            'Speed': f"{current_phase.items_per_second:.1f}/s"
        })
        self._current_phase_bar.refresh()
    
    def show_phase_summary(self, phase: ProgressPhase):
        """Show a summary when a phase completes."""
        if self.tracker.verbosity not in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        elapsed = phase.elapsed_time
        print(f"\n✅ {phase.phase.value} completed in {elapsed:.1f}s")
        print(f"   • Processed: {phase.processed:,} items")
        print(f"   • Speed: {phase.items_per_second:.1f} items/sec")
        if phase.failure_count > 0:
            print(f"   • Failures: {phase.failure_count}")
        if phase.skipped_count > 0:
            print(f"   • Skipped: {phase.skipped_count}")
        print()
    
    def show_overall_progress(self):
        """Show overall progress across all phases."""
        if self.tracker.verbosity not in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        overall_progress = self.tracker.get_overall_progress()
        current_phase = self.tracker.get_current_phase()
        
        if current_phase:
            print(f"\n📊 Overall Progress: {overall_progress:.1f}%")
            print(f"   Current: {current_phase.phase.value}")
            print(f"   Phase Progress: {current_phase.processed}/{current_phase.total} ({current_phase.progress_percent:.1f}%)")
            print(f"   Elapsed Time: {self.tracker.get_elapsed_time():.1f}s")
            print()
    
    def show_statistics(self):
        """Show current processing statistics."""
        if self.tracker.verbosity not in [VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        stats = self.tracker.get_stats()
        print("\n📈 Current Statistics:")
        print(f"   Movies: {stats.movies_found} found, {stats.movies_allowed} allowed")
        print(f"   TV Episodes: {stats.tv_episodes_found} found, {stats.tv_episodes_allowed} allowed")
        print(f"   Documentaries: {stats.documentaries_found} found, {stats.documentaries_allowed} allowed")
        print(f"   STRM Files: {stats.strm_created} created, {stats.strm_skipped} skipped")
        if stats.errors:
            print(f"   Errors: {len(stats.errors)}")
        print()
    
    def show_final_summary(self):
        """Show the final completion summary."""
        if self.tracker.verbosity == VerbosityLevel.QUIET:
            # For quiet mode, just show the essential summary
            stats = self.tracker.get_stats()
            print(f"✅ Processing Complete! Created {stats.strm_created} STRM files in {self.tracker.get_elapsed_time():.1f}s")
            return
        
        # Show the detailed summary
        summary = self.tracker.get_summary()
        print(f"\n{summary}")
    
    def cleanup(self):
        """Clean up progress display resources."""
        if self._current_phase_bar:
            self._current_phase_bar.close()
            self._current_phase_bar = None
        if self._tqdm_bar:
            self._tqdm_bar.close()
            self._tqdm_bar = None
    
    def pause_display(self):
        """Temporarily pause progress display updates."""
        if self._current_phase_bar:
            self._current_phase_bar.close()
            self._current_phase_bar = None
    
    def resume_display(self):
        """Resume progress display updates."""
        # Display will automatically resume on next update
        pass


class SimpleProgressDisplay:
    """Simple text-based progress display for basic terminals."""
    
    def __init__(self, tracker: ProgressTracker):
        self.tracker = tracker
        self._last_phase = None
        self._last_processed = 0
        self._last_time = time.time()
        
        self.tracker.register_callback(self._on_progress_update)
    
    def _on_progress_update(self, tracker: ProgressTracker):
        """Simple progress update for basic terminals."""
        if self.tracker.verbosity not in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        current_phase = self.tracker.get_current_phase()
        if current_phase is None:
            return
        
        # Only update every second to avoid spam
        current_time = time.time()
        if current_time - self._last_time < 1.0:
            return
        
        self._last_time = current_time
        
        # Clear previous line and show current progress
        if current_phase.processed > self._last_processed or current_phase.phase != self._last_phase:
            self._last_processed = current_phase.processed
            self._last_phase = current_phase.phase
            
            progress_pct = current_phase.progress_percent
            bar_length = 20
            filled = int(bar_length * progress_pct / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            current_item = current_phase.current_item[:30] + '...' if len(current_phase.current_item) > 30 else current_phase.current_item
            
            sys.stdout.write(f'\r{current_phase.phase.value}: [{bar}] {progress_pct:3.0f}% | {current_phase.processed}/{current_phase.total} | {current_item}')
            sys.stdout.flush()
    
    def show_phase_complete(self, phase: ProgressPhase):
        """Show phase completion message."""
        if self.tracker.verbosity not in [VerbosityLevel.NORMAL, VerbosityLevel.VERBOSE, VerbosityLevel.DEBUG]:
            return
            
        print(f"\n✅ {phase.phase.value} completed ({phase.processed} items in {phase.elapsed_time:.1f}s)")
    
    def show_final_summary(self):
        """Show final summary."""
        if self.tracker.verbosity == VerbosityLevel.QUIET:
            stats = self.tracker.get_stats()
            print(f"\n✅ Processing Complete! Created {stats.strm_created} STRM files in {self.tracker.get_elapsed_time():.1f}s")
        else:
            print(f"\n{self.tracker.get_summary()}")
    
    def cleanup(self):
        """Clean up display."""
        print()  # New line after progress
