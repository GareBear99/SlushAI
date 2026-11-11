# PIN Authentication System

**SlushAI 3D Modeller - Privileged Account Security**

Last Updated: November 27, 2025

---

## Overview

The PIN authentication system provides an additional security layer for privileged accounts (Founder, Administrators, and Moderators). After successful password authentication, these accounts must verify a 6-digit PIN sent to their email before gaining access.

---

## Why PIN Authentication?

### Security Benefits

1. **Two-Factor Authentication**: Requires both password and email access
2. **Prevents Credential Theft**: Stolen passwords alone can't access privileged accounts
3. **Activity Logging**: All PIN attempts are tracked with IP addresses
4. **Brute Force Protection**: Automatic 2-hour ban after 5 failed attempts
5. **Email Management Protection**: Gates access to sensitive admin features

---

## Affected Account Tiers

PIN authentication is **required** for:

- 🏆 **Founder** - Platform owner
- 👮 **Admin** - System administrators  
- 🛡️ **Moderator** - Content moderators

PIN authentication is **not required** for:

- 💎 Pro tier
- ⭐ Standard tier
- 🆓 Free tier

---

## How It Works

### Login Flow

```
1. User enters email + password
   ↓
2. System verifies credentials
   ↓
3. System detects privileged tier
   ↓
4. System generates 6-digit PIN
   ↓
5. PIN stored in database (10-min expiry)
   ↓
6. PIN sent via email
   ↓
7. User enters PIN from email
   ↓
8. System validates PIN
   ↓
9. [If valid] User logged in
   [If invalid] Attempt recorded
   ↓
10. After 5 failures → 2-hour ban
```

### PIN Generation

```python
import random

# Generate secure 6-digit PIN
pin = ''.join([str(random.randint(0, 9)) for _ in range(6)])

# Example: '837462'
```

### PIN Storage

```python
from datetime import datetime, timedelta

# Store PIN with 10-minute expiration
expires_at = datetime.now() + timedelta(minutes=10)

UPDATE users
SET verification_token = ?,
    verification_token_expires = ?
WHERE id = ?
```

---

## API Endpoints

### Login (Password Step)

```http
POST /auth/email/login
```

**Request**:
```json
{
  "email": "founder@example.com",
  "password": "SecurePassword123!",
  "remember_me": true
}
```

**Response for Privileged Account** (200):
```json
{
  "success": false,
  "requires_pin": true,
  "user_id": 1,
  "tier": "founder",
  "message": "Security PIN sent to your email",
  "pin_sent": true
}
```

**Response for Regular Account** (200):
```json
{
  "success": true,
  "message": "Signed in successfully"
}
```

### Verify PIN

```http
POST /auth/email/verify-pin
```

**Rate Limit**: 10 per minute (IP-based)

**Request**:
```json
{
  "user_id": 1,
  "pin": "837462",
  "remember_me": true
}
```

**Success Response** (200):
```json
{
  "success": true,
  "message": "Signed in successfully"
}
```

**Invalid PIN** (400):
```json
{
  "success": false,
  "error": "Incorrect verification code",
  "warning": "4 attempt(s) remaining before 2-hour lockout"
}
```

**Banned Account** (403):
```json
{
  "success": false,
  "error": "Too many failed attempts. Account locked until 02:30 PM",
  "banned": true,
  "ban_until": "2025-11-27T14:30:00"
}
```

---

## Database Schema

### Users Table Additions

```sql
-- PIN ban tracking
pin_ban_until TIMESTAMP
```

### PIN Attempts Table

```sql
CREATE TABLE pin_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL,
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## Security Features

### Attempt Tracking

Every PIN verification attempt is logged:

| Field | Description |
|-------|-------------|
| `user_id` | User being authenticated |
| `attempt_time` | When attempt occurred |
| `success` | Whether PIN was correct |
| `ip_address` | Source IP of attempt |

### Ban System

**Trigger**: 5 failed attempts within 10 minutes

**Duration**: 2 hours

**Implementation**:
```python
# Count recent failures
SELECT COUNT(*) FROM pin_attempts
WHERE user_id = ?
  AND success = 0
  AND attempt_time >= datetime('now', '-10 minutes')

# If count >= 5, ban for 2 hours
ban_until = datetime.now() + timedelta(hours=2)

UPDATE users
SET pin_ban_until = ?
WHERE id = ?
```

**Ban Expiration**:
- Automatic: Ban lifts after 2 hours
- Manual: Admin can clear ban via database
- On Success: Successful login clears any existing ban

### Session Tracking

Successful PIN login sets special session flags:

```python
session['pin_authenticated'] = True
session['pin_auth_time'] = datetime.now().isoformat()
session['user_tier'] = 'founder'  # or 'admin', 'moderator'
```

These flags gate access to:
- Email management interface
- Administrative functions
- Sensitive system operations

---

## Email Template

### Subject
`SlushAI Login PIN - Do Not Share`

### Content

**HTML Version**: Prominent PIN display, security warnings

**Plain Text Version**:
```
Your 6-digit login PIN: 837462

This PIN will expire in 10 minutes.

For your security:
- Never share this PIN with anyone
- SlushAI staff will never ask for your PIN
- If you didn't request this, someone may be trying to access your account

