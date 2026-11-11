# Storage Management & Activity Logging System

**Founded by Gary Richard Doman**

## Overview
SlushAI implements a comprehensive storage management system with intelligent auto-cleanup, user activity logging, and save/unsave functionality separate from favorites.

### What is SlushAI?
SlushAI 3D Modeller is an AI-powered platform that transforms 2D images into high-quality 3D models using TripoSR technology. The system includes:
- **Smart Generation**: Upload an image, get a 3D model in minutes
- **Intelligent Storage**: Auto-cleanup with save/favorite system
- **Activity Logging**: Track all your generations and actions (30-day history)
- **Security**: Multi-tier protection and fair-use rate limiting
- **Flexible Plans**: Free tier plus paid upgrades for power users

### Interface Tabs
The SlushAI platform features a clean tabbed interface:

1. **🎲 Generate Tab** - Upload images and start AI generation with real-time progress monitoring
2. **👁️ Viewer Tab** - Interactive 3D viewer with orbit controls, downloads, and screenshot capture
3. **⭐ Favorites Tab** - Manage saved (temporary) and favorited (permanent) models with storage indicators
4. **🖼️ Screenshots Tab** - Gallery of captured images with download/delete options (1-minute cooldown)
5. **👤 Account Tab** - Profile, quota usage, badge progress, subscription management, activity history
6. **🐛 Issues Tab** - Bug reports, feature requests, and admin moderation tools
7. **📊 Queue Status** - Real-time queue monitoring with 1-3 concurrent workers and ETA display

---

## Storage Capacity (1000GB Infrastructure)

### User Tiers
Based on **actual save limits** (average 10MB per model):

**🎁 Free Tier**
- **200 users maximum**
- **32 models max** per user (10 favorites + 32 total)
- **Total: ~64GB** (200 × 32 models × 10MB)
- **36-hour retention** for unsaved models

**⭐ Standard Tier**
- **50 users maximum**
- **150 models max** per user (50 favorites + 150 total)
- **Total: ~75GB** (50 × 150 models × 10MB)
- **14-day retention** for unsaved models

**👑 Pro Tier**
- **20 users maximum**
- **500 models max** per user (150 favorites + 500 total)
- **Total: ~100GB** (20 × 500 models × 10MB)
- **30-day retention** for unsaved models

### Staff Tiers
**👑 Founder**
- **Gary Richard Doman** (gdoman99@gmail.com)
- **Unlimited storage** (~10,000 models estimated)
- **Total: ~100GB**
- **Never deleted**

**🛡️ Moderators**
- **5 moderators maximum**
- **5,000 models** per moderator (1,000 favorites + 5,000 total)
- **Total: ~250GB** (5 × 50GB)
- **Never deleted**

**⚙️ Admins**
- **3 admins maximum**
- **5,000 models** per admin (1,000 favorites + 5,000 total)
- **Total: ~150GB** (3 × 50GB)
- **Never deleted**

### Total Capacity
- **Users: 239GB** (Free + Standard + Pro)
- **Staff: 500GB** (Founder + Moderators + Admins)
- **Grand Total: ~739GB** (74% of 1000GB capacity)
- **Headroom: 261GB** for growth

---

## Save/Unsave System

### Model States & Button Behavior
Every model in your gallery (Recent models, Favorites tab) has two buttons:

**💾 Save Button** (bookmark icon)
- Toggles between "Save" and "Unsave"
- Protects model from auto-cleanup
- Can be unsaved at any time (unless favorited)
- Counts toward storage limit when saved

**⭐ Favorite Button** (star icon)
- **Automatically saves the model** (sets `is_saved=1` and `is_favorited=1`)
- **Cannot be unfavorited or unsaved** - this is permanent!
- Once favorited, the Save button is disabled/hidden
- Always counts toward storage limit
- Protected from all deletion

### Three Model States

1. **Unsaved & Unfavorited** (default after generation)
   - Save button: Shows "Save"
   - Favorite button: Shows "Favorite"
   - **Auto-deleted after retention period** (36hr/14d/30d based on plan)
   - Can be manually deleted

2. **Saved & Unfavorited**
   - Save button: Shows "Unsave" (can toggle back to unsaved)
   - Favorite button: Shows "Favorite"
   - **Protected from auto-cleanup**
   - Counts toward storage limit
   - Can be manually unsaved or deleted

3. **Favorited & Saved** (permanent)
   - Save button: **Disabled/Hidden** (cannot unsave)
   - Favorite button: Shows "⭐ Favorited" (disabled)
   - **Cannot be unsaved until unfavorited**
   - **Cannot be unfavorited** - permanent lock!
   - Protected from all deletion
   - Always counts toward storage limit

