# Password Reset System

**SlushAI 3D Modeller - Password Reset Documentation**

Last Updated: November 27, 2025

---

## Overview

The password reset system allows users to securely reset their passwords via email verification. The system uses time-limited tokens and includes comprehensive security measures to prevent abuse.

---

## Features

### Security Features
- ✅ Secure URL-safe tokens (32 bytes)
- ✅ 1-hour token expiration
- ✅ 60-second throttling between requests (per email)
- ✅ Rate limiting: 3 requests per hour (per IP)
- ✅ Doesn't reveal if email exists
- ✅ Tokens are single-use (deleted after successful reset)
- ✅ Password strength validation (minimum 8 characters)
- ✅ Development mode console fallback

### User Experience
- Clean, responsive UI with password strength indicator
- Email with both HTML and plain text versions
- Clear requirements and error messages
- Automatic redirect to login after successful reset
- "Forgot Password?" link on login page

---

## How It Works

### 1. Request Password Reset

**User Action**: Clicks "Forgot Password?" on login page

**Process**:
1. User enters email address
2. System generates secure token (32-byte URL-safe)
3. Token stored in database with 1-hour expiration
4. Email sent with reset link
5. Request is throttled (60 seconds between requests per email)

**Email Contains**:
- Reset link: `http://localhost:5000/password-reset?token={token}`
- Expiration warning (1 hour)
- Security notice

### 2. Reset Password

**User Action**: Clicks link in email

**Process**:
1. User redirected to password reset page
2. Token validated (checked for existence and expiration)
3. User enters new password (must be 8+ characters)
4. Password strength indicator shows real-time feedback
5. User confirms password
6. Password is hashed and stored
7. Token is deleted from database
8. User redirected to login page

---

## API Endpoints

### Request Password Reset

```http
POST /auth/password-reset/request
```

**Rate Limit**: 3 per hour (IP-based)

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response** (Always 200 to not reveal if email exists):
```json
{
  "success": true,
  "message": "If that email exists, we've sent a password reset link"
}
```

**Throttling Error** (400):
```json
{
  "error": "Please wait 45 seconds before requesting another reset"
}
```

### Complete Password Reset

```http
POST /auth/password-reset/complete
```

**Rate Limit**: 5 per hour (IP-based)

**Request Body**:
```json
{
  "token": "abc123...",
  "password": "newSecurePassword123!"
}
```

**Success Response** (200):
```json
{
  "success": true,
  "message": "Password successfully reset"
}
```

**Error Responses** (400):
```json
{
  "success": false,
  "error": "Invalid or expired reset link"
}
```

```json
{
  "success": false,
  "error": "Password must be at least 8 characters long"
}
```

---

## Database Schema

### Users Table Additions

```sql
-- Password reset token (URL-safe 32-byte string)
reset_token TEXT

-- Token expiration timestamp (ISO format)
reset_token_expires TIMESTAMP

-- Last reset request time for throttling
last_reset_request_at TIMESTAMP
```

---

## Implementation Details

### Token Generation

```python
import secrets
from datetime import datetime, timedelta

# Generate secure token
token = secrets.token_urlsafe(32)  # 43 characters

# Set expiration (1 hour)
expires_at = datetime.now() + timedelta(hours=1)

# Store in database
UPDATE users
SET reset_token = ?, reset_token_expires = ?
WHERE id = ?
```

### Token Validation

```python
# Check token exists
SELECT id, email, reset_token_expires
FROM users
WHERE reset_token = ?

# Verify not expired
if datetime.now() > datetime.fromisoformat(expires_at):
    return False, "Reset link has expired"
```

### Password Reset

```python
import bcrypt

# Hash new password
password_hash = bcrypt.hashpw(
    new_password.encode('utf-8'),
    bcrypt.gensalt()
).decode('utf-8')

# Update password and clear token
UPDATE users
SET password_hash = ?,
    reset_token = NULL,
    reset_token_expires = NULL
WHERE id = ?
```

---

## Email Template

### Subject
`Reset your SlushAI password`

### Content

**HTML Version**: Beautiful gradient header, centered button, expiration warning

**Plain Text Version**: Simple formatted text with link

**Key Elements**:
- Personalized greeting (if name available)
- Clear reset link button
- 1-hour expiration warning
- Security notice (can be safely ignored if not requested)
- Link shown as plain text for copy/paste

---

## Security Considerations

### Rate Limiting

| Endpoint | Limit | Window | Type |
|----------|-------|--------|------|
| `/auth/password-reset/request` | 3 requests | 1 hour | IP-based |
| `/auth/password-reset/complete` | 5 requests | 1 hour | IP-based |
| Per-email throttling | 1 request | 60 seconds | Email-based |

