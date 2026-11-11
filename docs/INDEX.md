# SlushAI 3D Modeller - Complete Documentation

Welcome to the complete documentation for SlushAI 3D Modeller! This page helps you find exactly what you need, whether you're a beginner or an advanced user.

---

## 📚 Documentation Categories

### 🚀 **Getting Started** (New Users Start Here!)

Perfect if you're brand new and want to understand the basics.

#### [README.md](../README.md)
**What is this?** The main introduction to SlushAI 3D Modeller  
**You'll learn:**
- What the app does (turn images into 3D models)
- How to install it on your computer
- Quick start guide to generate your first model
- Basic features overview

**Read this first if:** You've never used the app before

---

#### [AUTH_SETUP.md](AUTH_SETUP.md)
**What is this?** Complete guide to setting up Google sign-in  
**You'll learn:**
- How to create Google OAuth credentials (step-by-step with screenshots)
- How to configure the .env file with your credentials
- How to test the login system
- Troubleshooting common login issues

**Read this if:** You want users to sign in with Google accounts

**Time needed:** 15-20 minutes  
**Difficulty:** ⭐⭐ Beginner-friendly (we walk you through everything!)

---

### 🎨 **User Guides** (How to Use the App)

Learn how to actually use SlushAI 3D Modeller as a regular user.

#### USER_GUIDE.md *(Coming Soon — not yet written)*
**What is this?** Complete user manual for creators  
**You'll learn:**
- How to upload images and generate 3D models
- Understanding quality settings (Basic, Higher, Max resolution)
- Using the 3D viewer controls
- Taking and saving screenshots
- Managing your weekly quota
- Upgrading your plan

**Read this if:** You're a content creator using the app

---

### 💻 **Developer Guides** (For Technical Users)

Technical documentation for developers who want to understand how everything works.

#### [API_USAGE.md](API_USAGE.md)
**What is this?** Complete API reference for developers  
**You'll learn:**
- Every API endpoint available
- What each endpoint does in plain English
- Required parameters for each request
- Example requests and responses
- Authentication requirements
- Rate limits for each endpoint

**Read this if:** You want to build apps that connect to SlushAI 3D Modeller

**Difficulty:** ⭐⭐⭐ Requires basic programming knowledge

---

#### [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md)
**What is this?** Deep dive into advanced features  
**You'll learn:**
- How the badge reward system works
- Rate limiting configuration
- Maintenance mode setup
- Subscription plan structure
- Weekly quota reset mechanism
- Database schema details

**Read this if:** You're a developer maintaining or extending the system

**Difficulty:** ⭐⭐⭐⭐ For experienced developers

---

#### [CONCURRENT_PROCESSING.md](CONCURRENT_PROCESSING.md)
**What is this?** How the task queue handles multiple users  
**You'll learn:**
- How 2-3 workers process models simultaneously
- CPU allocation (40% each normally, 30%+30%+20% under load)
- Adaptive scaling when queue backs up
- Queue status monitoring

**Read this if:** You want to understand performance and scaling

**Difficulty:** ⭐⭐⭐ Technical but explained simply

---

#### [ADAPTIVE_SCALING.md](ADAPTIVE_SCALING.md)
**What is this?** How the system handles heavy traffic  
**You'll learn:**
- When the 3rd worker activates (10+ queued tasks)
- CPU power distribution between workers
- Capacity calculations (960-1440 models/day)
- Performance monitoring

**Read this if:** You're worried about handling 1000+ users per day

**Difficulty:** ⭐⭐⭐ Technical concepts explained clearly

---

#### [ANALYTICS_SETUP.md](ANALYTICS_SETUP.md)
**What is this?** Complete analytics tracking and reporting system  
**You'll learn:**
- What metrics are tracked automatically
- How to generate monthly reports
- Setting up automated cron jobs
- Database schema and data retention
- Privacy and GDPR compliance
- Monitoring best practices and alert thresholds

**Read this if:** You want to track site performance and user behavior

**Difficulty:** ⭐⭐⭐ Technical but well documented

---

### 🤖 **AI Agent Guides** (For AI Assistants)

Special guides written for AI assistants who help maintain the codebase.

#### [AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)
**What is this?** Instructions for AI coding assistants  
**You'll learn:**
- Project structure and file organization
- Common modification patterns
- Testing procedures
- How to safely make changes

**Read this if:** You're an AI assistant helping with development

---

### 💳 **Business Documentation**

Information about pricing, subscriptions, and payments.

