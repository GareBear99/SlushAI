# Email Verification System

## Overview

The SlushAI 3D Modeller uses a 6-digit code verification system to confirm user email addresses during registration. This system replaces the traditional JWT token-based email verification with a more user-friendly approach.

## Features

- **6-digit verification codes**: Easy to read and type
- **10-minute expiration**: Codes expire after 10 minutes for security
- **60-second resend throttling**: Prevents abuse while allowing users to request new codes
- **Real-time countdown timers**: Visual feedback for code expiration and resend availability
- **Beautiful HTML emails**: Professional-looking verification emails with clear instructions
- **Automatic retry on login**: Unverified users can request a new code when trying to log in

## User Flow

### 1. Sign Up
1. User fills out the registration form (name, email, password, password confirmation)
2. User optionally opts into newsletter (checked by default)
3. Upon successful account creation, a 6-digit code is generated and sent via email
4. The verification form is immediately displayed with countdown timers

### 2. Email Verification
1. User receives an email with the 6-digit code
2. User enters the code in the verification form
3. The code is validated on the backend:
   - Checks if code matches
   - Checks if code has expired (10 minutes)
   - Marks email as verified on success
4. User is redirected to login form with email pre-filled

### 3. Code Resend
1. If the user doesn't receive the email or the code expires, they can click "Resend Code"
2. The resend button is disabled for 60 seconds after sending to prevent abuse
3. A new code is generated with a fresh 10-minute expiration
4. Real-time countdown shows when the next resend is available

### 4. Login Without Verification
1. If a user tries to log in with an unverified email, they receive an error
2. The verification form is automatically shown with their email
3. User can request a new code if needed

## Technical Implementation

### Backend (Python/Flask)

#### Database Schema
```sql
-- Users table columns for email verification
verification_token TEXT,           -- Stores the 6-digit code
verification_token_expires TIMESTAMP, -- Code expiration time
last_code_sent_at TIMESTAMP,      -- For resend throttling
email_verified BOOLEAN DEFAULT 0   -- Verification status
```

#### Key Methods in `user_manager.py`

**`generate_verification_code(user_id: int) -> Optional[str]`**
- Generates a random 6-digit code
- Sets 10-minute expiration
- Stores code and expiration in database
- Returns the code

**`verify_email_code(user_id: int, code: str) -> Tuple[bool, str]`**
- Validates code format (6 digits)
- Checks if code matches stored code
- Checks if code has expired
- Marks email as verified on success
- Returns (success, message) tuple

**`send_verification_email(email: str, code: str) -> Tuple[bool, str]`**
- Creates beautiful HTML email with code
- Includes plain text fallback
- Sends via SMTP
- Returns (success, message) tuple

**`resend_verification_code(user_id: int) -> Tuple[bool, str, Optional[str]]`**
- Checks 60-second throttling
- Generates new code
- Updates `last_code_sent_at`
- Sends new email
- Returns (success, message, code) tuple

#### API Endpoints

**`POST /auth/email/signup`**
- Creates user account
- Generates verification code
- Sends verification email
- Returns user_id and email_sent status

**`POST /auth/email/verify-code`**
- Accepts user_id and code
- Validates code
- Marks email as verified
- Returns success/error message

**`POST /auth/email/resend-code`**
- Accepts user_id
- Checks throttling (60 seconds)
- Generates and sends new code
- Returns success/error message

**`POST /auth/email/login`**
- Checks credentials
- If email not verified, returns 403 with user_id
- Frontend shows verification form automatically

### Frontend (JavaScript)

#### UI Components

**Verification Form**
- 6-digit code input field (numeric only, max 6 characters)
- Real-time countdown timer showing code expiration
- Verify button
- Resend button with countdown
- Back to sign-up link

**Countdown Timers**

**Code Expiration Timer (10 minutes)**
```javascript
⏱️ Code expires in 9:45
⏱️ Code expires in 5:23
⏱️ Code expires in 0:30
⌛ Code expired. Please request a new one.
```

**Resend Throttle Timer (60 seconds)**
```javascript
Resend Code (60s)
Resend Code (45s)
Resend Code (10s)
Resend Code
```

#### Key Functions

**`showVerificationForm(userId, email)`**
- Shows verification UI
- Sets expiry times
- Starts countdown timers
- Pre-fills email display

**`startCodeTimer()`**
- Updates every second
- Shows minutes:seconds remaining
- Disables verify button when expired

**`startResendTimer()`**
- Updates every second
- Enables resend button after 60 seconds
- Shows countdown on button

## SMTP Configuration

### Environment Variables