### Token Security

**Token Properties**:
- Length: 43 characters (32 bytes URL-safe encoded)
- Character set: A-Z, a-z, 0-9, -, _
- Entropy: 256 bits
- Unpredictable: Uses `secrets` module (cryptographically secure)

**Example Token**:
```
xQFd7KpN5m_3jZ2rL8wVhY4tPqR6nC9sA1bE0gH7UiM
```

### Attack Prevention

**Email Enumeration**: Always returns success message, doesn't reveal if email exists

**Brute Force**: 
- Rate limited (3/hour per IP)
- Large token space (2^256 combinations)
- Short expiration (1 hour)

**Replay Attacks**:
- Single-use tokens
- Tokens deleted after use
- Time-limited validity

---

## User Experience

### Password Strength Indicator

Shows real-time feedback as user types:

| Strength | Criteria | Color |
|----------|----------|-------|
| Weak | < 3 requirements | 🔴 Red |
| Medium | 3-4 requirements | 🟠 Orange |
| Strong | 5+ requirements | 🟢 Green |

**Requirements Checked**:
- Length ≥ 8 characters
- Length ≥ 12 characters
- Contains lowercase letter
- Contains uppercase letter
- Contains number
- Contains special character

### Error Messages

Clear, user-friendly messages:
- ❌ Invalid or expired reset link
- ❌ Password must be at least 8 characters long
- ❌ Passwords do not match
- ❌ Please wait X seconds before requesting another reset
- ✅ Password successfully reset! Redirecting to login...

---

## Development Mode

When SMTP is not configured:

**Console Output**:
```
⚠️ EMAIL NOT CONFIGURED - Development Mode
🔑 Password reset link for user@example.com:
http://localhost:5000/password-reset?token=xQFd7KpN5m_3jZ2rL8wVhY4tPqR6nC9sA1bE0gH7UiM
```

This allows testing without email configuration.

---

## Testing

### Test Flow

1. **Request Reset**:
   ```bash
   curl -X POST http://localhost:5000/auth/password-reset/request \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com"}'
   ```

2. **Check Console** (if email not configured):
   - Copy the reset link from server logs

3. **Visit Reset Page**:
   - Open link in browser
   - Enter new password (min 8 chars)
   - Confirm password

4. **Login**:
   - Return to login page
   - Use new password

### Test Cases

- ✅ Valid email → receives reset link
- ✅ Invalid email → still shows success (security)
- ✅ Expired token → shows error
- ✅ Used token → shows error
- ✅ Short password → shows validation error
- ✅ Mismatched passwords → shows error
- ✅ Multiple rapid requests → throttled
- ✅ Rate limit exceeded → shows error

---

## Troubleshooting

### User Can't Receive Email

**Possible Causes**:
1. SMTP not configured
2. Email in spam folder
3. Rate limit reached
4. Network issues

**Solutions**:
1. Check server logs for email send errors
2. Verify SMTP configuration in `.env`
3. Check spam/junk folder
4. Wait and retry (throttling may be active)

### Token Expired

**Cause**: More than 1 hour passed since request

**Solution**: Request new password reset link

### Can't Access Reset Page

**Cause**: Invalid or missing token in URL

**Solution**: Click the link in email again or request new reset

---

## Configuration

### Environment Variables

Required for email sending:

```bash
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=SlushAI 3D Modeller
```

See `EMAIL_SETUP.md` for detailed SMTP configuration instructions.

---

## Monitoring

### Logged Events

**Activity Log**:
- `password_reset_requested` - When user requests reset
- `password_reset_completed` - When user successfully resets

**Fields Logged**:
- Email address (for requests)
- IP address
- Timestamp
- Email send status

### Metrics to Monitor

- Password reset request rate
- Success/failure ratio
- Token expiration rate (indicates email delivery issues)
- Rate limit hits

---

## Future Enhancements

Potential improvements:

- [ ] 2FA option for password reset
- [ ] Email notification when password is changed
- [ ] Password history (prevent reuse of last N passwords)
- [ ] Account recovery questions as alternative
- [ ] SMS-based password reset option
- [ ] Integration with password managers

---

## Related Documentation

- [Email Setup Guide](EMAIL_SETUP.md) - Configure SMTP
- [Rate Limits](RATE_LIMITS.md) - Rate limiting details
- [API Documentation](API_DOCUMENTATION.md) - Full API reference
- [Security](../src/ai3d/utils/security.py) - Security implementation

---

## Support

For password reset issues:
1. Check this documentation
2. View server logs for errors
3. Verify SMTP configuration
4. Contact system administrator

**Remember**: Password resets are security-critical. Never share reset links or bypass security measures.
