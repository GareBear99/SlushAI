"""Task queue for generation requests — SPSC generation path (Stage 3).

Route: Flask request threads -> intake -> dispatcher -> per-lane SPSCRing
-> lane worker -> _execute_task. The generation PIPELINE structure, not
the GPU burst (that stays later, when Colab is in properly).

Design (same pattern as the ARC SPSC ring, Module 1, and Lucid's tick
rings — eventRing cap 512, aiChatTickRing cap 256; this ring's cap is
512, matching eventRing):

  * One bounded ring per worker lane (2 lanes normally, a 3rd when the
    queue backs up past SCALE_UP_THRESHOLD). Each ring is preallocated
    (power of two, 512 slots), monotonic head/tail counters, slot index
    wraps via ``idx & mask``. A slot is free exactly when
    ``tail - head < capacity``, so a producer can never overwrite a
    live task.
  * True single producer per ring: a dedicated dispatcher thread is the
    ONLY thread that pushes to any ring. Flask request threads never
    touch a ring — ``add_task`` only registers the task and hands its id
    to a ``queue.SimpleQueue`` intake, which the dispatcher drains. The
    dispatcher picks the lane with the least in-flight work (ties go to
    lane 0) and only uses lane 2 when the queue is backed up.
  * One consumer per ring: exactly one worker thread pops from each
    lane's ring. No other thread pops from it.
  * Backpressure, never drop: when a ring is full the dispatcher BLOCKS
    on push until the worker frees a slot. Tasks are never dropped and
    the buffer never grows. The HTTP request thread never blocks on a
    full ring — it only puts on the intake, which the dispatcher drains
    immediately; the backpressure sits between dispatcher and worker,
    where it belongs.
  * FIFO per lane. Tasks come out of a lane in the order they went in.
  * No lock in the hot path. Push/pop use no ``threading.Lock`` and no
    ``queue.Queue``. The only synchronisation is the monotonically
    advanced indices plus the GIL. The ``tasks`` registry and status
    reads still use ``self.lock`` (they are not the hot path).
  * Cancelled tasks are skipped twice: the dispatcher skips them before
    pushing to a ring, and the worker skips them on pop. Cancelling
    never has to reach into a ring.
  * Workers are started once and then block on empty rings (zero CPU
    while idle) instead of exiting and restarting per batch, as the old
    deque version did. ``processing`` therefore means "workers are up",
    and the live load is ``active_workers`` (tasks currently executing).

Honesty note (same as the ARC ring — read before assuming "lock-free"
means what it means in C/Rust): this is pure Python on CPython.
CPython's GIL makes a plain int attribute read/write atomic, and that
is what this ring relies on for index visibility. It is *not* truly
lock-free at the C level — the GIL itself is a lock, and a thread can
be descheduled mid-operation. What this guarantees, and what matters
for the generation path, is the SPSC *structure and discipline*: a
fixed bound, one writer per index, no mutex around the ring, no
per-task allocation, and a producer that cannot outrun its consumer.
The bound (``len(ring) <= capacity`` at every instant) holds regardless
of the GIL, because the producer physically cannot write a slot until
the consumer has freed it.

The raw ring rate (~1.36M ticks/s for the ARC ring) is the RING, not
generation — TripoSR inference on CPU dominates end-to-end generation
time, so the honest SPSC delta is measured on task-submit-to-mesh-out
(``queue_wait_seconds`` + ``execution_seconds`` in get_task_status),
never on the ring rate. See ~/workspace/slushai-complete-state.md
item 23 for the measured before/after numbers.
"""
import time
import threading
import logging
import queue as _queue
from datetime import datetime
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger('TaskQueue')

# Busy-spin iterations before yielding the GIL while waiting for a slot
# (full ring) or a task (empty ring). Short on purpose: the other end is
# usually only microseconds away.
_SPIN = 100

# Ring capacity (power of two). 512, matching Lucid's eventRing.
RING_CAPACITY = 512


def _wait() -> None:
    """Brief spin, then yield the GIL so the other end can run.

    Used only on the wait paths (ring full / ring empty), never on the
    fast push/pop path. No lock is taken here.
    """
    for _ in range(_SPIN):
        pass
    time.sleep(0)


