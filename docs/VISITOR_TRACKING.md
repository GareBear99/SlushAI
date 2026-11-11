# Visitor Tracking & Analytics

## Overview
AI3DModeller now includes comprehensive visitor tracking and analytics that logs every request with IP addresses, response times, and user actions.

**Key Features:**
- ✅ Automatic IP tracking on every request
- ✅ GDPR-friendly IP hashing for privacy
- ✅ Real-time analytics dashboard
- ✅ SQLite database for persistent storage
- ✅ CLI commands for monitoring
- ✅ API endpoints for programmatic access

---

## How It Works

### Automatic Tracking
The Flask server automatically tracks **every request** including:
- IP address (with proxy support)
- Request method (GET, POST, etc.)
- Endpoint accessed
- Response time in milliseconds
- User agent
- HTTP status code
- Referer URL

### Privacy & GDPR Compliance
- IP addresses are hashed (SHA-256) for visitor identification
- Original IPs are stored but can be anonymized
- No cookies or client-side tracking
- Data retention policies can be configured

---

## Database Schema

### Tables Created

**visitors**
- Unique visitors identified by IP hash
- First seen, last seen timestamps
- Visit count
- User agent

**requests**
- Detailed log of every HTTP request
- Links to visitor ID
- Response times for performance monitoring
- Full request metadata

**sessions**
- User session tracking
- Page views, actions performed
- Models generated, screenshots taken

**daily_stats**
- Aggregated statistics per day
- Unique visitors count
- Total requests
- Average response times

---

## CLI Commands

### View Analytics
```bash
./ai3d.sh analytics
```
Shows visitor statistics including:
- Total visitors
- Active today
- Requests per day
- Models generated
- Screenshots taken
- Top endpoints

**Example Output:**
```json
{
    "total_visitors": 1,
    "active_today": 1,
    "recent_days": [
        {
            "date": "2025-11-25",
            "unique_visitors": 1,
            "total_requests": 15,
            "models_generated": 2,
            "screenshots_taken": 1,
            "avg_response_time": 45.3
        }
    ],
    "top_endpoints": [
        {"endpoint": "list_models", "count": 8},
        {"endpoint": "get_logs", "count": 4}
    ]
}
```

### List All Visitors
```bash
./ai3d.sh visitors
```
Shows recent visitors with:
- IP address
- Visit count
- First visit date
- Last visit date

**Example Output:**
```
ip_address     visit_count  first_visit          last_visit         
127.0.0.1      15           2025-11-25 22:56:58  2025-11-25 23:10:42
192.168.1.100  3            2025-11-25 20:15:00  2025-11-25 20:30:15
```

### Get Visitor History
```bash
./ai3d.sh visitor-info <ip_address>
```
Shows detailed history for a specific visitor (when accessed via API).

---

## API Endpoints

### GET /api/analytics
Get visitor statistics and analytics.

**Query Parameters:**
- `days` (optional): Number of days to include (default: 7)

**Response:**
```json
{
  "total_visitors": 42,
  "active_today": 5,
  "recent_days": [...],
  "top_endpoints": [...]
}
```

### GET /api/visitor/history
Get current visitor's request history.

**Response:**
```json
{
  "first_seen": "2025-11-25T22:56:58",
  "last_seen": "2025-11-25T23:10:42",
  "visit_count": 15,
  "recent_requests": [
    {
      "timestamp": "2025-11-25T23:10:42",
      "method": "GET",
      "endpoint": "list_models",
      "path": "/api/models",
      "status_code": 200
    }
  ]
}
```

---

## Tracked Actions

### Automatic Actions
Every request is automatically logged with:
- Timestamp
- IP address
- HTTP method
- Endpoint accessed
- Response time
- Status code

### Specific Actions Tracked

**Model Generation**
```
- Action: model_generated
- Details: filename, backend used
- Aggregated in daily stats
```

**Screenshot Capture**
```
- Action: screenshot
- Details: filename, file size
- Aggregated in daily stats
```

