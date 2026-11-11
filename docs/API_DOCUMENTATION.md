# API Documentation

**SlushAI 3D Modeller API Reference**

Last Updated: November 26, 2025

---

## Overview

The SlushAI 3D Modeller API provides programmatic access to our AI-powered 3D model generation service. All API endpoints require authentication via OAuth (Google or Facebook).

**Base URL:** `http://localhost:5000` (production URL will differ)

**Authentication:** OAuth 2.0 (Google / Facebook)

**Response Format:** JSON

---

## Authentication

### OAuth Providers

#### Google OAuth
```
GET /auth/login
```
Initiates Google OAuth flow. Redirects to Google sign-in page.

**Callback:** `/auth/callback`

#### Facebook OAuth
```
GET /auth/facebook
```
Initiates Facebook OAuth flow. Redirects to Facebook sign-in page.

**Callback:** `/auth/facebook/callback`

### Logout
```
GET /auth/logout
```
Logs out the current user and invalidates the session.

**Authentication:** Required

---

## User Endpoints

### Get User Profile
```
GET /api/user/profile
```

Returns the authenticated user's profile information and quota status.

**Authentication:** Required

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "John Doe",
  "picture": "https://lh3.googleusercontent.com/...",
  "badge_level": 0,
  "badge_name": "Free",
  "badge_color": "#6b7280",
  "total_models": 42,
  "joined_date": "2025-01-15T10:30:00",
  "quota": {
    "can_generate": true,
    "weekly_limit": 10,
    "weekly_used": 3,
    "weekly_remaining": 7,
    "week_start": "2025-11-24",
    "week_end": "2025-12-01"
  }
}
```

---

## Model Generation

### Generate 3D Model
```
POST /api/generate
```

Generate a 3D model from an uploaded image.

**Authentication:** Required

**Content-Type:** `multipart/form-data`

**Request Body:**
- `image` (file, required): Image file (PNG, JPG, JPEG, WEBP)
- `backend` (string, optional): Generation backend (`triposr` or `dust3r`, default: `triposr`)

**Response (Success):**
```json
{
  "success": true,
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Model generation started",
  "position": 1,
  "estimated_time": "3-5 minutes"
}
```

**Response (Queue Full):**
```json
{
  "success": false,
  "error": "Queue is full (15 tasks). Please try again later."
}
```

**Response (Quota Exceeded):**
```json
{
  "error": "Weekly quota exceeded. You've used 10/10 free models this week."
}
```

**Rate Limit:** 5 requests/minute per user

---

## Model Management

### List Models
```
GET /api/models
```

List all available 3D models.

**Authentication:** Required

**Response:**
```json
{
  "models": [
    {
      "name": "example_model_preview.obj",
      "path": "outputs/example_model_preview.obj",
      "size": 15728640,
      "created": "2025-11-26T10:30:00"
    }
  ]
}
```

### Download Model
```
GET /download/<filename>
```

Download a specific 3D model file.

**Authentication:** Required

**Parameters:**
- `filename` (path): Name of the model file

**Response:** Binary file data (OBJ, GLB, MTL, or PNG)

---

## Favorites System

### Add to Favorites
```
POST /api/favorites/add
```

Mark a model as a favorite (prevents auto-deletion after 36 hours).

**Authentication:** Required

**Request Body:**
```json
{
  "model_path": "/absolute/path/to/model.obj"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Model added to favorites",
  "favorites_count": 5
}
```

**Limits:**
- Maximum 10 favorites per user
- Maximum 32 total models per user

### Remove from Favorites
```
POST /api/favorites/remove
```

Remove a model from favorites (36-hour deletion timer restarts).

**Authentication:** Required

**Request Body:**
```json
{
  "model_path": "/absolute/path/to/model.obj"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Model removed from favorites"
}
```

### List Favorites
```
GET /api/favorites/list
```

Get all favorited models for the current user.

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "favorites": [
    {
      "model_path": "/path/to/model.obj",
      "added_at": "2025-11-26T10:30:00"
    }
  ],
  "count": 5,
  "limit": 10
}
```

**Rate Limit:** 30 requests/minute per user

### Get Recent Models
```
GET /api/favorites/recent
```