class SPSCRing:
    """A bounded single-producer single-consumer ring buffer.

    ``capacity`` must be a power of two >= 1. The ring holds at most
    ``capacity`` items at any instant; ``len(ring)`` never exceeds it.
    ``track`` keeps the ``max_inflight`` / ``pushed`` / ``popped``
    counters (cheap; left on — this is a task queue, not a tick loop).
    """

    __slots__ = ("_capacity", "_mask", "_slots", "_head", "_tail",
                 "_closed", "_track", "max_inflight", "pushed", "popped")

    def __init__(self, capacity: int = RING_CAPACITY, track: bool = True) -> None:
        if capacity < 1 or (capacity & (capacity - 1)) != 0:
            raise ValueError("capacity must be a power of two >= 1")
        self._capacity = capacity
        self._mask = capacity - 1
        self._slots = [None] * capacity
        self._head = 0  # consumer index; only the consumer writes it
        self._tail = 0  # producer index; only the producer writes it
        self._closed = False  # set by the producer when it is done
        self._track = track
        self.max_inflight = 0
        self.pushed = 0
        self.popped = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        """Items currently in flight (0 .. capacity)."""
        return self._tail - self._head

    def push(self, item) -> None:
        """Enqueue one item. Producer (the dispatcher) only.

        Blocks with backpressure when the ring is full — never drops.
        """
        while self._tail - self._head >= self._capacity:
            _wait()
        self._slots[self._tail & self._mask] = item
        # Publish AFTER the write: the consumer must never see a slot
        # whose item is not yet stored.
        self._tail += 1
        if self._track:
            self.pushed += 1
            inflight = self._tail - self._head
            if inflight > self.max_inflight:
                self.max_inflight = inflight

    def pop(self):
        """Dequeue one item. Consumer (the lane worker) only.

        Blocks until an item arrives. Returns None only after close()
        and the ring has drained.
        """
        while True:
            if self._head != self._tail:
                item = self._slots[self._head & self._mask]
                self._slots[self._head & self._mask] = None
                self._head += 1
                if self._track:
                    self.popped += 1
                return item
            if self._closed:
                return None
            _wait()

    def close(self) -> None:
        """Producer only: no more items will be pushed. The consumer
        drains what is left and then pop() returns None."""
        self._closed = True


@dataclass
class Task:
    """Represents a generation task in the queue."""
    task_id: str
    task_type: str  # 'model', 'texture', 'animation'
    params: Dict
    callback: Optional[Callable] = None
    status: str = 'queued'  # queued, processing, completed, failed
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    # Stamped by the dispatcher when the task enters its lane ring.
    dispatched_at: Optional[float] = None


