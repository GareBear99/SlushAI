# Support System Documentation

**SlushAI 3D Modeller - Integrated Support and Email Management**

Last Updated: November 27, 2025

---

## Overview

SlushAI implements a comprehensive support system with built-in email tracking, allowing users to submit support requests and privileged accounts (founder/admin/moderator) to manage incoming and outgoing emails through the platform.

---

## Architecture

### Components

1. **Support Forms**
   - Public support form (landing page)
   - Member support form (authenticated users in viewer)
   
2. **Email Tracking System**
   - `EmailManager` class for logging all inbound and outbound emails
   - SQLite database (`logs/emails.db`) with `emails` and `email_threads` tables
   - Automatic logging of verification emails, password reset emails, and support requests

3. **API Endpoints**
   - `/api/support/submit` - Submit support requests (public or member)
   - Future: `/api/emails/*` - Email management for privileged users

---

## Support Forms

### Public Support Form (Landing Page)

**Location:** `viewer/landing.html`

**Features:**
- Floating button (💬) in bottom-right corner
- Modal popup with form fields:
  - Name (required)
  - Email (required)
  - Message/Issue Description (required)
- Available to all visitors (no authentication required)
- Rate Limited: 5 requests per hour per IP address

**Implementation:**
```javascript
// Open modal
openSupportModal()

// Close modal  
closeSupportModal()

// Submits to /api/support/submit with is_member: false
```

### Member Support Form (Viewer)

**Location:** `viewer/viewer.html`

**Features:**
- Same floating button UI (💬)
- Modal popup with simplified form:
  - Message/Issue Description (required)
  - Name and email auto-populated from user profile
- Only available to authenticated users
- Rate Limited: 5 requests per hour per user

**Implementation:**
```javascript
// Fetches user profile automatically
const profile = await fetch('/api/user/profile');

// Submits to /api/support/submit with is_member: true
```

---

## Email Tracking System

### EmailManager Class

**Location:** `src/ai3d/utils/email_manager.py`

**Database Schema:**

#### `emails` Table
```sql
CREATE TABLE emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,           -- 'inbound' or 'outbound'
    from_email TEXT NOT NULL,
    to_email TEXT NOT NULL,
    subject TEXT,
    body_text TEXT,
    body_html TEXT,
    email_type TEXT,                   -- 'verification', 'password_reset', 'support_request', etc.
    thread_id INTEGER,                 -- Foreign key to email_threads
    created_at TEXT NOT NULL,
    read_at TEXT                       -- Timestamp when email was read
)
```

#### `email_threads` Table
```sql
CREATE TABLE email_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    participants TEXT NOT NULL,        -- JSON array of email addresses
    first_email_id INTEGER,
    last_email_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

### Email Types

| Type | Direction | Description |
|------|-----------|-------------|
| `verification` | Outbound | Email verification codes |
| `password_reset` | Outbound | Password reset links |
| `pin_login` | Outbound | PIN codes for privileged login |
| `support_request` | Inbound | Support form submissions |
| `support_response` | Outbound | Responses to support requests |

### Methods

#### `log_outbound_email()`
```python
email_manager.log_outbound_email(
    to_email="user@example.com",
    from_email="support@slushai.com",
    subject="Your Subject",
    body_text="Plain text version",
    body_html="<html>HTML version</html>",
    email_type="verification",
    thread_id=None  # Optional
)
```

#### `log_inbound_email()`
```python
email_manager.log_inbound_email(
    from_email="user@example.com",
    to_email="support@slushai.com",
    subject="Support Request",
    body_text="User's message",
    body_html=None,
    email_type="support_request",
    thread_id=None  # Optional
)
```

#### `get_emails()`
```python
emails = email_manager.get_emails(
    direction="inbound",     # Optional: 'inbound', 'outbound', or None for all
    email_type="support_request",  # Optional filter
    unread_only=True,        # Optional: only unread emails
    limit=50,                # Optional: max results
    offset=0                 # Optional: pagination offset
)
```

#### `get_threads()`
```python
threads = email_manager.get_threads(
    limit=50,
    offset=0
)
```

#### `get_email_stats()`
```python
stats = email_manager.get_email_stats()
# Returns:
# {
#     'total_emails': 150,
#     'inbound_count': 75,
#     'outbound_count': 75,
#     'unread_count': 10,
#     'support_requests': 25,
#     'threads_count': 30
# }
```

---

## API Endpoints

### POST `/api/support/submit`

Submit a support request.

**Rate Limit:** 5 requests per hour (IP-based for public, user-based for members)

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "message": "Description of the issue",
  "is_member": false
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Support request submitted successfully"
}
```

