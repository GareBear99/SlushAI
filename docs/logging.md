# AI3DModeller Logging System

Complete documentation for the logging and monitoring system.

## Overview

AI3DModeller features a comprehensive logging system that tracks all user actions, system events, and errors. Logs are automatically organized by session and archived for historical reference.

## Log Structure

### Log Directory Layout
```
logs/
├── viewer.log              # Current active session log
├── archive/                # Archived logs from previous sessions
│   ├── viewer_20241126_143022.log
│   └── viewer_20241126_151544.log
└── sessions/               # Session logs with full output
    ├── session_20241126_143022.log
    └── session_20241126_151544.log
```

## Log Entry Format

Each log entry is a JSON object with the following structure:

```json
{
  "timestamp": "2024-11-26T14:30:22.123456",
  "session": "20241126_143022",
  "type": "action_type",
  "details": {
    "key": "value"
  }
}
```

## Tracked Actions

### Viewer Actions
- `viewer_started` - Viewer session initiated
- `page_view` - Page accessed
- `mode_switch` - Navigation mode changed (image/model/refine/texture/animate)
- `view_filter_change` - Asset filter changed (all/images/models)

### Image Actions
- `image_upload` - Image uploaded for generation
  - Details: filename, size, type
- `color_extraction` - Colors extracted from image
  - Details: r, g, b values

### Generation Actions
- `generation_start` - 3D generation initiated
  - Details: backend (triposr)
- `generation_complete` - Generation finished successfully
  - Details: path, duration (seconds)
- `generation_error` - Generation failed
  - Details: error message

### Model Actions
- `model_load_start` - Model loading initiated
  - Details: path
- `model_load_complete` - Model loaded successfully
  - Details: path
- `model_load_error` - Model loading failed
  - Details: path, error
- `color_change` - Model color changed
  - Details: type (theme-1, clay, white, etc.)
- `material_change` - Material type changed
  - Details: type (standard, glossy, metal, plastic, clay)
- `display_mode_change` - Display mode changed
  - Details: mode (solid, wireframe, points)
- `shading_change` - Shading type changed
  - Details: type (smooth, flat)

### Camera Actions
- `camera_reset` - Camera position reset

### Screenshot Actions
- `screenshot_captured` - Screenshot taken
  - Details: filename, path, size

### API Actions
- `api_call` - API endpoint accessed
  - Details: endpoint, method
- `file_access` - Output file accessed
  - Details: type, file

## Session Management

### Automatic Session Rotation

When the viewer server starts:
1. Old `viewer.log` is automatically archived with timestamp
2. New session log is created
3. Session ID is generated: `YYYYMMDD_HHMMSS`

### Manual Session Control

Start new session with logging:
```bash
./ai3d.sh start-log
```

This creates both:
- `logs/viewer.log` (structured JSON logs)
- `logs/sessions/session_TIMESTAMP.log` (full stdout/stderr)

## Accessing Logs

### Via CLI

```bash
# Tail active logs (real-time)
./ai3d.sh logs

# View last 100 entries
./ai3d.sh logs-view

# Search for specific term
./ai3d.sh logs-search "error"
./ai3d.sh logs-search "generation_complete"

# Archive and clear logs
./ai3d.sh logs-clear
```

### Via API

```bash
# Get recent log entries (JSON)
curl http://localhost:5000/api/logs

# Get last 50 entries
curl http://localhost:5000/api/logs?limit=50
```

### Via Python

```python
import json

# Read and parse logs
with open('logs/viewer.log', 'r') as f:
    for line in f:
        if '{' in line and '}' in line:
            json_str = line[line.index('{'):line.rindex('}')+1]
            entry = json.loads(json_str)
            print(f"{entry['timestamp']} [{entry['type']}] {entry['details']}")
```

## Log Analysis Examples

### Find all generation attempts
```bash
./ai3d.sh logs-search "generation_start"
```

### Calculate average generation time
```bash
grep "generation_complete" logs/viewer.log | \
python -c "
import json, sys
times = []
for line in sys.stdin:
    data = json.loads(line[line.index('{'):line.rindex('}')+1])
    times.append(data['details']['duration'])
print(f'Average: {sum(times)/len(times):.1f}s')
"
```

### Count actions by type
```bash
grep -o '\"type\":\"[^\"]*\"' logs/viewer.log | \
sort | uniq -c | sort -rn
```

