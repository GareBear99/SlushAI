# Comprehensive Logging System Documentation

## Overview
The SlushAI 3D Modeller platform now includes extensive logging for debugging and tracking all actions, rate limiter hits, and requests.

## Log Types

### 1. Request Logs
Every incoming request is logged with complete context:

**Format:** `INCOMING: {json_data}`

**Fields:**
- `timestamp`: ISO format timestamp
- `event`: "request_received"
- `method`: HTTP method (GET, POST, etc.)
- `path`: Request path
- `endpoint`: Flask endpoint name
- `ip`: Client IP address
- `limiter_key`: Rate limiter key (user:USER_ID or ip:IP_ADDRESS)
- `user_agent`: Browser/client user agent
- `referer`: Referring URL
- `query_string`: URL query parameters
- `user`: User object (if authenticated) with user_id and email

**Example:**
```json
{
  "timestamp": "2025-11-28T02:10:15.123456",
  "event": "request_received",
  "method": "GET",
  "path": "/",
  "endpoint": "landing",
  "ip": "127.0.0.1",
  "limiter_key": "ip:127.0.0.1",
  "user_agent": "Mozilla/5.0...",
  "referer": "",
  "query_string": ""
}
```

### 2. Request Completion Logs
Every completed request is logged with response details:

**Format:** `REQUEST: {json_data}`

**Fields:**
- `timestamp`: ISO format timestamp
- `event`: "request_complete"
- `method`: HTTP method
- `path`: Request path
- `endpoint`: Flask endpoint name
- `status_code`: HTTP response status code
- `response_time_ms`: Response time in milliseconds
- `ip`: Client IP address
- `limiter_key`: Rate limiter key
- `rate_limit_delayed`: Reason if request was delayed (or null)
- `visitor_id`: Unique visitor tracking ID
- `user`: User object (if authenticated)

**Log Level:**
- WARNING: status_code >= 400
- INFO: status_code < 400

**Example:**
```json
{
  "timestamp": "2025-11-28T02:10:15.234567",
  "event": "request_complete",
  "method": "GET",
  "path": "/",
  "endpoint": "landing",
  "status_code": 200,
  "response_time_ms": 45.32,
  "ip": "127.0.0.1",
  "limiter_key": "ip:127.0.0.1",
  "rate_limit_delayed": null,
  "visitor_id": "abc123"
}
```

### 3. Rate Limiter Hit Logs
When a rate limit is exceeded:

**Format:** `RATE_LIMIT: {json_data}` or `RATE_LIMIT_BLOCKED: {json_data}`

**Fields:**
- `timestamp`: ISO format timestamp
- `event`: "rate_limit_exceeded"
- `limiter_key`: Rate limiter key (user or IP based)
- `ip`: Client IP address
- `user`: User object (if authenticated) with user_id, email, name
- `endpoint`: Flask endpoint name
- `path`: Request path
- `method`: HTTP method
- `limit_description`: Description of the limit exceeded
- `user_agent`: Browser/client user agent
- `referer`: Referring URL
- `action`: "global_limit_queue_delay" or "rate_limit_blocked"
- `delay_seconds`: Delay applied (if global limit)

**Example (Global Limit - Queued):**
```json
{
  "timestamp": "2025-11-28T02:10:15.123456",
  "event": "rate_limit_exceeded",
  "limiter_key": "ip:127.0.0.1",
  "ip": "127.0.0.1",
  "user": null,
  "endpoint": "api_health",
  "path": "/api/health",
  "method": "GET",
  "limit_description": "1000 per 1 minute (global)",
  "user_agent": "curl/7.68.0",
  "referer": "",
  "action": "global_limit_queue_delay",
  "delay_seconds": 2
}
```

**Example (Per-IP Limit - Blocked):**
```json
{
  "timestamp": "2025-11-28T02:10:15.123456",
  "event": "rate_limit_exceeded",
  "limiter_key": "ip:127.0.0.1",
  "ip": "127.0.0.1",
  "user": null,
  "endpoint": "landing",
  "path": "/",
  "method": "GET",
  "limit_description": "100 per 1 minute",
  "user_agent": "Mozilla/5.0...",
  "referer": "",
  "action": "rate_limit_blocked"
}
```

### 4. Function Call Action Logs
Tracked functions log their execution:

**Format:** `ACTION: {json_data}`

**Fields:**
- `timestamp`: ISO format timestamp
- `event`: "function_call"
- `function`: Function name
- `action`: Action name or description
- `status`: "completed" or "failed" (for completion logs)
- `error`: Error message (if failed)
- `path`: Request path (if in request context)
- `method`: HTTP method (if in request context)
- `endpoint`: Flask endpoint (if in request context)
- `ip`: Client IP (if in request context)
- `limiter_key`: Rate limiter key (if in request context)
- `user`: User object (if authenticated)

**Example:**
```json
{
  "timestamp": "2025-11-28T02:10:15.123456",
  "event": "function_call",
  "function": "generate_model",
  "action": "generate_model_success",
  "status": "completed",
  "path": "/api/generate",
  "method": "POST",
  "endpoint": "api_generate",
  "ip": "127.0.0.1",
  "limiter_key": "user:user_abc123",
  "user": {
    "user_id": "user_abc123",
    "email": "user@example.com"
  }
}
```

## Log Files

### viewer.log
- Location: `logs/viewer.log`
- Retention: Last 2560 request entries (auto-truncates)
- Contains: All INFO, WARNING, and ERROR logs
- Archives old logs to: `logs/archive/viewer_TIMESTAMP.log`

### errors.log
- Location: `logs/errors.log`
- Retention: 90 days (3 months)
- Contains: Only ERROR and CRITICAL logs
- Auto-cleanup: Entries older than 90 days are removed on startup

### Archived Logs
- Location: `logs/archive/`
- Format: `viewer_YYYYMMDD_HHMMSS.log`
- Retention: Manual cleanup required

## Using the Logging System

### Debugging Rate Limiter Issues
1. Search for `RATE_LIMIT` in logs to find all rate limit hits
2. Check `limiter_key` to identify which user/IP was rate limited
3. Look at `limit_description` to see which limit was exceeded
4. Check `action` field:
   - `global_limit_queue_delay`: Request was queued (not blocked)
   - `rate_limit_blocked`: Request was blocked with 429 response

### Tracking Request Flow
1. Find `INCOMING` log entry for request start
2. Find `REQUEST` log entry for request completion
3. Match by `timestamp` and `path` to see full request lifecycle
4. Check `response_time_ms` for performance issues
5. Check `status_code` for errors

### Tracking User Actions
1. Search for user_id or email in logs
2. Filter by `ACTION` prefix to see function executions
3. Look for `_success` or `_error` suffixes in action names
4. Check `status` field for completion state

### Finding Errors
1. Check `errors.log` for ERROR and CRITICAL entries
2. Search `viewer.log` for `status_code >= 400`
3. Look for `"status": "failed"` in ACTION logs
4. Check `error` field for exception messages

## Log Analysis Commands

```bash
# Find all rate limit hits
grep "RATE_LIMIT" logs/viewer.log

# Find specific user activity
grep "user_abc123" logs/viewer.log | grep "ACTION"

# Find all 500 errors
grep '"status_code": 500' logs/viewer.log

# Find slow requests (>1000ms)
grep -E '"response_time_ms": [0-9]{4,}' logs/viewer.log

# Count requests by endpoint
grep "request_complete" logs/viewer.log | jq -r '.endpoint' | sort | uniq -c

# Find all blocked rate limit hits
grep "RATE_LIMIT_BLOCKED" logs/viewer.log

# Get recent errors only
tail -100 logs/errors.log
```

## Performance Considerations

- Logs are written synchronously but efficiently
- JSON format allows for easy parsing and analysis
- Auto-truncation prevents disk space issues
- Archived logs can be compressed or deleted manually

## Best Practices

1. **Always check logs when debugging** - comprehensive tracking is in place
2. **Use structured search** - logs are JSON formatted for easy parsing
3. **Monitor rate limits** - track RATE_LIMIT entries for abuse patterns
4. **Archive important logs** - auto-cleanup will remove old entries
5. **Use jq for analysis** - JSON logs work great with jq tool

## Adding New Tracked Actions

To add tracking to a new function:

```python
@track_action("action_name")
def my_function():
    # Function code
    pass
```

Or manually log:

```python
log_function_call("my_function", action="custom_action", custom_field="value")
```
