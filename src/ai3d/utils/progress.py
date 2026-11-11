"""Progress tracking with ETA for AI3DModeller operations."""
import time
import sys
from typing import Optional, Dict
from tqdm import tqdm


class ProgressTracker:
    """Track progress with percentage, ETA, and elapsed time."""
    
    def __init__(self, total_steps: int, description: str = "Processing"):
        """
        Initialize progress tracker.
        
        Args:
            total_steps: Total number of steps
            description: Description of the operation
        """
        self.total_steps = total_steps
        self.description = description
        self.current_step = 0
        self.start_time = time.time()
        self.step_times = {}
        self.pbar = None
        
    def start(self):
        """Start the progress bar."""
        self.pbar = tqdm(
            total=self.total_steps,
            desc=self.description,
            unit="step",
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
            ncols=100,
            file=sys.stdout
        )
        self.start_time = time.time()
        
    def update(self, step_name: str, increment: int = 1):
        """
        Update progress with a named step.
        
        Args:
            step_name: Name of the current step
            increment: Number of steps to increment
        """
        if self.pbar:
            self.pbar.set_description(f"{self.description}: {step_name}")
            self.pbar.update(increment)
            self.current_step += increment
            self.step_times[step_name] = time.time()
    
    def set_progress(self, progress: float, step_name: str):
        """
        Set progress directly as a percentage.
        
        Args:
            progress: Progress as float 0.0-1.0
            step_name: Name of current step
        """
        if self.pbar:
            target_step = int(progress * self.total_steps)
            diff = target_step - self.current_step
            if diff > 0:
                self.update(step_name, diff)
    
    def finish(self):
        """Complete the progress bar."""
        if self.pbar:
            self.pbar.n = self.total_steps
            self.pbar.refresh()
            self.pbar.close()
            
            # Print summary
            elapsed = time.time() - self.start_time
            print(f"\n✓ {self.description} complete in {elapsed:.1f}s")
    
    def get_elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time
    
    def get_eta(self) -> float:
        """Estimate time remaining in seconds."""
        if self.current_step == 0:
            return 0
        elapsed = self.get_elapsed()
        rate = self.current_step / elapsed
        remaining_steps = self.total_steps - self.current_step
        return remaining_steps / rate if rate > 0 else 0