#### [Pricing page](/pricing) *(live page — no PRICING.md doc exists)*
**What is this?** Complete pricing and subscription guide  
**You'll learn:**
- All available plans (Free, Standard, Pro)
- What's included in each plan
- How the $1 quick refill works
- Yearly savings calculations
- Payment processing with Stripe
- Refund and cancellation policies

**Read this if:** You want to understand costs and billing

**Difficulty:** ⭐ Anyone can understand this!

---

## 🔍 Quick Reference Guides

### Common Tasks

| I want to... | Read this guide | Section |
|--------------|----------------|---------|
| Install the app | [README.md](../README.md) | Installation |
| Set up Google login | [AUTH_SETUP.md](AUTH_SETUP.md) | Full guide |
| Generate my first 3D model | [README.md](../README.md) | Quick Start |
| Understand API endpoints | [API_USAGE.md](API_USAGE.md) | All sections |
| Fix authentication issues | [AUTH_SETUP.md](AUTH_SETUP.md) | Troubleshooting |
| Upgrade my subscription | [Pricing page](/pricing) | Plans section |
| Build an integration | [API_USAGE.md](API_USAGE.md) | Full guide |
| Understand badge rewards | [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) | Badge System |
| Configure rate limits | [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) | Rate Limiting |
| Handle server overload | [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) | Maintenance Mode |
| Track site analytics | [ANALYTICS_SETUP.md](ANALYTICS_SETUP.md) | Full guide |
| Generate monthly reports | [ANALYTICS_SETUP.md](ANALYTICS_SETUP.md) | Monthly Reports |

---

## 📖 API Documentation (For Developers)

Complete reference for all API endpoints. **Explained like you're 5!**

### Authentication Endpoints

#### `POST /auth/login`
**What it does:** Sends you to Google to sign in  
**Who can use it:** Anyone (public)  
**What you need:** Nothing! Just visit this URL  
**What happens:** Redirects to Google sign-in page  
**Example:** `http://localhost:5000/auth/login`

---

#### `GET /auth/callback`
**What it does:** Google sends you back here after signing in  
**Who can use it:** Automatic (Google uses this)  
**What you need:** Nothing, Google handles it  
**What happens:** Creates your account or logs you in, then sends you to /viewer

---

#### `GET /auth/logout`
**What it does:** Signs you out  
**Who can use it:** Logged-in users only  
**What you need:** Just be logged in  
**What happens:** Clears your session and sends you back to landing page  
**Example:** `http://localhost:5000/auth/logout`

---

### User Profile Endpoints

#### `GET /api/user/profile`
**What it does:** Gets all your account info  
**Who can use it:** Logged-in users only  
**Rate limit:** None (you can check as often as you want)  

**What you get back:**
```json
{
  "user_id": 123,
  "email": "you@example.com",
  "name": "Your Name",
  "picture": "https://your-avatar-url.com/photo.jpg",
  "badge_level": 1,
  "badge_name": "Creator",
  "badge_color": "#3b82f6",
  "total_models": 15,
  "joined_date": "2025-11-26T10:30:00",
  "quota": {
    "used_this_week": 3,
    "weekly_limit": 10,
    "remaining": 7,
    "reset_date": "2025-12-02T00:00:00"
  }
}
```

**What each field means:**
- `user_id`: Your unique ID number
- `email`: Your Google email address
- `name`: Your display name
- `picture`: URL to your profile picture
- `badge_level`: Number 0-4 (0=Newcomer, 1=Creator, 2=Artist, 3=Master, 4=Legend)
- `badge_name`: Text name of your badge
- `badge_color`: Hex color code for your badge
- `total_models`: How many models you've made ever
- `joined_date`: When you created your account
- `quota.used_this_week`: How many models you've made this week
- `quota.weekly_limit`: Your max for this week (10, 40, or 120)
- `quota.remaining`: How many you can still make
- `quota.reset_date`: When your quota resets to zero

**Example in JavaScript:**
```javascript
const response = await fetch('/api/user/profile');
const user = await response.json();
console.log(`Hello ${user.name}!`);
console.log(`You have ${user.quota.remaining} models left this week`);
```

---

#### `GET /api/user/gallery`
**What it does:** Gets all your saved screenshots  
**Who can use it:** Logged-in users only  
**Rate limit:** None  

**What you get back:**
```json
[
  {
    "filename": "screenshot_20251126_103045.png",
    "file_path": "outputs/screenshots/screenshot_20251126_103045.png",
    "created_at": "2025-11-26T10:30:45"
  },
  {
    "filename": "screenshot_20251126_091523.png",
    "file_path": "outputs/screenshots/screenshot_20251126_091523.png",
    "created_at": "2025-11-26T09:15:23"
  }
]
```