Add these to your `.env` file:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=SlushAI 3D Modeller
```

### Gmail Setup

1. **Enable 2-Factor Authentication**
   - Go to https://myaccount.google.com/security
   - Enable 2-Step Verification

2. **Generate App Password**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the 16-character password (no spaces)
   - Use this as `SMTP_PASSWORD`

3. **Update .env**
   ```bash
   SMTP_USER=youremail@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop  # Remove spaces: abcdefghijklmnop
   SMTP_FROM_EMAIL=youremail@gmail.com
   ```

### Other SMTP Providers

**Outlook/Hotmail**
```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
```

**Yahoo Mail**
```bash
SMTP_HOST=smtp.mail.yahoo.com
SMTP_PORT=587
```

**SendGrid**
```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
```

**Mailgun**
```bash
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
```

## Email Template

The verification email includes:

### HTML Version
- SlushAI branding with gradient header
- Large, centered 6-digit code with monospace font
- Expiration warning (10 minutes)
- Professional styling with SlushAI colors
- Footer with motto and copyright

### Plain Text Version
- Simple text format
- Clear code display
- Expiration notice
- Fallback for email clients without HTML support

## Security Features

1. **Code Expiration**: 10-minute window prevents code reuse
2. **Resend Throttling**: 60-second delay prevents spam
3. **Rate Limiting**: 
   - Signup: 5 attempts per hour per IP
   - Verify: 10 attempts per minute per IP
   - Resend: 5 attempts per hour per IP
4. **Random Code Generation**: Cryptographically random 6-digit codes
5. **Database Storage**: Codes stored in database, not in tokens
6. **Email Verification Required**: Users cannot access the app until verified

## Error Handling

### Common Errors and Solutions

**"Failed to send email"**
- Check SMTP credentials in `.env`
- Verify SMTP server allows connections
- Check firewall/network settings
- For Gmail, verify App Password is correct

**"Code expired"**
- Click "Resend Code" to get a new code
- New code has fresh 10-minute expiration

**"Please wait X seconds"**
- Resend is throttled to prevent abuse
- Wait for countdown to finish

**"Invalid code format"**
- Code must be exactly 6 digits
- Input field only accepts numbers

**"Incorrect verification code"**
- Double-check the code in your email
- Code is case-insensitive (all digits)
- Request new code if needed

## Testing

### Manual Testing Checklist

1. **Sign Up Flow**
   - [ ] Create account with valid email
   - [ ] Receive verification email within 30 seconds
   - [ ] Email contains 6-digit code
   - [ ] Email is formatted correctly

2. **Verification Flow**
   - [ ] Enter correct code → email verified
   - [ ] Enter incorrect code → error message
   - [ ] Enter expired code → expiration error
   - [ ] Timer counts down correctly

3. **Resend Flow**
   - [ ] Click resend → new code sent
   - [ ] Resend button disabled for 60 seconds
   - [ ] Countdown shows remaining time
   - [ ] New code works, old code invalid

4. **Login Flow**
   - [ ] Try to login before verification → shown verification form
   - [ ] Verify email → can login successfully
   - [ ] Verified users can login normally

### Development Mode

For development without SMTP:
1. Check server logs for verification codes
2. Codes are logged when email sending fails
3. Use the logged code to verify manually

## Migration from Token-Based System

The old JWT token-based verification system has been completely replaced. No migration is needed for existing users as:
- Old `verification_token` column is reused for codes
- Old `verification_token_expires` column is reused
- New `last_code_sent_at` column added automatically

## Troubleshooting

### Email Not Received

1. Check spam/junk folder
2. Verify SMTP credentials are correct
3. Check server logs for errors
4. Try resending code
5. Verify email address is correct

### Code Not Working

1. Check if code expired (10 minutes)
2. Verify you're entering the latest code
3. Ensure code is exactly 6 digits
4. Request new code if unsure

### Resend Button Not Working

1. Wait for 60-second throttle
2. Check network connection
3. Verify user_id is valid
4. Check server logs for errors

## Best Practices

1. **Set up SMTP before launch**: Email verification is required
2. **Use app-specific passwords**: Never use your main email password
3. **Monitor email delivery**: Check bounce rates and failures
4. **Keep SMTP credentials secure**: Use environment variables, never commit to git
5. **Test with real emails**: Don't rely on logs for production
6. **Provide clear instructions**: Help users find the email and enter the code
7. **Handle failures gracefully**: Show helpful error messages

## Future Enhancements

Potential improvements:
- SMS verification as alternative
- Email template customization
- Multi-language support
- Rate limit adjustments per user tier
- Remember device feature
- Social login verification bypass