### Visual Behavior Flow

```
New Model Generated
       |
       v
[Unsaved & Unfavorited] <-------- Can click "Save"
       |                                 |
       |                                 v
       |                          [Saved & Unfavorited]
       |                                 |
       |                                 |
       +-------> Click "Favorite" <-----+
                        |
                        v
              [Favorited & Saved]
                 (PERMANENT)
                 Cannot unsave
                 Cannot unfavorite

Auto-Cleanup Timer:
  - Unsaved models: Delete after 36hr/14d/30d
  - Saved models: Never auto-deleted
  - Favorited models: Never deleted (permanent)
```

### Database Schema
```sql
-- generated_models table
CREATE TABLE generated_models (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    model_path TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    file_size INTEGER,
    is_saved BOOLEAN DEFAULT 0,      -- Can be unsaved (unless favorited)
    is_favorited BOOLEAN DEFAULT 0,  -- Cannot be unfavorited (permanent)
    UNIQUE(model_path)
)
```

### UI Button Behavior Summary

**In Recent Models / Favorites Tab:**

Every model shows TWO buttons:

| State | Save Button | Favorite Button | Auto-Delete? |
|-------|-------------|-----------------|-------------|
| **Just Generated** | 🔖 "Save" (clickable) | ⭐ "Favorite" (clickable) | ✅ Yes (after 36hr/14d/30d) |
| **User Clicked Save** | 🔖 "Unsave" (clickable) | ⭐ "Favorite" (clickable) | ❌ No (protected) |
| **User Clicked Favorite** | 🔖 Disabled/Hidden | ⭐ "Favorited" (disabled) | ❌ No (permanent) |

**Key Rules:**
1. ⭐ Clicking "Favorite" automatically saves the model (permanent)
2. 🔖 "Save" only protects from auto-cleanup (can be unsaved later)
3. ⭐ Favorited models **cannot be unsaved** or unfavorited (locked forever)
4. ⏰ Only unsaved, unfavorited models get deleted by auto-cleanup timer

### API Endpoints
All endpoints require authentication and include **1-second delay** for rate limiting.

**Save Model**
```http
POST /api/models/save
Rate Limit: 30 per minute (1-second delay)
Body: { "model_path": "/path/to/model.glb" }
Response: { "success": true, "message": "Model saved" }
```

**Unsave Model**
```http
POST /api/models/unsave
Rate Limit: 30 per minute (1-second delay)
Body: { "model_path": "/path/to/model.glb" }
Response: { "success": true } OR { "error": "Cannot unsave favorited model" }
```

**Favorite Model** (automatically saves)
```http
POST /api/models/favorite
Rate Limit: 30 per minute (1-second delay)
Body: { "model_path": "/path/to/model.glb" }
Sets: is_favorited=1, is_saved=1 (permanent)
```

---

## Auto-Cleanup System

### Cleanup Priority
When storage limit is reached:

1. **First: Delete oldest unsaved models**
   - WHERE `is_saved = 0` AND `is_favorited = 0`
   - Oldest models deleted first (by `generated_at`)
   - Logged as `model_deleted_limit`

2. **If no unsaved models: Block action**
   - Error: "Storage limit reached (X models). Please unsave or delete some models to continue."
   - Logged as `storage_limit_reached`
   - User must manually unsave saved models

### Scheduled Cleanup
Runs every hour in background thread:

```python
# Only deletes models that are:
# 1. Older than retention period (36hr/14d/30d)
# 2. NOT saved (is_saved = 0)
# 3. NOT favorited (is_favorited = 0)

cleanup_old_models():
    WHERE generated_at < cutoff_time
    AND is_saved = 0
    AND is_favorited = 0
```

### Retention Periods
- **Free:** 36 hours (prevents data accumulation)
- **Standard:** 14 days
- **Pro:** 30 days
- **Staff:** Never deleted

---

## Activity Logging System

### Database Schema
```sql
CREATE TABLE user_activity_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,  -- JSON details
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)

-- Indexed for performance
CREATE INDEX idx_activity_user_time ON user_activity_log(user_id, timestamp DESC)
CREATE INDEX idx_activity_timestamp ON user_activity_log(timestamp)
```

### Event Types
**Generation Events**
- `generation_started` - Model generation begins
- `generation_completed` - Model successfully generated
- `generation_failed` - Generation failed

**Model Management Events**
- `model_saved` - User saved a model
- `model_unsaved` - User unsaved a model
- `model_favorited` - User favorited a model (permanent)