**Page Views**
```
- Action: page_view
- Details: page name
- Tracked in sessions
```

**API Calls**
```
- Action: api_call
- Details: endpoint, method
- Counted in endpoint statistics
```

---

## Implementation Details

### Flask Middleware
Two middleware functions wrap every request:

**@app.before_request**
- Captures request start time
- Extracts visitor IP (handles proxies)

**@app.after_request**
- Calculates response time
- Logs request to database
- Returns visitor ID for route handlers

### Database Location
```
logs/visitors.db
```
SQLite database, can be queried directly:
```bash
sqlite3 logs/visitors.db "SELECT * FROM visitors ORDER BY last_seen DESC LIMIT 10;"
```

---

## Use Cases

### Monitor Traffic
Track how many people are using your AI3DModeller instance:
```bash
./ai3d.sh analytics
```

### Identify Heavy Users
See who's generating the most models:
```bash
./ai3d.sh visitors | sort -k2 -nr
```

### Performance Monitoring
Check average response times:
```bash
curl -s http://localhost:5000/api/analytics | jq '.recent_days[].avg_response_time'
```

### Debug Issues
Find which endpoints are being hit:
```bash
./ai3d.sh analytics | jq '.top_endpoints'
```

---

## Privacy Configuration

### Anonymize IPs (Optional)
To hash IPs without storing originals, modify `visitor_tracker.py`:
```python
# In track_request(), change:
cursor.execute('''
    INSERT INTO visitors (ip_hash, ip_address, ...)
    VALUES (?, '[anonymized]', ...)  # Don't store real IP
''', (ip_hash, user_agent, user_agent))
```

### Data Retention
Set up automatic cleanup of old data:
```bash
# Add to cron: clean data older than 90 days
sqlite3 logs/visitors.db "DELETE FROM requests WHERE timestamp < datetime('now', '-90 days');"
```

---

## Server Behavior

### On-Demand Operation
The Flask server:
- ✅ Only runs when started (`./ai3d.sh start`)
- ✅ Waits for requests (doesn't consume resources when idle)
- ✅ Can be stopped when not needed (`./ai3d.sh stop`)
- ✅ Automatically tracks all activity when running

### Resource Usage
- Minimal overhead (~1ms per request for tracking)
- SQLite database grows slowly (~1KB per 100 requests)
- No impact on generation performance

---

## Examples

### Real-Time Monitoring
```bash
# Terminal 1: Start server
./ai3d.sh start

# Terminal 2: Watch analytics
watch -n 5 './ai3d.sh analytics'

# Terminal 3: Monitor visitors
watch -n 10 './ai3d.sh visitors'
```

### Generate Report
```bash
# Get today's stats
curl -s http://localhost:5000/api/analytics?days=1 | \
  jq '.recent_days[0]' > daily_report.json

echo "Today: $(jq '.total_requests' daily_report.json) requests"
echo "Models: $(jq '.models_generated' daily_report.json)"
echo "Screenshots: $(jq '.screenshots_taken' daily_report.json)"
```

---

## Testing

Test visitor tracking:
```bash
# Start server
./ai3d.sh start

# Make some requests
curl http://localhost:5000/api/models
curl http://localhost:5000/api/logs
curl http://localhost:5000/

# View analytics
./ai3d.sh analytics

# Check visitor list
./ai3d.sh visitors
```

---

## Summary

**What Gets Tracked:**
- ✅ Every HTTP request with IP address
- ✅ Response times for performance monitoring
- ✅ User actions (model generation, screenshots)
- ✅ Daily aggregated statistics
- ✅ Top endpoints and usage patterns

**How to Access:**
- CLI: `./ai3d.sh analytics`, `./ai3d.sh visitors`
- API: `GET /api/analytics`, `GET /api/visitor/history`
- Direct: `sqlite3 logs/visitors.db`

**Benefits:**
- Monitor usage patterns
- Identify performance issues
- Track feature adoption
- Debug problems
- Understand user behavior