**What each field means:**
- `filename`: Name of the screenshot file
- `file_path`: Where it's stored on the server
- `created_at`: When you took the screenshot

---

### Model Generation Endpoints

#### `POST /api/generate`
**What it does:** Creates a 3D model from your image  
**Who can use it:** Logged-in users only  
**Rate limit:** **1 request every 2 seconds** (prevents spam)  
**Quota:** Counts towards your weekly limit (if successful)

**What you need to send:**
```javascript
const formData = new FormData();
formData.append('image', fileInput.files[0]);  // Your image file
formData.append('backend', 'triposr');          // Which AI to use

fetch('/api/generate', {
  method: 'POST',
  body: formData
});
```

**Parameters explained:**
- `image`: The image file (JPG, PNG, WebP)
- `backend`: Which AI model to use
  - `'triposr'` = Best quality, full 3D (recommended!)
  - `'native'` = Fast but 2.5D only
  - `'proc'` = Fallback cube (for testing)

**What you get back (success):**
```json
{
  "success": true,
  "task_id": "abc123-def456",
  "status": {
    "status": "queued",
    "position": 3,
    "estimated_wait": 360
  }
}
```

**What you get back (quota exceeded):**
```json
{
  "error": "Weekly quota exceeded",
  "quota": {
    "used_this_week": 10,
    "weekly_limit": 10,
    "remaining": 0,
    "reset_date": "2025-12-02T00:00:00"
  }
}
```
**HTTP Status:** 429 (Too Many Requests)

**What you get back (rate limited):**
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 2
}
```
**HTTP Status:** 429 (Too Many Requests)

**How it works:**
1. You send an image
2. System checks your quota (do you have models left?)
3. If yes, adds to queue
4. Returns task_id to track progress
5. Processing takes 2-3 minutes
6. When done, you get a WebSocket notification
7. If successful, counts towards your quota

---

#### `GET /api/task/{task_id}/status`
**What it does:** Checks how your model generation is going  
**Who can use it:** Logged-in users only  
**Rate limit:** None (check as often as you want!)

**Example:**
```javascript
const response = await fetch('/api/task/abc123-def456/status');
const status = await response.json();
```

**What you get back:**
```json
{
  "task_id": "abc123-def456",
  "status": "processing",
  "position": 0,
  "estimated_wait": 120,
  "progress": 45
}
```

**Status values:**
- `"queued"`: Waiting in line
- `"processing"`: Being generated right now
- `"completed"`: Done! Model is ready
- `"failed"`: Something went wrong
- `"cancelled"`: You cancelled it

**Other fields:**
- `position`: How many tasks ahead of you (0 = you're next!)
- `estimated_wait`: Seconds until completion
- `progress`: Percentage done (0-100)

---

#### `POST /api/task/{task_id}/cancel`
**What it does:** Cancels a queued model generation  
**Who can use it:** Logged-in users only  
**Rate limit:** 1 request every 2 seconds  
**Important:** Cancelled tasks DON'T count towards quota!

**Example:**
```javascript
fetch('/api/task/abc123-def456/cancel', {
  method: 'POST'
});
```

**What you get back:**
```json
{
  "success": true,
  "message": "Task cancelled"
}
```

**Note:** Can only cancel if status is "queued". Can't cancel if already processing.

---

### Queue Management Endpoints

#### `GET /api/queue/status`
**What it does:** Shows how busy the server is  
**Who can use it:** Logged-in users only  
**Rate limit:** None

**What you get back:**
```json
{
  "queued_count": 5,
  "active_workers": 2,
  "third_worker_active": false,
  "current_tasks": {
    "0": {"task_id": "abc123", "started": 120},
    "1": {"task_id": "def456", "started": 45}
  }
}
```

**What each field means:**
- `queued_count`: How many models waiting to be made
- `active_workers`: How many workers running (1, 2, or 3)
- `third_worker_active`: Is backup worker helping? (true/false)
- `current_tasks`: What's being processed right now

**How to interpret:**
- `queued_count < 5`: Server available, quick generation
- `queued_count 5-10`: Moderate load, ~5-10 min wait
- `queued_count 10-15`: High load, ~15-20 min wait
- `queued_count > 15`: Overloaded, maintenance mode triggered

---

### Screenshot Endpoints

#### `POST /api/screenshot`
**What it does:** Saves a screenshot of your 3D model  
**Who can use it:** Logged-in users only  
**Rate limit:** 1 request every 2 seconds

**What you need to send:**
```javascript
// Get image data from canvas
const dataURL = canvas.toDataURL('image/png');