Get recently generated models with their deletion timers.

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "models": [
    {
      "name": "model_preview.obj",
      "path": "/absolute/path/to/model.obj",
      "generated_at": "2025-11-26T10:30:00",
      "expires_at": "2025-11-27T22:30:00",
      "is_favorite": false,
      "time_display": "12h"
    }
  ]
}
```

**Time Display Values:**
- `∞` - Favorited (never expires)
- `23h`, `12h`, `45m` - Time remaining until deletion

---

## Screenshot System

### Capture Screenshot
```
POST /api/screenshot
```

Capture a screenshot of the current 3D model view.

**Authentication:** Required

**Request Body:**
```json
{
  "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANS..."
}
```

**Response:**
```json
{
  "success": true,
  "filename": "screenshot_20251126_103045.png",
  "path": "outputs/screenshots/screenshot_20251126_103045.png"
}
```

**Rate Limit:** 1 request/minute per user

**Cooldown:** 60 seconds between screenshots

### Check Screenshot Cooldown
```
GET /api/screenshot/cooldown
```

Check remaining cooldown time before next screenshot.

**Authentication:** Required

**Response:**
```json
{
  "can_capture": false,
  "remaining_seconds": 42
}
```

---

## Issue Reporting

### Get All Issues
```
GET /api/issues
```

Retrieve all reported issues (admin only for full access).

**Authentication:** Required

**Response:**
```json
{
  "issues": [
    {
      "issue_id": "issue-uuid",
      "title": "Model generation failed",
      "description": "Error occurred during texture generation",
      "status": "open",
      "priority": "high",
      "created_at": "2025-11-26T10:30:00",
      "user_id": "user-uuid",
      "user_email": "user@example.com"
    }
  ]
}
```

**Rate Limit:** 20 requests/minute per user

### Create Issue
```
POST /api/issues/create
```

Report a new issue or bug.

**Authentication:** Required

**Request Body:**
```json
{
  "title": "Issue title",
  "description": "Detailed description of the issue",
  "priority": "medium",
  "issue_type": "bug"
}
```

**Priorities:** `low`, `medium`, `high`, `critical`

**Types:** `bug`, `feature`, `feedback`, `other`

**Response:**
```json
{
  "success": true,
  "issue_id": "issue-uuid",
  "message": "Issue reported successfully"
}
```

---

## Queue Status

### Get Queue Status
```
GET /api/queue/status
```

Get current generation queue status.

**Authentication:** Not required

**Response:**
```json
{
  "active_workers": 2,
  "queued_count": 3,
  "processing_count": 2,
  "third_worker_active": false,
  "current_tasks": {
    "0": {
      "task_id": "task-uuid-1",
      "filename": "image1.png",
      "status": "processing"
    },
    "1": {
      "task_id": "task-uuid-2",
      "filename": "image2.png",
      "status": "processing"
    }
  }
}
```

---

## Security Endpoints

### Get Security Statistics
```
GET /api/security/stats?days=30
```

Get attack statistics for the specified period.

**Authentication:** Required

**Query Parameters:**
- `days` (integer, optional): Number of days to query (default: 30)

**Response:**
```json
{
  "success": true,
  "stats": {
    "period_days": 30,
    "total_attacks": 156,
    "blocked_ips": 23,
    "attack_types": {
      "sql_injection": 45,
      "xss_attempt": 32,
      "suspicious_user_agent": 28,
      "rate_limit_exceeded": 51
    }
  }
}
```

### Get Recent Attacks
```
GET /api/security/recent-attacks?limit=100
```

Get recent attack attempts (admin only).

**Authentication:** Required (Admin)

**Query Parameters:**
- `limit` (integer, optional): Maximum number of attacks to return (default: 100)

**Response:**
```json
{
  "success": true,
  "attacks": [
    {
      "ip": "192.168.1.100",
      "type": "sql_injection",
      "endpoint": "/api/generate",
      "timestamp": "2025-11-26T10:30:00"
    }
  ],
  "count": 42
}
```

---

## Health Check

### Server Health
```
GET /api/health
```

Check if the server is running.

**Authentication:** Not required

**Response:**
```json
{
  "ok": true,
  "time": 1700000000.123,
  "outputs_dir": "/path/to/outputs"
}
```

---

## Error Responses

### Common Error Codes

**400 Bad Request**
```json
{
  "error": "Invalid input",
  "reason": "Potentially malicious pattern detected"
}
```

**403 Forbidden**
```json
{
  "error": "Access denied",
  "reason": "IP blocked due to suspicious activity"
}
```

**429 Too Many Requests**
```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests"
}
```

**500 Internal Server Error**
```json
{
  "success": false,
  "message": "An error occurred"
}
```

---

## WebSocket Events

The application uses Socket.IO for real-time progress updates during model generation.

### Connection
```javascript
const socket = io();
```

### Events

#### `generation_started`
Emitted when a generation task starts.
```javascript
{
  "task_id": "task-uuid",
  "filename": "image.png",
  "backend": "triposr"
}
```

#### `progress`
Emitted periodically during generation.
```javascript
{
  "task_id": "task-uuid",
  "stage": "extract",
  "percent": 65,
  "elapsed": 120
}
```

**Stages:** `loading`, `extract`, `texture`

#### `generation_complete`
Emitted when generation finishes successfully.
```javascript
{
  "task_id": "task-uuid",
  "success": true,
  "preview_path": "outputs/model_preview.obj"
}
```

#### `generation_error`
Emitted when generation fails.
```javascript
{
  "task_id": "task-uuid",
  "success": false,
  "error": "Error message"
}
```

---

## Best Practices

### Rate Limiting
- Respect rate limits to avoid being temporarily blocked
- Implement exponential backoff for retries
- Cache responses when appropriate

### Error Handling
- Always check for error responses
- Log errors for debugging
- Provide user-friendly error messages

### Security
- Never expose your session tokens
- Use HTTPS in production
- Validate all input data
- Monitor for unusual API usage patterns

### Performance
- Compress images before uploading
- Use appropriate image formats (PNG/JPG recommended)
- Poll queue status instead of waiting synchronously
- Close WebSocket connections when done

---

## Support

For API support, please:
1. Visit `/docs` for documentation
2. Report issues via the issue reporting system
3. Check rate limits and quota status

**Note:** This API is subject to change. Always refer to the latest documentation.