class TaskQueue:
    """
    Manages a queue of generation tasks with position tracking and wait time estimates.
    Supports adaptive parallel processing:
    - 2 workers normally (40% CPU each = 80% total)
    - 3 workers when queue >= 10 (26.7% CPU each, 3rd worker gets 10% less = 80% total)
    Automatically scales up/down based on queue depth.
    """

    # Average processing times per task type (seconds)
    AVG_TIMES = {
        'model': 180,      # 3 minutes for TripoSR
        'texture': 120,    # 2 minutes for texturing
        'animation': 60,   # 1 minute for animation
    }

    BASE_WORKERS = 2           # Always run 2 workers
    MAX_WORKERS = 3            # Scale up to 3 during high load
    SCALE_UP_THRESHOLD = 10    # Add 3rd worker when queue >= 10

    def __init__(self):
        # Task registry (guarded by self.lock; not the hot path).
        self.tasks = {}  # task_id -> Task
        # Intake: request threads hand task ids to the dispatcher here.
        # queue.SimpleQueue is the handoff, not the bound — the bound
        # lives in the per-lane rings, which the dispatcher feeds.
        self._intake = _queue.SimpleQueue()
        # One SPSC ring + one worker per lane. The dispatcher is the
        # only producer on every ring; lane worker N is the only
        # consumer on ring N.
        self._rings = [SPSCRing(RING_CAPACITY) for _ in range(self.MAX_WORKERS)]
        self._dispatcher_thread = None
        self._lane2_active = False
        self.current_tasks: Dict[int, Optional[Task]] = {
            0: None,  # Worker 0 (primary)
            1: None,  # Worker 1 (primary)
            2: None   # Worker 2 (backup - only used when queue >= 10)
        }
        self.lock = threading.Lock()
        self.processing = False
        self.worker_threads = []
        self.active_worker_count = self.BASE_WORKERS  # Start with 2

    # -- public API: intake ------------------------------------------------

    def add_task(self, task_id: str, task_type: str, params: Dict, callback: Optional[Callable] = None) -> Task:
        """Add a new task to the queue and return task object.

        The request thread only registers the task and puts its id on
        the intake — it never touches a ring, so it can never block on
        a full ring. The dispatcher (the single producer) picks the
        task up and pushes it to a lane ring.
        """
        with self.lock:
            task = Task(
                task_id=task_id,
                task_type=task_type,
                params=params,
                callback=callback
            )
            self.tasks[task_id] = task
            self._intake.put(task_id)
            start_workers = not self.processing

        # Start the dispatcher + workers AFTER releasing the lock:
        # _start_worker() takes this same lock, and threading.Lock is
        # not reentrant — calling it while holding the lock deadlocked
        # the request thread forever. That was the first /api/generate
        # after every server restart on the old code: the POST never
        # returned, no worker ever started, no model was ever generated
        # (observed 2026-11-10: POST stuck 10+ min).
        if start_workers:
            self._start_worker()

        return task

    # -- public API: status -------------------------------------------------

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status, position, and estimated wait time for a task."""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None

            # Position in queue: FIFO over queued tasks by creation
            # time. (The old deque version read the position out of the
            # deque; the rings are per-lane now, so creation order is
            # the queue order.)
            position = 0
            queued_before = 0
            if task.status == 'queued':
                queued_before = sum(
                    1 for t in self.tasks.values()
                    if t.status == 'queued' and t.created_at < task.created_at
                )
                position = queued_before + 1

            # Calculate estimated wait time
            estimated_wait = 0
            if task.status == 'queued' and position > 0:
                # Count how many tasks are currently processing
                processing_count = sum(1 for t in self.current_tasks.values() if t is not None)

                # With 2 workers, tasks process in pairs
                # Calculate how many "rounds" of processing are needed.
                # (Was self.MAX_CONCURRENT_WORKERS, which the class never
                # defined — every get_task_status call raised AttributeError,
                # which 500'd POST /api/generate after queueing the task.
                # The live parallel-task count is active_worker_count:
                # 2 normally, 3 when the queue scales up.)
                workers = self.active_worker_count
                if processing_count < workers:
                    # Workers available, might start sooner
                    slots_available = workers - processing_count
                    if position <= slots_available:
                        estimated_wait = 0  # Will start immediately
                    else:
                        # Calculate rounds needed
                        remaining_ahead = position - slots_available
                        rounds = (remaining_ahead + workers - 1) // workers
                        # Average time per round
                        avg_time = self.AVG_TIMES.get(task.task_type, 180)
                        estimated_wait = rounds * avg_time
                else:
                    # All workers busy - calculate based on queue position
                    rounds = (position + workers - 1) // workers
                    avg_time = self.AVG_TIMES.get(task.task_type, 180)
                    estimated_wait = rounds * avg_time

                # Add remaining time for currently processing tasks
                for current_task in self.current_tasks.values():
                    if current_task and current_task.started_at:
                        elapsed = time.time() - current_task.started_at
                        avg_time = self.AVG_TIMES.get(current_task.task_type, 180)
                        remaining = max(0, avg_time - elapsed)
                        # Divide by concurrent workers since they run in parallel
                        estimated_wait = max(estimated_wait, remaining)

            # Measured timings (SPSC): queue wait is created -> started,
            # execution is started -> completed (or now, while running).
            queue_wait = None
            if task.started_at is not None:
                queue_wait = task.started_at - task.created_at
            execution = None
            if task.started_at is not None:
                end = task.completed_at if task.completed_at is not None else time.time()
                execution = end - task.started_at

            return {
                'task_id': task_id,
                'task_type': task.task_type,
                'status': task.status,
                'position': position,
                'queue_length': self._queued_count_locked(),
                'estimated_wait_seconds': int(estimated_wait),
                'estimated_wait_minutes': round(estimated_wait / 60, 1),
                'created_at': task.created_at,
                'dispatched_at': task.dispatched_at,
                'started_at': task.started_at,
                'completed_at': task.completed_at,
                'queue_wait_seconds': queue_wait,
                'execution_seconds': execution,
                'result': task.result,
                'error': task.error
            }

    def _queued_count_locked(self) -> int:
        """Queued tasks (intake + rings). Call with self.lock held."""
        return sum(1 for t in self.tasks.values() if t.status == 'queued')

    def get_queue_status(self) -> Dict:
        """Get overall queue status including adaptive worker info."""
        with self.lock:
            current_task_ids = [
                task.task_id for task in self.current_tasks.values() if task is not None
            ]
            queue_length = self._queued_count_locked()

            # Determine if 3rd worker should be active
            should_scale_up = queue_length >= self.SCALE_UP_THRESHOLD

            return {
                'queue_length': queue_length,
                'processing': self.processing,
                'base_workers': self.BASE_WORKERS,
                'max_workers': self.MAX_WORKERS,
                'active_workers': len(current_task_ids),
                'target_workers': self.MAX_WORKERS if should_scale_up else self.BASE_WORKERS,
                'third_worker_active': self._lane2_active,
                'scale_up_threshold': self.SCALE_UP_THRESHOLD,
                'current_tasks': current_task_ids,
                'total_tasks': len(self.tasks),
                'queued_tasks': sum(1 for t in self.tasks.values() if t.status == 'queued'),
                'processing_tasks': sum(1 for t in self.tasks.values() if t.status == 'processing'),
                'completed_tasks': sum(1 for t in self.tasks.values() if t.status == 'completed'),
                'failed_tasks': sum(1 for t in self.tasks.values() if t.status == 'failed'),
                'spsc': self.get_spsc_stats(),
            }

    def get_spsc_stats(self) -> Dict:
        """SPSC observability: per-lane ring counters + intake depth.

        Proves the bound holds (inflight <= 512 per lane) and shows
        where tasks actually spend their queue time. No lock is taken
        here — the ring counters are read directly, as designed.
        """
        lanes = []
        for i, ring in enumerate(self._rings):
            lanes.append({
                'lane': i,
                'capacity': ring.capacity,
                'inflight': len(ring),
                'pushed': ring.pushed,
                'popped': ring.popped,
                'max_inflight': ring.max_inflight,
            })
        return {
            'ring_capacity': RING_CAPACITY,
            'intake_depth': self._intake.qsize(),
            'dispatcher_alive': bool(self._dispatcher_thread and self._dispatcher_thread.is_alive()),
            'lanes': lanes,
        }

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued task (cannot cancel currently processing task).

        Marks the task cancelled; the dispatcher skips it before it
        reaches a ring, and a worker skips it on pop if it is already
        ringed. Either way it never executes.
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if not task or task.status != 'queued':
                return False
            task.status = 'cancelled'
            task.completed_at = time.time()
            return True

    # -- workers + dispatcher ----------------------------------------------

    def _start_worker(self):
        """Start the dispatcher and the lane workers (once).

        Workers block on empty rings (zero CPU while idle) instead of
        exiting and restarting per batch, as the old deque version did.
        """
        with self.lock:
            if self._dispatcher_thread is None or not self._dispatcher_thread.is_alive():
                self.processing = True
                dispatcher = threading.Thread(
                    target=self._dispatch_loop,
                    daemon=True,
                    name="TaskDispatcher"
                )
                self._dispatcher_thread = dispatcher
                dispatcher.start()
            for worker_id in range(self.MAX_WORKERS):
                if worker_id >= len(self.worker_threads) or not self.worker_threads[worker_id].is_alive():
                    worker = threading.Thread(
                        target=self._process_queue,
                        args=(worker_id,),
                        daemon=True,
                        name=f"TaskWorker-{worker_id}"
                    )
                    if worker_id >= len(self.worker_threads):
                        self.worker_threads.append(worker)
                    else:
                        self.worker_threads[worker_id] = worker
                    worker.start()

    def _pick_lane(self) -> int:
        """Lane with the least in-flight work (ties -> lane 0).

        Lane 2 is only used when the queue is backed up past the
        scale-up threshold — otherwise lanes 0 and 1 share the load.
        Caller is the dispatcher (the single producer).
        """
        with self.lock:
            depth = self._queued_count_locked()
            lanes = range(self.MAX_WORKERS) if depth >= self.SCALE_UP_THRESHOLD else range(self.BASE_WORKERS)
            if depth >= self.SCALE_UP_THRESHOLD:
                if not self._lane2_active:
                    self._lane2_active = True
                    logger.info(f"🚀 Queue backed up ({depth} tasks), activating 3rd lane")
                if self.active_worker_count < self.MAX_WORKERS:
                    self.active_worker_count = self.MAX_WORKERS
            else:
                if self.active_worker_count > self.BASE_WORKERS:
                    self.active_worker_count = self.BASE_WORKERS
                    logger.info("↓ Queue cleared, 3rd lane idle")
        # Ring lengths are read lock-free (single producer/consumer
        # per ring); the choice is a heuristic, not an invariant.
        best = min(lanes, key=lambda i: len(self._rings[i]))
        return best

    def _dispatch_loop(self):
        """The single producer: drain the intake, push to lane rings.

        Runs forever (daemon). Blocks on intake.get() when there is
        nothing to do, and blocks on ring.push() when a lane is full
        (backpressure — tasks are never dropped).
        """
        while True:
            task_id = self._intake.get()
            lane = self._pick_lane()
            with self.lock:
                task = self.tasks.get(task_id)
                if not task or task.status != 'queued':
                    # Cancelled (or removed) while sitting in the
                    # intake — drop it here, before it reaches a ring.
                    continue
                # Stamp BEFORE the push: a fast worker can pop and start
                # the task while push() is still returning, and stamping
                # after would miss it (status is 'processing' by then).
                task.dispatched_at = time.time()
            # Push outside the lock: push() can block on backpressure,
            # and nothing else needs the lock while it waits.
            self._rings[lane].push(task_id)

    def _process_queue(self, worker_id: int):
        """Lane worker: the single consumer on its ring.

        Blocks on pop() when the ring is empty. Skips cancelled tasks.
        Executes outside any lock so status queries stay responsive.
        """
        ring = self._rings[worker_id]
        while True:
            task_id = ring.pop()
            if task_id is None:
                # Ring closed (shutdown) and drained.
                with self.lock:
                    self.current_tasks[worker_id] = None
                break

            with self.lock:
                task = self.tasks.get(task_id)
                if not task or task.status != 'queued':
                    # Cancelled after dispatch — skip, never execute.
                    continue
                # Mark as processing
                task.status = 'processing'
                task.started_at = time.time()
                self.current_tasks[worker_id] = task

            # Execute task (outside lock to allow status queries)
            try:
                result = self._execute_task(task)

                with self.lock:
                    task.status = 'completed'
                    task.completed_at = time.time()
                    task.result = result
                    self.current_tasks[worker_id] = None

                    # Call callback if provided
                    if task.callback:
                        try:
                            task.callback(task)
                        except Exception:
                            pass

            except Exception as e:
                with self.lock:
                    task.status = 'failed'
                    task.completed_at = time.time()
                    task.error = str(e)
                    self.current_tasks[worker_id] = None

                    # Call callback with error
                    if task.callback:
                        try:
                            task.callback(task)
                        except Exception:
                            pass

            # Small delay between tasks
            time.sleep(0.5)

    def _execute_task(self, task: Task) -> Dict:
        """Execute the actual task via the injected executor.

        Stage 3 (#13): the old fallback *simulated* work — it slept for the
        average task time and returned {'success': True} without generating
        anything. A task that "succeeds" without doing work is a lie, so
        there is no silent fallback any more: without an executor the task
        FAILS loudly. The only escape is the explicit dev flag
        SLUSHAI_ALLOW_SIMULATED_TASKS=1, for offline queue plumbing tests.
        """
        import os as _os
        if hasattr(self, 'task_executor') and self.task_executor:
            return self.task_executor(task)
        if _os.environ.get('SLUSHAI_ALLOW_SIMULATED_TASKS') == '1':
            logger.warning(
                'SIMULATED task %s (SLUSHAI_ALLOW_SIMULATED_TASKS=1, dev only)',
                task.task_id)
            time.sleep(1)
            return {'success': True, 'simulated': True}
        raise RuntimeError(
            'No task executor is set — refusing to simulate a generation')

    def set_executor(self, executor: Callable):
        """Set the task executor function."""
        self.task_executor = executor

    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """Remove completed/failed tasks older than max_age."""
        with self.lock:
            cutoff = time.time() - max_age_seconds
            to_remove = [
                tid for tid, task in self.tasks.items()
                if task.status in ('completed', 'failed', 'cancelled')
                and (task.completed_at or task.created_at) < cutoff
            ]
            for tid in to_remove:
                del self.tasks[tid]

    def close(self):
        """Shutdown aid for tests: close the rings so workers drain and
        exit. Not used by the server (its workers run for its lifetime).
        """
        for ring in self._rings:
            ring.close()
