# SlushAI 3D Modeller - Advanced Features Guide

This document covers the advanced features implemented in SlushAI 3D Modeller, including badge rewards, rate limiting, maintenance mode, and subscription plans.

## Table of Contents
- [Badge Reward System](#badge-reward-system)
- [Rate Limiting](#rate-limiting)
- [Maintenance Mode](#maintenance-mode)
- [Subscription Plans](#subscription-plans-future)
- [Weekly Quota System](#weekly-quota-system)

---

## Badge Reward System

### Overview
Users earn badges based on their lifetime model completions. Each badge level grants a **one-time reward** that resets their weekly quota.

### Badge Levels

| Level | Name | Requirements | Color | Reward |
|-------|------|--------------|-------|--------|
| 0 | Newcomer | 0-9 models | Gray (#94a3b8) | None |
| 1 | Creator | 10-49 models | Blue (#3b82f6) | Quota Reset |
| 2 | Artist | 50-199 models | Purple (#8b5cf6) | Quota Reset |
| 3 | Master | 200-499 models | Orange (#f59e0b) | Quota Reset |
| 4 | Legend | 500+ models | Red (#ef4444) | Quota Reset |

### How It Works

1. **Lifetime Tracking**: Every successfully completed model increments the user's lifetime completion count
2. **Auto-Level Up**: Badge level is automatically calculated based on completions
3. **One-Time Reward**: When a user reaches a new badge level (Creator+), they receive a quota reset **once**
4. **Reward Tracking**: The `badge_rewards` table prevents duplicate rewards for the same badge level

### Database Schema

```sql
CREATE TABLE badge_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_level INTEGER NOT NULL,
    badge_name TEXT NOT NULL,
    reward_type TEXT NOT NULL,
    reward_value TEXT,
    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, badge_level)
)
```

### Example Flow

```
User completes 10th model → Creator badge → Check badge_rewards table
  → No reward claimed yet → Insert reward record → Reset weekly quota → User gets fresh 10 models!
```

### Implementation Details

- **Check on Completion**: Badge level is checked after every successful model generation
- **Atomic Rewards**: Reward claiming is atomic (UNIQUE constraint prevents double-claiming)
- **Reset Notification**: Server logs show: "🎉 User {id} reached Creator level! Weekly quota reset as reward!"

---

## Rate Limiting

### Overview
Protects server resources by limiting request rates per user and per IP address.

### Rate Limits

| Endpoint | Authenticated | Anonymous | Notes |
|----------|--------------|-----------|-------|
| `/` (Landing) | N/A | 100/minute (by IP) | High limit for browsing |
| `/api/generate` | 1 per 2 seconds (by user) | Blocked | Prevents API abuse |
| `/api/screenshot` | 1 per 2 seconds (by user) | Blocked | Prevents spam |
| `/api/task/cancel` | 1 per 2 seconds (by user) | Blocked | Normal operations |

### Implementation

Uses **Flask-Limiter** with custom key functions:

```python
def get_limiter_key():
    if current_user.is_authenticated:
        return f'user:{current_user.user_id}'
    return f'ip:{get_remote_address()}'
```

### Decorator Usage

```python
@app.route('/api/generate', methods=['POST'])
@login_required
@limiter.limit("1 per 2 seconds", key_func=lambda: f'user:{current_user.user_id}')
def generate_model():
    ...
```

### Rate Limit Headers

Responses include standard rate limit headers:
- `X-RateLimit-Limit`: Total allowed requests
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Timestamp when limit resets

### Error Handling

When rate limit is exceeded:
- **Status Code**: 429 Too Many Requests
- **Response**: `{"error": "Rate limit exceeded", "retry_after": 2}`
- **Frontend**: Should show user-friendly message and retry button

---

## Maintenance Mode

### Overview
Automatic maintenance page displayed when server is overloaded (queue > 15 tasks).

### Features

1. **Auto-Detection**: Checks queue depth on `/viewer` access
2. **Real-Time Stats**: Shows current queue position and active workers
3. **ETA Calculation**: Estimates wait time based on queue and workers
4. **Auto-Retry**: Checks status every 5 seconds, auto-redirects when available
5. **Manual Retry**: Button to check immediately

### Trigger Conditions

```python
# In /viewer route
queue_status = task_queue.get_queue_status()
if queue_status.get('queued_count', 0) > 15:
    return redirect(url_for('maintenance'))
```

### Thresholds

- **< 5 tasks**: Available (auto-redirect to viewer)
- **5-10 tasks**: Moderate Load
- **10-15 tasks**: High Load (still accessible)
- **> 15 tasks**: Overloaded (redirect to maintenance)

### User Experience

**Maintenance Page Shows:**
- Queue position
- Active workers (1-3)
- Estimated wait time
- Real-time status updates
- Retry button

**Auto-Recovery:**
- Page checks status every 5 seconds
- Automatically redirects when queue < 5

---

## Subscription Plans (Future)

### Plan Structure

#### Standard Plan
- **Weekly**: $3.47/week
- **Yearly**: $72.17/year (60% off = $181.04 savings)
- **Features**:
  - 100 models per week
  - Priority queue
  - Higher resolution (512 vs 256)

#### Pro Plan
- **Weekly**: $7.89/week
- **Yearly**: $164.27/year (60% off = $410.68 savings)
- **Features**:
  - Unlimited models
  - Highest priority (jump to front of queue)
  - Maximum resolution (1024)
  - API access

### Currency Conversion

Plans will support multi-currency pricing:
- Base prices in USD
- API integration with exchangerate-api.io or similar
- User selects preferred currency
- Display shows: "$3.47 (€3.20) per week"
- Stripe handles actual conversion at checkout

### Database Schema

```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_type TEXT NOT NULL,
    billing_cycle TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    currency TEXT NOT NULL,
    amount_local REAL NOT NULL,
    stripe_subscription_id TEXT,
    status TEXT DEFAULT 'active',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    cancelled_at TIMESTAMP
)
```

### Quota Behavior

- **Free**: 10 models/week
- **Standard**: 100 models/week
- **Pro**: Unlimited (quota check returns `unlimited: true`)

---

## Weekly Quota System

### Reset Mechanism

#### Automatic Monday Reset
- **Frequency**: Every Monday at 00:00 UTC
- **Scope**: Per user, per week
- **Tracking**: ISO week number + year

#### Badge Reward Reset
- **Trigger**: User reaches new badge level (Creator+)
- **Effect**: Immediately resets `models_used` to 0 for current week
- **Frequency**: Once per badge level (tracked in `badge_rewards` table)

### Implementation

```python
def _reset_weekly_quota(self, cursor, user_id: int):
    """Reset the current week's quota for a user."""
    now = datetime.now()
    week_number = now.isocalendar()[1]
    year = now.year
    cursor.execute('''
        UPDATE weekly_quotas
        SET models_used = 0, textures_used = 0
        WHERE user_id = ? AND week_number = ? AND year = ?
    ''', (user_id, week_number, year))
```

### Quota Tracking

Only successful completions count:
```python
if status == 'completed':
    # Increment quota
    cursor.execute('UPDATE weekly_quotas SET models_used = models_used + 1...')
else:
    # Failed/cancelled tasks don't count
    log_usage(user_id, task_id, status, counted=False)
```

### Database Schema

```sql
CREATE TABLE weekly_quotas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    year INTEGER NOT NULL,
    models_used INTEGER DEFAULT 0,
    textures_used INTEGER DEFAULT 0,
    quota_limit INTEGER DEFAULT 10,
    UNIQUE(user_id, week_number, year)
)
```

---

## API Endpoints

### Rate Limiting
No new endpoints - limits applied via decorators

### Maintenance Mode
- `GET /maintenance` - Maintenance mode page (public)

### Badge Rewards
Integrated into existing endpoints:
- Badge check happens automatically on model completion
- Reward granted immediately when new level reached

---

## Configuration

### Environment Variables

```bash
# Rate Limiting
RATE_LIMIT_STORAGE=memory://  # Use Redis in production
RATE_LIMIT_STRATEGY=fixed-window

# Maintenance Mode
MAINTENANCE_QUEUE_THRESHOLD=15  # Trigger at 15+ queued tasks

# Subscriptions (Future)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
CURRENCY_API_KEY=...
```

### Tuning Parameters

**Rate Limits:**
```python
# In app.py
@limiter.limit("1 per 2 seconds")  # Adjust as needed
```

**Maintenance Threshold:**
```python
# In app.py /viewer route
if queue_status.get('queued_count', 0) > 15:  # Adjust threshold
```

**Badge Rewards:**
```python
# In user_manager.py
BADGE_REWARDS = {
    1: {'type': 'quota_reset', 'value': 'reset'},  # Customize reward type
    ...
}
```

---

## Testing

### Badge Rewards
```bash
# Test badge level-up
python -c "
from src.ai3d.utils.user_manager import UserManager
um = UserManager('logs/users.db')

# Simulate 10 completions
for i in range(10):
    um.log_task_complete(user_id=1, task_id=f'test_{i}', status='completed')

# Check badge level
user = um.get_user_by_id(1)
print(f'Badge Level: {user[\"badge_level\"]}')  # Should be 1 (Creator)
"
```

### Rate Limiting
```bash
# Test rate limit
for i in {1..5}; do
    curl -X POST http://localhost:5000/api/generate \
         -H "Cookie: session=..." \
         -F "image=@test.jpg"
    echo "Request $i"
done
# Should see 429 errors after 2nd request (within 2 seconds)
```

### Maintenance Mode
```bash
# Trigger maintenance mode
# Queue 16+ tasks rapidly, then visit http://localhost:5000/viewer
```

---

## Troubleshooting

### Badge reward not granted
**Check:**
1. Verify completion status is 'completed' (not 'failed')
2. Check `badge_rewards` table for existing entry
3. Check server logs for "🎉" emoji message

### Rate limit too restrictive
**Solution:**
```python
# Adjust limits in app.py
@limiter.limit("2 per 2 seconds")  # Increase to 2 requests
```

### Maintenance mode stuck
**Solution:**
```python
# Check queue status
from src.ai3d.utils.task_queue import TaskQueue
tq = TaskQueue()
print(tq.get_queue_status())

# Manually clear queue if needed
tq.clear_queue()  # Add this method if needed
```

---

## Security Considerations

1. **Rate Limiting**: Prevents brute force and API abuse
2. **Badge Rewards**: UNIQUE constraint prevents duplicate claims
3. **Maintenance Mode**: Protects server from overload
4. **User ID Tracking**: All operations tied to authenticated user_id

---

**Last Updated**: November 26, 2025  
**Status**: ✅ Badge Rewards, Rate Limiting, and Maintenance Mode fully implemented