**Deletion Events**
- `model_deleted_manual` - User manually deleted
- `model_deleted_auto` - Auto-deleted by cleanup (retention expired)
- `model_deleted_limit` - Deleted due to storage limit

**Storage Events**
- `storage_limit_reached` - User hit storage capacity

### Log Retention
- **Automatic truncation:** 30 days
- **Cleanup runs:** Daily at midnight
- **Performance:** Indexed queries for fast retrieval

### API Endpoints
All endpoints require authentication and include **1-second delay**.

**Get User Activity**
```http
GET /api/user/activity?limit=100&type=generation_completed
Rate Limit: 30 per minute (1-second delay)
Response: {
  "success": true,
  "activity": [
    {
      "id": 123,
      "event_type": "generation_completed",
      "event_data": { "model_path": "/path/to/model.glb" },
      "timestamp": "2025-11-27T08:00:00"
    }
  ],
  "stats": {
    "total_generations": 45,
    "models_saved": 15,
    "total_deletions": 12
  },
  "count": 100
}
```

**Get Activity Statistics**
```http
GET /api/user/activity/stats?days=30
Rate Limit: 30 per minute (1-second delay)
Response: {
  "success": true,
  "stats": {
    "total_generations": 45,
    "failed_generations": 2,
    "models_saved": 15,
    "models_unsaved": 3,
    "models_favorited": 10,
    "manual_deletions": 5,
    "auto_deletions": 8,
    "limit_deletions": 2,
    "storage_limit_hits": 1,
    "period_days": 30
  }
}
```

**Get Recent Events**
```http
GET /api/user/activity/recent?types=generation_completed,model_saved&limit=20
Rate Limit: 30 per minute (1-second delay)
Response: {
  "success": true,
  "events": [...],
  "count": 20
}
```

---

## Rate Limiting with 1-Second Delays

### Implementation
All authenticated API endpoints include:
```python
@limiter.limit("30 per minute")  # 1-second minimum delay
def endpoint():
    time.sleep(1)  # Enforce 1-second delay
    # ... endpoint logic
```

### Limits by Endpoint Type
**User Activity Endpoints** (30/min = 1-second delay)
- `/api/user/activity`
- `/api/user/activity/stats`
- `/api/user/activity/recent`

**Security Endpoints** (30/min = 1-second delay)
- `/api/security/stats`
- `/api/security/recent-attacks`

**Model Management** (30/min = 1-second delay)
- `/api/models/save`
- `/api/models/unsave`
- `/api/models/favorite`

### Benefits
- **Prevents abuse:** 1-second minimum between requests
- **Fair usage:** All users get equal access
- **Server protection:** Prevents overload
- **Smooth UX:** Delay is imperceptible for normal use

---

## Storage Capacity Enforcement

### Registration Limits
When tier reaches capacity, new signups are blocked:

```python
# Check before registration
if free_users >= 200:
    return "Free tier at capacity (200/200). Upgrade to Standard or Pro!"
if standard_users >= 50:
    return "Standard tier at capacity (50/50). Upgrade to Pro!"
if pro_users >= 20:
    return "Pro tier at capacity (20/20). Please check back later!"
```

### Real-Time Capacity Display
Public API endpoint shows current capacity:
```http
GET /api/capacity
Response: {
  "free": { "current": 145, "max": 200, "available": 55 },
  "standard": { "current": 32, "max": 50, "available": 18 },
  "pro": { "current": 8, "max": 20, "available": 12 },
  "founder": { "count": 1, "email": "gdoman99@gmail.com" },
  "moderator": { "current": 2, "max": 5 },
  "admin": { "current": 1, "max": 3 },
  "total": { "current": 189, "max": 278, "percent_full": 68 }
}
```

---

## Key Points Summary

✅ **Smart Auto-Cleanup**
- Removes oldest **unsaved** models first
- Blocks action if all models are saved/favorited
- Clear error messages guide user

✅ **Permanent Favorites**
- Favorited models **cannot be unsaved**
- Protected from all deletion
- Permanent storage guarantee

✅ **Complete Activity Logging**
- All user actions logged (generations, saves, deletes)
- 30-day automatic log retention
- Fast indexed queries

✅ **1-Second Rate Limiting**
- Enforced on all authenticated endpoints
- Prevents abuse while maintaining smooth UX
- 30 requests per minute maximum

✅ **Accurate Storage Calculations**
- Based on actual save limits (32/150/500)
- Real-time capacity tracking
- Clear upgrade paths when capacity reached

✅ **Transparent Capacity Display**
- Shows current/max users per tier
- Storage utilization percentage
- Staff tier tracking included
