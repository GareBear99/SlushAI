"""SPSC TaskQueue checks (stdlib only, dev-flag executor).

Run: .venv/bin/python tests/test_spsc_queue.py  (or python3 on the VM).
Covers the ring bound/FIFO/backpressure, queue completion + cancel-skip,
status timing fields, and the public API surface the app uses.
"""
import os, sys, time
os.environ['SLUSHAI_ALLOW_SIMULATED_TASKS'] = '1'
_here = os.path.dirname(os.path.abspath(__file__))
# task_queue.py lives in src/ai3d/utils/ on the Mac; next to tests/ on
# the VM working copy. Try both, first hit wins.
for _p in (os.path.join(_here, '..', 'src', 'ai3d', 'utils'), _here, os.path.dirname(_here)):
    if os.path.exists(os.path.join(_p, 'task_queue.py')):
        sys.path.insert(0, os.path.abspath(_p))
        break
from task_queue import TaskQueue, SPSCRing

# 1. Ring bound + FIFO + backpressure shape
r = SPSCRing(4)
for i in range(4):
    r.push(i)
assert len(r) == 4, len(r)
assert r.max_inflight == 4
assert [r.pop() for _ in range(4)] == [0, 1, 2, 3]
assert len(r) == 0
print("ring: bound 4, FIFO, counters OK")

# 2. Queue: add 3 tasks, one cancelled, all complete; status fields present
q = TaskQueue()
def exec_(task):
    time.sleep(0.05)
    return {'success': True, 'task_id': task.task_id}
q.set_executor(exec_)
t1 = q.add_task('t1', 'model', {})
t2 = q.add_task('t2', 'model', {})
t3 = q.add_task('t3', 'model', {})
assert q.cancel_task('t3') is True, "cancel t3"
assert q.cancel_task('t3') is False, "cancel t3 twice"
assert q.cancel_task('nope') is False
deadline = time.time() + 10
while time.time() < deadline:
    s1, s2, s3 = (q.get_task_status(x) for x in ('t1', 't2', 't3'))
    if s1['status'] == 'completed' and s2['status'] == 'completed' and s3['status'] == 'cancelled':
        break
    time.sleep(0.1)
assert s1['status'] == 'completed', s1
assert s2['status'] == 'completed', s2
assert s3['status'] == 'cancelled', s3
assert s1['dispatched_at'] is not None and s1['dispatched_at'] >= s1['created_at']
assert s1['queue_wait_seconds'] is not None and s1['queue_wait_seconds'] >= 0
assert s1['execution_seconds'] is not None and s1['execution_seconds'] >= 0.05
assert s1['result'] == {'success': True, 'task_id': 't1'}
print("queue: 2 completed + 1 cancelled-skip; status fields OK")
print("  t1 queue_wait=%.3fs execution=%.3fs" % (s1['queue_wait_seconds'], s1['execution_seconds']))

# 3. get_queue_status + spsc stats shape
qs = q.get_queue_status()
assert qs['queue_length'] == 0, qs
assert qs['spsc']['ring_capacity'] == 512
assert qs['spsc']['dispatcher_alive'] is True
assert len(qs['spsc']['lanes']) == 3
assert all(l['inflight'] <= 512 for l in qs['spsc']['lanes'])
assert sum(l['pushed'] for l in qs['spsc']['lanes']) >= 2  # dispatcher balances across lanes
print("queue_status + spsc stats OK:", {k: qs['spsc'][k] for k in ('ring_capacity', 'intake_depth', 'dispatcher_alive')})

# 4. Backpressure: fill a lane ring directly (dispatcher blocked path is
#    structural — here prove push blocks when full, then unblocks on pop).
r2 = SPSCRing(2)
r2.push('a'); r2.push('b')
done = []
def _pusher():
    r2.push('c')
    done.append('pushed')
import threading
th = threading.Thread(target=_pusher, daemon=True); th.start()
time.sleep(0.3)
assert done == [], "push must block while the ring is full"
assert r2.pop() == 'a'
th.join(timeout=2)
assert done == ['pushed'], "push must unblock once a slot frees"
print("ring: backpressure blocks when full, unblocks on pop — never drops")

# 5. Public API surface the app uses
for name in ('add_task', 'get_task_status', 'get_queue_status', 'cancel_task',
             'set_executor', 'cleanup_old_tasks', 'get_spsc_stats', 'tasks',
             'lock', 'current_tasks', 'processing', 'active_worker_count'):
    assert hasattr(q, name), name
print("public API surface OK")
print("ALL SPSC VM CHECKS PASSED")