fetch('/api/screenshot', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ image: dataURL })
});
```

**What you get back:**
```json
{
  "success": true,
  "filename": "screenshot_20251126_103045.png",
  "path": "outputs/screenshots/screenshot_20251126_103045.png"
}
```

**What happens:**
1. Image data is decoded from base64
2. Saved to `outputs/screenshots/` folder
3. Added to your personal gallery
4. Tracked in database for your user_id

---

### Model Listing Endpoints

#### `GET /api/models`
**What it does:** Lists all generated 3D models  
**Who can use it:** Logged-in users only  
**Rate limit:** None

**What you get back:**
```json
[
  {
    "name": "temp_photo_preview",
    "path": "outputs/temp_photo_preview.obj",
    "refined_path": "outputs/temp_photo_refined.obj",
    "vertices": 215000,
    "faces": 107000,
    "size": 15340000,
    "modified": 1732617845
  }
]
```

**What each field means:**
- `name`: Model filename without extension
- `path`: Preview model location (lower quality, textured)
- `refined_path`: High quality version (if available)
- `vertices`: Number of 3D points in the model
- `faces`: Number of triangles in the model
- `size`: File size in bytes
- `modified`: Unix timestamp when created

---

## 🔐 Authentication & Security

### How Authentication Works (Simple Explanation)

1. **You visit the site** → Shows landing page with "Sign in with Google"
2. **You click sign in** → Redirects to `/auth/login`
3. **Google asks permission** → "Allow SlushAI to access your email and name?"
4. **You click Allow** → Google sends you to `/auth/callback`
5. **Server creates your account** → Saved in database with unique user_id
6. **You're logged in!** → Cookie stored in browser
7. **All requests authenticated** → Server knows who you are

### Rate Limiting (Prevents Abuse)

**Why it exists:** Stops people from spamming the server with requests

**Limits:**
- **Landing page:** 100 requests/minute per IP address
- **Generate model:** 1 request every 2 seconds per user
- **Screenshot:** 1 request every 2 seconds per user
- **Cancel task:** 1 request every 2 seconds per user

**What happens if you exceed:**
- HTTP status 429 (Too Many Requests)
- Response includes `retry_after` in seconds
- Wait that long, then try again

**Example response:**
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 2
}
```

### Security Features

✅ **Passwords:** Never stored (Google handles login)  
✅ **Sessions:** Encrypted cookies, expire after 30 days  
✅ **IP tracking:** Hashed with SHA256 (GDPR compliant)  
✅ **Rate limiting:** Prevents API abuse  
✅ **Login required:** Can't generate models without account  
✅ **HTTPS ready:** Session cookies marked secure for production  

---

## 💰 Pricing & Quotas (Simple Explanation)

### What's a "Quota"?

A quota is like a monthly phone plan's minutes. You get a certain number of models you can make each week, then it resets on Monday.

### Plans

| Plan | Cost | Models/Week | When to Choose |
|------|------|-------------|----------------|
| **Free** | $0 | 10 | Trying the app, casual use |
| **Standard** | $3.47/week<br>$72/year | 40 | Regular creators, hobbyists |
| **Pro** | $7.89/week<br>$164/year | 120 | Power users, professionals |
| **Refill** | $1 one-time | +10 models | Emergency boost |

### How Quotas Work

**Example:**
- You're on Free plan (10/week)
- Monday morning: Quota resets to 0/10
- You make 3 models → Now 3/10 used
- Wednesday: Make 5 more → Now 8/10 used
- Quota exceeded alert at 10/10
- Next Monday: Resets back to 0/10

### Quick Refills

**What is it?** Add 10 models instantly for $1

**How it works:**
```
Current quota: 8/10 used
Buy $1 refill → 8/20 used (limit increased to 20!)
Still have 12 models left this week
```

**Limits:**
- Max 10 refills per week
- Refills don't carry over to next week
- Monday reset includes refills (back to base 10/40/120)

---

## 🏆 Badge System (Gamification)

### How Badges Work

As you create more models, you level up! Each level gives you a **one-time bonus**.

| Badge | Level | Models Needed | Reward | Color |
|-------|-------|---------------|---------|--------|
| 🆕 Newcomer | 0 | 0-9 | None | Gray |
| 🎨 Creator | 1 | 10-49 | **Quota reset!** | Blue |
| 🖌️ Artist | 2 | 50-199 | **Quota reset!** | Purple |
| 👑 Master | 3 | 200-499 | **Quota reset!** | Orange |
| ⭐ Legend | 4 | 500+ | **Quota reset!** | Red |