The SlushAI Team
```

---

## Development Mode

When SMTP is not configured, PIN is printed to console:

```
⚠️ EMAIL NOT CONFIGURED - Development Mode PIN for founder@example.com
🔑 LOGIN PIN: 837462
⏱️ Expires in 10 minutes
```

This allows testing without email setup.

---

## Rate Limiting

| Endpoint | Limit | Window | Type |
|----------|-------|--------|------|
| `/auth/email/login` | 10 requests | 1 minute | IP-based |
| `/auth/email/verify-pin` | 10 requests | 1 minute | IP-based |
| PIN attempts (internal) | 5 attempts | 10 minutes | User-based |

---

## User Experience

### Login Flow for Privileged Users

1. **Enter Credentials**
   - Email and password
   - "Remember me" checkbox

2. **PIN Prompt**
   - Automatic detection of privileged tier
   - Clear indication: "FOUNDER Account Security"
   - Message: "A 6-digit login PIN has been sent to your email"

3. **Enter PIN**
   - 6-digit input field
   - Same verification form as email verification
   - Timer showing when code expires

4. **Access Granted**
   - Redirect to `/viewer`
   - Session marked as PIN-authenticated
   - Email management access enabled

### Error Handling

**Clear Warnings**:
- "4 attempt(s) remaining before 2-hour lockout"
- "3 attempt(s) remaining before 2-hour lockout"
- etc.

**Ban Message**:
- "Too many failed attempts. Account locked until 02:30 PM"
- Shows exact unlock time
- Prevents further attempts

---

## Monitoring

### Logged Events

**Activity Log**:
- `privileged_login` - Successful PIN authentication
- PIN verification attempts (success/failure)
- Ban events

**Fields Logged**:
- User ID
- Email address
- Account tier
- IP address
- Timestamp
- Remember me preference

### Security Metrics

Monitor these for security incidents:

- Failed PIN attempts per user
- Ban rate (should be very low)
- Multiple IPs for same account
- Failed attempts from single IP across multiple accounts

---

## Admin Functions

### View PIN Attempt History

```python
attempts = user_manager.get_pin_attempt_history(user_id, limit=20)

# Returns list of dicts:
# [
#   {
#     'id': 1,
#     'user_id': 1,
#     'attempt_time': '2025-11-27T10:30:00',
#     'success': False,
#     'ip_address': '192.168.1.100'
#   },
#   ...
# ]
```

### Check Ban Status

```python
is_banned, ban_until = user_manager.check_pin_ban(user_id)

if is_banned:
    print(f"User banned until {ban_until}")
```

### Clear Ban (Manual)

```sql
UPDATE users
SET pin_ban_until = NULL
WHERE id = ?
```

---

## Testing

### Test Successful Login

1. Create test founder account
2. Attempt login with email/password
3. Check console for PIN (if email not configured)
4. Enter PIN on verification page
5. Verify redirect to `/viewer`
6. Check session has `pin_authenticated = True`

### Test Failed Attempts

1. Login with founder account
2. Enter incorrect PIN (e.g., `000000`)
3. Repeat 4 more times
4. Verify error messages show decreasing attempts
5. On 5th failure, verify 2-hour ban message
6. Attempt to verify PIN again, should be blocked

### Test Ban Expiration

1. Trigger 5 failed attempts
2. Wait 2 hours (or manually clear ban)
3. Attempt login again
4. Verify PIN verification works

---

## Troubleshooting

### Can't Receive PIN Email

**Causes**:
1. SMTP not configured
2. Email in spam
3. Network issues

**Solutions**:
1. Check server console logs for PIN
2. Verify email configuration
3. Check spam/junk folder

### Locked Out (Banned)

**Cause**: 5 failed PIN attempts

**Solutions**:
1. Wait 2 hours for automatic unlock
2. Contact admin to clear ban
3. Check email for correct PIN

### PIN Expired

**Cause**: More than 10 minutes since request

**Solution**: Request new PIN by logging in again

---

## Best Practices

### For Users

✅ **Do**:
- Check email immediately after login
- Enter PIN carefully
- Keep email account secure
- Enable 2FA on email account

❌ **Don't**:
- Share PIN with anyone
- Use same password as email
- Ignore ban warnings
- Request PIN repeatedly

### For Administrators

✅ **Do**:
- Monitor failed attempt rates
- Investigate unusual patterns
- Clear bans only after verification
- Keep SMTP credentials secure

❌ **Don't**:
- Disable PIN authentication
- Clear bans automatically
- Share admin credentials
- Ignore security alerts

---

## Security Considerations

### Attack Scenarios

**Scenario 1: Stolen Password**
- Attacker has password but not email access
- Can't complete login without PIN
- ✅ Protected

**Scenario 2: Brute Force PIN**
- 1,000,000 possible PINs (000000-999999)
- 5 attempts allowed
- 2-hour cooldown
- ✅ Impractical to brute force

**Scenario 3: Email Compromise**
- If email is compromised, attacker can get PIN
- But also needs password
- Emphasizes importance of email security
- ⚠️ User responsibility

### Future Enhancements

Potential improvements:

- [ ] TOTP (Google Authenticator) as PIN alternative
- [ ] SMS-based PIN delivery
- [ ] Biometric authentication option
- [ ] Hardware security key support
- [ ] Longer ban duration for repeat offenders
- [ ] Notification when account is banned

---

## Related Documentation

- [Email Setup Guide](EMAIL_SETUP.md) - Configure SMTP for PIN delivery
- [Rate Limits](RATE_LIMITS.md) - Rate limiting details
- [Password Reset](PASSWORD_RESET.md) - Password recovery
- [User Manager](../src/ai3d/utils/user_manager.py) - Implementation

---

## Support

For PIN authentication issues:
1. Check server console logs
2. Verify SMTP configuration
3. Review ban status
4. Contact system administrator

**Security Notice**: PIN authentication is critical for protecting privileged accounts. Never disable or bypass this security feature.