### Find error events
```bash
grep -i "error" logs/viewer.log | \
python -c "
import json, sys
for line in sys.stdin:
    try:
        data = json.loads(line[line.index('{'):line.rindex('}')+1])
        print(f\"{data['timestamp']}: {data['type']} - {data['details']}\")
    except: pass
"
```

## Performance Monitoring

### Track Generation Performance
```bash
# Watch generation progress
watch -n 1 "./ai3d.sh logs-view | grep generation"

# Monitor memory during generation
watch -n 2 'ps aux | grep python | grep -v grep | awk "{print \$11, \$6/1024\"MB\"}"'
```

### Session Statistics
```python
import json
from collections import Counter
from datetime import datetime

with open('logs/viewer.log', 'r') as f:
    entries = []
    for line in f:
        if '{' in line and '}' in line:
            json_str = line[line.index('{'):line.rindex('}')+1]
            entries.append(json.loads(json_str))

# Count actions
action_counts = Counter(e['type'] for e in entries)
print("Action Summary:")
for action, count in action_counts.most_common():
    print(f"  {action}: {count}")

# Generation stats
generations = [e for e in entries if e['type'] == 'generation_complete']
if generations:
    durations = [e['details']['duration'] for e in generations]
    print(f"\nGeneration Stats:")
    print(f"  Total: {len(generations)}")
    print(f"  Avg Time: {sum(durations)/len(durations):.1f}s")
    print(f"  Min Time: {min(durations)}s")
    print(f"  Max Time: {max(durations)}s")
```

## Log Rotation

### Automatic Rotation
- Logs rotate automatically on server restart
- Old logs moved to `logs/archive/`

### Manual Rotation
```bash
./ai3d.sh logs-clear
```

### Cleanup Old Logs
```bash
# Keep only last 10 archived logs
cd logs/archive
ls -t *.log | tail -n +11 | xargs rm

# Delete logs older than 30 days
find logs/archive -name "*.log" -mtime +30 -delete
```

## Troubleshooting

### No Logs Generated
1. Check server is running: `./ai3d.sh status`
2. Check logs directory exists: `ls -la logs/`
3. Check file permissions: `ls -la logs/viewer.log`

### Logs Not Updating
1. Confirm logging endpoint is reachable:
   ```bash
   curl -X POST http://localhost:5000/api/log \
     -H "Content-Type: application/json" \
     -d '{"type":"test","details":{"message":"test"}}'
   ```
2. Check browser console for errors
3. Verify server is not in debug mode (which may suppress logs)

### Large Log Files
```bash
# Check log file size
du -h logs/viewer.log

# Compress old logs
gzip logs/archive/*.log

# Truncate active log (only if server stopped)
> logs/viewer.log
```

## Integration Examples

### Custom Logging in Code

Backend (Python):
```python
from viewer.app import session_logger

# Log custom action
session_logger.log_action('custom_event', {
    'key': 'value',
    'count': 123
})
```

Frontend (JavaScript):
```javascript
// Log custom action
async function logAction(type, details) {
    await fetch('/api/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, details })
    });
}

// Usage
logAction('user_clicked_button', { button: 'export' });
```

### Webhooks
```python
# Send logs to external service
import requests

def send_to_webhook(log_entry):
    webhook_url = "https://your-service.com/webhook"
    requests.post(webhook_url, json=log_entry)

# In session_logger.log_action()
send_to_webhook(log_entry)
```

## Best Practices

1. **Regular Review**: Check logs weekly for errors and performance issues
2. **Archive Management**: Keep 30 days of archived logs
3. **Monitoring**: Set up alerts for error events
4. **Privacy**: Never log sensitive user data or credentials
5. **Performance**: Rotate logs before they exceed 100MB

## Configuration

Environment variables (optional):
```bash
# Set log level
export AI3D_LOG_LEVEL="DEBUG"  # DEBUG, INFO, WARNING, ERROR

# Custom log directory
export AI3D_LOG_DIR="/custom/path/logs"

# Disable logging
export AI3D_LOGGING_ENABLED="false"
```

## Support

For issues or questions about the logging system:
1. Check this documentation
2. Review logs for error messages
3. Test with `./ai3d.sh logs-search "error"`
4. Verify API endpoints are accessible