**Response (Error):**
```json
{
  "error": "All fields are required"
}
```

**Status Codes:**
- `200` - Success
- `400` - Missing required fields
- `429` - Rate limit exceeded
- `500` - Server error

### Future: Email Management Endpoints

**Planned endpoints for privileged users:**

#### GET `/api/emails`
Get paginated list of emails with optional filters.

**Query Parameters:**
- `direction` - Filter by 'inbound' or 'outbound'
- `email_type` - Filter by email type
- `unread_only` - Boolean to show only unread
- `limit` - Max results (default 50)
- `offset` - Pagination offset

**Requires:** Privileged account (founder/admin/moderator) + PIN authentication

#### GET `/api/emails/threads`
Get email threads grouped by conversation.

**Requires:** Privileged account + PIN authentication

#### POST `/api/emails/mark-read`
Mark email(s) as read.

**Request Body:**
```json
{
  "email_ids": [1, 2, 3]
}
```

**Requires:** Privileged account + PIN authentication

#### POST `/api/emails/compose`
Send a new email from the master email.

**Request Body:**
```json
{
  "to": "user@example.com",
  "subject": "Response to your request",
  "body_text": "Plain text version",
  "body_html": "<html>HTML version</html>",
  "reply_to_id": 123  // Optional: reply to existing email
}
```

**Requires:** Privileged account + PIN authentication

---

## Integration with User Manager

### Automatic Email Logging

The `UserManager` class automatically logs all emails it sends when an `EmailManager` instance is provided:

**Initialization:**
```python
from src.ai3d.utils.email_manager import EmailManager
from src.ai3d.utils.user_manager import UserManager

email_manager = EmailManager('logs/emails.db')
user_manager = UserManager(
    'logs/users.db', 
    jwt_secret='...',
    email_manager=email_manager  # Pass email_manager
)
```

**Email Types Logged:**
1. **Verification Emails** - Automatically logged when `send_verification_email()` is called
2. **Password Reset Emails** - Automatically logged when `send_password_reset_email()` is called
3. **PIN Login Emails** - Automatically logged when privileged users log in

**Example:**
```python
# This call automatically logs to email_manager
success, message = user_manager.send_verification_email(
    email="user@example.com",
    code="123456"
)

# Email is now tracked in emails.db with type 'verification'
```

---

## Development Mode

When SMTP is not configured (email credentials not in `.env`), the system operates in development mode:

### Features:
1. **Console Logging**
   - PINs printed to console: `🔑 LOGIN PIN: 123456`
   - Password reset links printed to console
   
2. **Email Tracking Still Works**
   - All emails are still logged to `emails.db`
   - Email tracking independent of SMTP configuration
   
3. **Support Forms Work**
   - Support requests logged even without email delivery
   - Useful for development and testing

---

## Security

### Rate Limiting
- **Public Support:** 5 requests per hour per IP
- **Member Support:** 5 requests per hour per user
- **Email Management:** 30 requests per minute with 1-second delay

### Access Control
- Support forms: Public access
- Email viewing: Requires privileged account (founder/admin/moderator)
- Email management: Requires privileged account + PIN authentication (session['pin_authenticated'] = True)

### Data Protection
- Emails stored in local SQLite database
- No external email services for storage
- Proper escaping of HTML content
- SQL injection prevention via parameterized queries

---

## Future Enhancements

### Phase 1: Email Management UI (Planned)
- **Email Management Interface** (`viewer/email_management.html`)
  - Inbox view (unread/all)
  - Sent emails view
  - Thread view for conversations
  - Compose new email form
  - Reply functionality
  - Search and filters
  
