# Email Verification - Quick Setup Guide

This guide will help you set up email verification for SlushAI 3D Modeller in under 5 minutes.

## Prerequisites

- Gmail account (or other SMTP provider)
- Python dependencies already installed

## Step 1: Configure Gmail (Recommended)

### Enable 2-Factor Authentication

1. Go to https://myaccount.google.com/security
2. Click on "2-Step Verification"
3. Follow the prompts to enable 2FA

### Generate App Password

1. Go to https://myaccount.google.com/apppasswords
2. If you don't see this option, make sure 2FA is enabled first
3. In the "Select app" dropdown, choose "Mail"
4. In the "Select device" dropdown, choose "Other (Custom name)"
5. Enter "SlushAI 3D Modeller" as the name
6. Click "Generate"
7. **Copy the 16-character password** (it will look like: `abcd efgh ijkl mnop`)
8. **Important**: Remove the spaces when using it: `abcdefghijklmnop`

## Step 2: Update .env File

1. Open your `.env` file in the project root
2. Add or update these lines:

```bash
# SMTP Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=youremail@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM_EMAIL=youremail@gmail.com
SMTP_FROM_NAME=SlushAI 3D Modeller
```

**Replace**:
- `youremail@gmail.com` with your actual Gmail address
- `abcdefghijklmnop` with your 16-character app password (no spaces)

## Step 3: Restart the Server

```bash
python viewer/app.py
```

## Step 4: Test the System

1. Go to http://localhost:5000
2. Click "Sign Up"
3. Fill out the form with a real email address
4. Check your inbox for the verification email
5. Enter the 6-digit code
6. You should be verified and redirected to login!

## Troubleshooting

### "Failed to send email"

**Check your .env file:**
```bash
# Make sure there are no extra spaces
SMTP_PASSWORD=abcdefghijklmnop  # ✅ Correct
SMTP_PASSWORD=abcd efgh ijkl mnop  # ❌ Wrong (has spaces)
```

**Verify Gmail settings:**
- 2FA is enabled
- App password was generated correctly
- You copied the password without spaces

**Check server logs:**
```bash
# Look for SMTP errors in the terminal where you ran viewer/app.py
```

### "Email not received"

1. **Check spam folder** - Verification emails might end up there initially
2. **Wait 1-2 minutes** - Sometimes there's a delay
3. **Click "Resend Code"** - Try sending again
4. **Check email address** - Make sure you typed it correctly during signup

### "Code expired"

- Codes expire after 10 minutes
- Click "Resend Code" to get a new code with a fresh 10-minute timer

### "Resend button disabled"

- There's a 60-second cooldown between resends to prevent spam
- Wait for the countdown timer to reach zero

## Alternative: Other Email Providers

### Outlook/Hotmail

```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=youremail@outlook.com
SMTP_PASSWORD=your-password
```

### Yahoo Mail

```bash
SMTP_HOST=smtp.mail.yahoo.com
SMTP_PORT=587
SMTP_USER=youremail@yahoo.com
SMTP_PASSWORD=your-app-password
```

**Note**: Yahoo also requires an app-specific password. Generate one at:
https://login.yahoo.com/account/security/app-passwords

### SendGrid (Professional)

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
```

Get your API key from: https://app.sendgrid.com/settings/api_keys

## Development Mode (No SMTP)

If you want to test without setting up SMTP:

1. The server will log verification codes in the terminal
2. Look for lines like: `Verification code for user 123: 456789`
3. Use the code from the logs to verify manually

However, **SMTP must be configured for production use**.

## Security Reminders

✅ **DO:**
- Use app-specific passwords (never your main password)
- Keep SMTP credentials in `.env` file
- Add `.env` to `.gitignore`
- Use different passwords for dev and production

❌ **DON'T:**
- Commit `.env` to version control
- Share your app password
- Use your main email password
- Hardcode credentials in code

## Verification System Features

Once set up, your users will experience:

- 📧 Beautiful HTML verification emails
- ⏱️ Real-time countdown timers (10-minute expiration)
- 🔄 Resend functionality (with 60-second cooldown)
- 🎨 Branded emails with SlushAI colors
- 📱 Mobile-friendly email design
- ✅ Automatic verification on correct code entry

## Need Help?

See the full documentation: `docs/EMAIL_VERIFICATION.md`

## Success!

You're all set! Users can now sign up and receive verification codes via email. 🎉