### Example Journey

```
Start: 0 models → Newcomer badge
Make 10 models → Creator badge! → Quota resets (free 10 models!)
Make 50 total → Artist badge! → Quota resets again!
Make 200 total → Master badge! → Another quota reset!
Make 500 total → Legend badge! → Final quota reset!
```

### Important Notes

- Rewards granted **once per badge** (can't farm resets)
- Only counts **successful** models (failed don't count)
- Badge progression tracked forever (doesn't reset)

---

## 🚨 Error Codes Explained

| HTTP Code | What It Means | What To Do |
|-----------|---------------|------------|
| **200** | Success! | Everything worked |
| **400** | Bad Request | Check your parameters |
| **401** | Unauthorized | You need to log in |
| **403** | Forbidden | You don't have permission |
| **404** | Not Found | URL is wrong |
| **429** | Too Many Requests | Slow down! Wait a bit |
| **500** | Server Error | Not your fault, try again later |

---

## 📞 Support & Help

### Where to Get Help

1. **Check this documentation first!** Most answers are here
2. **GitHub Issues:** Report bugs at the repository
3. **Email Support:** (Configure in your .env)

### Common Issues

**Problem:** "Sign in with Google" doesn't work  
**Solution:** Check [AUTH_SETUP.md](AUTH_SETUP.md) troubleshooting section

**Problem:** "Quota exceeded" error  
**Solution:** 
- Wait until Monday for reset, OR
- Buy a $1 refill, OR
- Upgrade to Standard/Pro plan

**Problem:** Model quality is bad  
**Solution:** Make sure you selected "TripoSR" backend (not "native")

**Problem:** Generation stuck at 99%  
**Solution:** This is normal! Final texture baking takes time

---

## 🔧 For Developers

### Quick Start Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your Google OAuth credentials

# Run development server
python viewer/app.py

# Server starts at http://localhost:5000
```

### File Structure

```
AI3DModeller/
├── viewer/              # Web interface
│   ├── app.py          # Main Flask server
│   ├── viewer.html     # 3D viewer interface
│   ├── landing.html    # Login page
│   ├── pricing.html    # Subscription plans
│   └── maintenance.html # Overload page
├── src/ai3d/
│   └── utils/
│       ├── user_manager.py    # User accounts & quotas
│       ├── task_queue.py      # Job processing
│       └── visitor_tracker.py # Analytics
├── docs/               # All documentation
└── logs/              # Database & log files
    ├── users.db       # User accounts
    ├── visitors.db    # Analytics
    └── viewer.log     # Server logs
```

### Database Schema

See [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) for complete schema documentation.

---

## 📊 Monitoring & Analytics

### Log Files

**Location:** `logs/viewer.log`  
**Max entries:** 2560 (auto-truncates)  
**Format:** JSON per line

**Example log entry:**
```json
{
  "timestamp": "2025-11-26T10:30:45",
  "session": "20251126_103000",
  "type": "generation_complete",
  "details": {
    "user_id": 123,
    "task_id": "abc123",
    "filename": "photo.jpg",
    "duration": 180
  }
}
```

### Analytics Database

**Location:** `logs/visitors.db`  
**Max requests:** 2560 (auto-cleans)  
**Tracks:** IP (hashed), endpoints, response times, user agents

---

## 🎓 Learning Path

### If You're New to Web Development

1. Read [README.md](../README.md) to understand what the app does
2. Follow [AUTH_SETUP.md](AUTH_SETUP.md) to set up login
3. Play with the app as a user
4. Read [API_USAGE.md](API_USAGE.md) to understand endpoints
5. Try making simple API calls with `curl` or JavaScript

### If You're An Experienced Developer

1. Skim [README.md](../README.md) for overview
2. Read [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) for architecture
3. Review [API_USAGE.md](API_USAGE.md) for integration points
4. Check [CONCURRENT_PROCESSING.md](CONCURRENT_PROCESSING.md) for performance
5. Dive into source code with context

### If You're An AI Assistant

1. Read [AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md) first
2. Reference this INDEX.md for questions
3. Check [API_USAGE.md](API_USAGE.md) for endpoints
4. Review [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) for complex features

---

## 🏁 Conclusion

This documentation is designed to help **everyone** — from complete beginners to expert developers. 

**Key principle:** If you don't understand something, it's our fault (not yours!), and we want to fix it.

**Contributing:** Found something confusing? Please open an issue or submit a documentation improvement!

---

**Last Updated:** November 26, 2025  
**Version:** 2.0  
**Maintained By:** SlushAI Team  
**License:** MIT