- **Access Control**
  - Only accessible to founder/admin/moderator
  - Requires PIN authentication
  - Session timeout after 2 hours

### Phase 2: Advanced Features (Future)
- Email templates for common responses
- Auto-categorization of support requests
- Priority/urgency tagging
- Assignment to specific moderators/admins
- Notification system for new support requests
- Email forwarding to external addresses
- SMTP configuration UI for admins

### Phase 3: Analytics (Future)
- Support request trends
- Response time metrics
- Common issue categorization
- User satisfaction tracking

---

## Usage Examples

### Submit Public Support Request
```javascript
// From landing page
const response = await fetch('/api/support/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        name: "John Doe",
        email: "john@example.com",
        message: "I can't upload images larger than 10MB",
        is_member: false
    })
});
```

### Submit Member Support Request
```javascript
// From viewer (authenticated)
const profile = await fetch('/api/user/profile').then(r => r.json());

const response = await fetch('/api/support/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        name: profile.name,
        email: profile.email,
        message: "My model generation failed at 87%",
        is_member: true
    })
});
```

### Check Email Stats (Backend)
```python
from src.ai3d.utils.email_manager import EmailManager

email_manager = EmailManager('logs/emails.db')
stats = email_manager.get_email_stats()

print(f"Total emails: {stats['total_emails']}")
print(f"Unread support requests: {stats['unread_count']}")
print(f"Total support requests: {stats['support_requests']}")
```

### Get Recent Support Requests (Backend)
```python
support_requests = email_manager.get_emails(
    direction='inbound',
    email_type='support_request',
    unread_only=True,
    limit=10
)

for email in support_requests:
    print(f"From: {email['from_email']}")
    print(f"Subject: {email['subject']}")
    print(f"Message: {email['body_text']}")
    print(f"Received: {email['created_at']}")
    print("---")
```

---

## Troubleshooting

### Support form not submitting
1. Check browser console for JavaScript errors
2. Verify rate limit not exceeded (429 error)
3. Check network tab for request/response
4. Ensure all required fields are filled

### Emails not being logged
1. Verify `EmailManager` is passed to `UserManager`
2. Check `logs/emails.db` exists and is writable
3. Check server logs for errors
4. Verify email_manager.log_*_email() is being called

### Development mode not showing PINs
1. Verify SMTP credentials are NOT in `.env`
2. Check console/terminal output, not browser console
3. Look for lines starting with 🔑 LOGIN PIN

---

## Files Modified

### Core Implementation
- `src/ai3d/utils/email_manager.py` - Email tracking system
- `src/ai3d/utils/user_manager.py` - Integration with email logging
- `viewer/app.py` - Support API endpoint and manager initialization

### Frontend
- `viewer/landing.html` - Public support form
- `viewer/viewer.html` - Member support form

### Documentation
- `docs/SUPPORT_SYSTEM.md` - This file
- `docs/RATE_LIMITS.md` - Updated with support endpoint limits

---

## Database Location

```
logs/
├── emails.db           # Email tracking database
├── users.db            # User accounts and authentication
├── visitors.db         # Visitor tracking
├── analytics.db        # Usage analytics
├── crypto_payments.db  # Payment tracking
├── issues.db           # Community issues board
├── security.db         # Security monitoring
├── activity.db         # User activity logs
└── favorites.db        # Favorite models
```

---

## Summary

The SlushAI support system provides:

✅ **Public Support Form** - Available on landing page for all visitors  
✅ **Member Support Form** - Simplified form for authenticated users  
✅ **Email Tracking** - All emails logged to database  
✅ **Automatic Integration** - Verification and password reset emails auto-tracked  
✅ **Rate Limiting** - 5 requests/hour to prevent abuse  
✅ **Development Mode** - Works without SMTP configuration  
✅ **Security** - IP-based and user-based rate limiting  
✅ **Extensible** - Ready for email management UI and advanced features  

The foundation is complete and working. Future enhancements will add the email management interface for privileged users to view, reply to, and manage support requests through the platform.
