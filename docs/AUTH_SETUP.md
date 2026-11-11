# SlushAI 3D Modeller - Authentication Setup Guide

This guide will walk you through setting up Google OAuth authentication for SlushAI 3D Modeller.

## Overview

The authentication system includes:
- **Google OAuth 2.0** for user sign-in
- **User accounts** with unique IDs and profiles
- **Badge progression system** (Newcomer → Creator → Artist → Master → Legend)
- **Weekly quota limits** (10 free models per week)
- **User galleries** for screenshots
- **Session management** with secure cookies

## Prerequisites

- Python 3.8 or higher
- A Google Cloud account (free)
- SlushAI 3D Modeller installed and working

## Step 1: Create Google OAuth Credentials

### 1.1 Go to Google Cloud Console
Visit: https://console.cloud.google.com/

### 1.2 Create or Select a Project
- Click "Select a project" at the top
- Click "NEW PROJECT"
- Name it "SlushAI 3D Modeller" (or your preference)
- Click "CREATE"

### 1.3 Enable Required APIs
- In the left sidebar, go to **APIs & Services** → **Library**
- Search for "Google+ API" and enable it
- Search for "People API" and enable it

### 1.4 Create OAuth 2.0 Client ID
1. Go to **APIs & Services** → **Credentials**
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - Choose **External** (unless you have Google Workspace)
   - Fill in required fields:
     - **App name**: SlushAI 3D Modeller
     - **User support email**: Your email
     - **Developer contact**: Your email
   - Click **SAVE AND CONTINUE**
   - Skip scopes (click **SAVE AND CONTINUE**)
   - Add test users (your email) if still in testing mode
   - Click **SAVE AND CONTINUE**

4. Back at "Create OAuth client ID":
   - **Application type**: Web application
   - **Name**: SlushAI 3D Modeller Web Client
   - **Authorized JavaScript origins**:
     - http://localhost:5000
     - http://127.0.0.1:5000
   - **Authorized redirect URIs**:
     - http://localhost:5000/auth/callback
     - http://127.0.0.1:5000/auth/callback
   - Click **CREATE**

5. **Copy your credentials**:
   - You'll see a popup with your **Client ID** and **Client Secret**
   - Keep this window open or download the JSON

## Step 2: Configure Environment Variables

### 2.1 Edit the .env file
Open `/Users/TheRustySpoon/Desktop/Projects/Main projects/Lucifer_Modules/AI3DModeller/.env` and update:

```bash
# Replace these with your actual credentials from Google Cloud Console
GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-actual-client-secret
```

**Example:**
```bash
GOOGLE_CLIENT_ID=123456789012-abcdefghijklmnop.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-AbCdEfGhIjKlMnOpQrStUvWx
```

### 2.2 Verify SECRET_KEY
The `.env` file already has a generated `SECRET_KEY`. Keep it secure and don't share it.

## Step 3: Install Dependencies

All required packages should already be installed, but verify:

```bash
cd /Users/TheRustySpoon/Desktop/Projects/Main\ projects/Lucifer_Modules/AI3DModeller
pip install flask-login==0.6.3 authlib==1.6.5 python-dotenv==1.2.1 cryptography==46.0.3
```

## Step 4: Test the Authentication System

### 4.1 Restart the Server
If the server is already running, stop it (Ctrl+C) and restart:

```bash
python viewer/app.py
```

### 4.2 Test the Login Flow

1. **Visit the landing page**:
   - Open http://localhost:5000 in your browser
   - You should see the landing page with "Sign in with Google" button

2. **Sign in**:
   - Click "Sign in with Google"
   - Choose your Google account
   - Grant permissions if prompted
   - You should be redirected to the main viewer

3. **Verify user profile**:
   - Check the header - you should see:
     - Your name
     - Your Google profile picture
     - Badge: "Newcomer" (colored badge)
     - Quota: "0 / 10 this week"
     - Logout button

4. **Test protected routes**:
   - Try visiting http://localhost:5000/viewer directly (should work if logged in)
   - Log out, then try visiting /viewer again (should redirect to landing page)

5. **Test model generation with quota**:
   - Upload an image and generate a model
   - Watch the quota counter increase: "1 / 10 this week"
   - Take a screenshot (should save to your gallery)
   - Generate 9 more models to hit the limit
   - Try generating an 11th model - should show quota exceeded error