class TripoSRProgress:
    """Progress tracker for TripoSR with overall and per-stage bars."""
    
    # Estimated time for each stage (in seconds, approximate)
    STAGE_ESTIMATES = {
        'init': 15,
        'preprocess': 2,
        'inference': 30,
        'extract': 50,
        'texture': 80,
        'export': 5
    }
    
    STAGE_NAMES = {
        'init': 'Loading Model',
        'preprocess': 'Preprocessing',
        'inference': '3D Reconstruction',
        'extract': 'Mesh Extraction',
        'texture': 'Texture Baking',
        'export': 'Exporting'
    }
    
    def __init__(self, use_individual_bars: bool = True):
        self.use_individual_bars = use_individual_bars
        self.current_stage = None
        self.stage_start = None
        self.stage_pbar = None
        self.overall_pbar = None
        self.completed_stages = 0
        self.total_stages = len(self.STAGE_ESTIMATES)
        # fallback tracker for single-bar mode
        total_time = sum(self.STAGE_ESTIMATES.values())
        self.tracker = ProgressTracker(total_time, "TripoSR Generation")
        
    def start(self):
        """Start tracking."""
        if self.use_individual_bars:
            print("\n" + "="*60)
            print("  TripoSR High-Quality 3D Generation")
            print("="*60 + "\n")
            self.overall_pbar = tqdm(
                total=self.total_stages,
                desc="Overall",
                unit="stage",
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} stages [{elapsed}<{remaining}]',
                position=0,
                leave=True,
                file=sys.stdout
            )
        else:
            self.tracker.start()
        
    def start_stage(self, stage: str):
        """Start a new stage with its own bar."""
        # Close previous stage pbar if any
        if self.stage_pbar:
            self.stage_pbar.n = 100
            self.stage_pbar.refresh()
            self.stage_pbar.close()
            self.stage_pbar = None
        
        self.current_stage = stage
        self.stage_start = time.time()
        stage_name = self.STAGE_NAMES.get(stage, stage)
        estimate = self.STAGE_ESTIMATES.get(stage, 10)
        
        if self.use_individual_bars:
            self.stage_pbar = tqdm(
                total=100,
                desc=f"{stage_name}",
                unit="%",
                bar_format='{l_bar}{bar}| {n_fmt}% [ETA: {remaining}]',
                position=1,
                leave=False,
                file=sys.stdout
            )
        else:
            print(f"\n{stage_name} (est. {estimate}s)...")
        
    def update_stage(self, stage: str, progress: float = 1.0):
        """Update progress within a stage (0.0-1.0)."""
        if stage not in self.STAGE_ESTIMATES:
            return
        
        if self.use_individual_bars:
            if self.stage_pbar and stage == self.current_stage:
                target = max(0, min(100, int(progress * 100)))
                # Always update, even if going backwards (for real-time tracking)
                self.stage_pbar.n = target
                self.stage_pbar.refresh()
        else:
            # Single-bar mode: map stage progress to total
            cumulative = 0
            for s in ['init', 'preprocess', 'inference', 'extract', 'texture', 'export']:
                if s == stage:
                    cumulative += self.STAGE_ESTIMATES[s] * progress
                    break
                else:
                    cumulative += self.STAGE_ESTIMATES[s]
            stage_name = self.STAGE_NAMES.get(stage, stage)
            self.tracker.set_progress(cumulative / sum(self.STAGE_ESTIMATES.values()), stage_name)
    
    def finish_stage(self, stage: str):
        """Mark current stage as complete and update overall bar."""
        if self.stage_start is not None:
            elapsed = time.time() - self.stage_start
            estimate = self.STAGE_ESTIMATES.get(stage, 0)
            
            if self.use_individual_bars:
                if self.stage_pbar:
                    self.stage_pbar.n = 100
                    self.stage_pbar.refresh()
                    self.stage_pbar.close()
                    self.stage_pbar = None
                self.completed_stages += 1
                if self.overall_pbar:
                    self.overall_pbar.update(1)
                # Print timing line
                diff = elapsed - estimate
                timing_info = f"{elapsed:.1f}s"
                if abs(diff) > 5:
                    timing_info += f" ({'faster' if diff < 0 else 'slower'} than expected)"
                tqdm.write(f"  ✓ {self.STAGE_NAMES.get(stage, stage)} completed in {timing_info}")
            else:
                if abs(elapsed - estimate) > 5:
                    print(f"  ({elapsed:.1f}s, {'faster' if elapsed < estimate else 'slower'} than expected)")
        
        self.update_stage(stage, 1.0)
        self.stage_start = None
        
    def finish(self, success: bool = True):
        """Complete tracking and close bars."""
        if self.stage_pbar:
            self.stage_pbar.close()
            self.stage_pbar = None
        if self.use_individual_bars:
            if self.overall_pbar:
                self.overall_pbar.n = self.total_stages
                self.overall_pbar.refresh()
                self.overall_pbar.close()
                self.overall_pbar = None
            # Summary line
            print("\n" + "="*60)
            print("  Generation Complete!" if success else "  Generation Failed")
            print("="*60 + "\n")
        else:
            self.tracker.finish()


class SimpleProgress:
    """Simple progress tracker for quick operations."""
    
    def __init__(self, steps: list, description: str = "Processing"):
        """
        Initialize with list of step names.
        
        Args:
            steps: List of step names
            description: Overall description
        """
        self.steps = steps
        self.current = 0
        self.tracker = ProgressTracker(len(steps), description)
        
    def start(self):
        """Start tracking."""
        self.tracker.start()
    
    def next_step(self):
        """Move to next step."""
        if self.current < len(self.steps):
            self.tracker.update(self.steps[self.current])
            self.current += 1
    
    def finish(self):
        """Complete tracking."""
        self.tracker.finish()


def format_time(seconds: float) -> str:
    """Format seconds as human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f"{hours}h {mins}m"