6. **Test logout**:
   - Click "Logout" button
   - Should redirect to landing page
   - Try accessing /viewer - should redirect back to landing

## Architecture

### Database Schema
Located at: `logs/users.db`

**Tables:**
- `users` - User profiles (google_id, email, name, picture, badge_level)
- `weekly_quotas` - Weekly usage tracking (resets every Monday)
- `usage_log` - Complete task history
- `user_gallery` - Saved screenshots

### Badge System
Badges are awarded automatically based on lifetime model completions:

| Badge Level | Name | Models Required | Color |
|-------------|------|-----------------|-------|
| 0 | Newcomer | 0-9 | Gray (#94a3b8) |
| 1 | Creator | 10-49 | Blue (#3b82f6) |
| 2 | Artist | 50-199 | Purple (#a855f7) |
| 3 | Master | 200-499 | Orange (#f97316) |
| 4 | Legend | 500+ | Gold (#eab308) |

### Quota System
- **Free tier**: 10 models per week
- **Resets**: Every Monday at 00:00 UTC
- **Only counts**: Successfully completed models
- **Failed tasks**: Do not count against quota

### Protected Routes
All routes except these require authentication:
- `/` (landing page)
- `/auth/login`
- `/auth/callback`
- `/api/health`

## Troubleshooting

### "Redirect URI mismatch" error
**Solution**: Check your Google Cloud Console redirect URIs match exactly:
- http://localhost:5000/auth/callback
- http://127.0.0.1:5000/auth/callback

### "Client ID not found" error
**Solution**: Verify your .env file has correct `GOOGLE_CLIENT_ID` and no extra spaces

### User profile not loading
**Solution**: 
1. Check browser console for errors
2. Verify `/api/user/profile` returns data: http://localhost:5000/api/user/profile
3. Clear cookies and log in again

### Quota not resetting
**Solution**: The quota resets automatically every Monday. To manually reset for testing:
```python
from src.ai3d.utils.user_manager import UserManager
um = UserManager('logs/users.db')
um.cursor.execute('DELETE FROM weekly_quotas WHERE user_id = "your-user-id"')
um.conn.commit()
```

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never commit .env file to git** - It's already in .gitignore
2. **Keep SECRET_KEY secret** - Used for session encryption
3. **Use HTTPS in production** - Update `SESSION_COOKIE_SECURE = True` in app.py
4. **Restrict OAuth scopes** - Only request email, profile, and openid
5. **Validate redirect URIs** - Don't allow wildcard redirects

## Production Deployment

When deploying to production (e.g., Heroku, AWS, Google Cloud):

1. **Update redirect URIs** in Google Cloud Console:
   ```
   https://yourdomain.com/auth/callback
   ```

2. **Set environment variables** on your hosting platform

3. **Enable HTTPS**:
   ```python
   # In viewer/app.py
   app.config['SESSION_COOKIE_SECURE'] = True
   ```

4. **Use production database** instead of SQLite if needed

5. **Set proper CORS origins** instead of wildcard

## API Endpoints

### Authentication
- `GET /` - Landing page (public)
- `GET /auth/login` - Initiate OAuth flow
- `GET /auth/callback` - OAuth callback handler
- `GET /auth/logout` - Log out user

### Protected APIs
- `GET /api/user/profile` - Get user profile and quota
- `GET /api/user/gallery` - Get user's screenshot gallery
- `POST /api/generate` - Generate 3D model (checks quota)
- `POST /api/screenshot` - Save screenshot to gallery
- `GET /api/models` - List available models
- `GET /api/queue/status` - Get task queue status

## Next Steps

- **Custom domains**: Add your production domain to Google OAuth
- **Payment integration**: Add Stripe/PayPal for premium tiers
- **Email notifications**: Notify users when quota resets
- **Admin dashboard**: Create admin panel to manage users
- **Analytics**: Track user engagement and popular features

## Support

If you encounter issues:
1. Check the server logs in `logs/viewer.log`
2. Check browser console for JavaScript errors
3. Verify all dependencies are installed
4. Review the .env file for typos

---

**Status**: ✅ Authentication system fully implemented and ready for testing

**Last Updated**: November 26, 2025
