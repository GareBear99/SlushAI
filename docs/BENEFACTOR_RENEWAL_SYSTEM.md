# Benefactor Badge Monthly Renewal System

**Last Updated: November 27, 2025**
**Status: ⚠️ SPECIFICATION — NOT implemented (Stage 3, 2026-11-10)**

> The database columns exist (`benefactor_badge_expires`,
> `benefactor_last_renewal`, `benefactor_badge_unlocked` — added by
> `user_manager.py`), and `record_donation()` unlocks the badge. But **no
> monthly expiry is enforced anywhere**: `record_donation()` sets
> `benefactor_badge_unlocked = 1` and never sets `benefactor_badge_expires`,
> and nothing in the code reads `benefactor_badge_expires` or expires
> badges on the 1st of the month. A donated badge is currently permanent.
> The monthly-expiration / renewal / expiry-email system described below
> is a design to implement, not a description of the live behaviour.
> Do not tell users their badge expires monthly until this is built.

## Overview
The Benefactor badge grants access to the referral system and requires a $1+ monthly donation to maintain. This document outlines the implementation of the monthly expiration and renewal system.

**Key Features:**
- Monthly badge expiration (1st of each month at 00:00 UTC)
- Earnings-first billing model (referral earnings pay subscription before becoming profit)
- Minimum $5 cashout requirement
- Preserved redeemable balance when badge expires
- PayPal or Crypto (BTC/ETH) payout options

## System Requirements

### 1. Database Schema Updates

**Add new columns to `users` table:**
```sql
ALTER TABLE users ADD COLUMN benefactor_badge_expires TIMESTAMP;
ALTER TABLE users ADD COLUMN benefactor_last_renewal TIMESTAMP;
```

**Purpose:**
- `benefactor_badge_expires`: Timestamp when the badge expires (set to 1st of next month at 00:00 UTC)
- `benefactor_last_renewal`: Last time user renewed their badge (donation timestamp)

### 2. Badge Expiration Logic

**Update `record_donation()` method in `user_manager.py`:**

```python
def record_donation(self, user_id: int, amount_usd: float, payment_method: str, 
                   payment_id: str = None) -> bool:
    """Record a donation and unlock/renew Benefactor badge."""
    try:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Record donation
        if payment_method == 'stripe':
            cursor.execute('''
                INSERT INTO donations (user_id, amount_usd, payment_method, stripe_payment_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount_usd, payment_method, payment_id))
        else:
            cursor.execute('''
                INSERT INTO donations (user_id, amount_usd, payment_method, crypto_tx_hash)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount_usd, payment_method, payment_id))
        
        # Calculate expiration date (1st of next month at 00:00 UTC)
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        
        now = datetime.utcnow()
        # Get first day of next month
        first_of_next_month = (now.replace(day=1) + relativedelta(months=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Unlock/renew Benefactor badge with new expiration
        cursor.execute('''
            UPDATE users 
            SET has_donated = 1, 
                benefactor_badge_unlocked = 1,
                benefactor_badge_expires = ?,
                benefactor_last_renewal = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (first_of_next_month.isoformat(), user_id))
        
        # Generate referral code if they don't have one
        cursor.execute('SELECT referral_code FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            self.generate_referral_code(user_id)
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error recording donation: {e}")
        return False
```

### 3. Daily Badge Expiration Job

**Add new method to `user_manager.py`:**

```python
def expire_benefactor_badges(self) -> int:
    """Expire Benefactor badges on the 1st of each month.
    
    Should be run daily as a cron job.
    
    Returns:
        Number of badges expired
    """
    try:
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow()
        
        # Find all users with expired badges
        cursor.execute('''
            SELECT id, email, username 
            FROM users 
            WHERE benefactor_badge_unlocked = 1 
            AND benefactor_badge_expires IS NOT NULL
            AND benefactor_badge_expires <= ?
        ''', (now.isoformat(),))
        
        expired_users = cursor.fetchall()
        
        if not expired_users:
            conn.close()
            return 0
        
        # Expire badges
        expired_ids = [user[0] for user in expired_users]
        placeholders = ','.join('?' * len(expired_ids))
        
        cursor.execute(f'''
            UPDATE users 
            SET benefactor_badge_unlocked = 0
            WHERE id IN ({placeholders})
        ''', expired_ids)
        
        conn.commit()
        
        # Send notification emails to expired users
        for user_id, email, username in expired_users:
            self._send_badge_expiration_email(email, username)
        
        conn.close()
        return len(expired_users)
        
    except Exception as e:
        print(f"Error expiring badges: {e}")
        return 0

def _send_badge_expiration_email(self, email: str, username: str):
    """Send email notification when Benefactor badge expires."""
    subject = "🏷️ Your Benefactor Badge Has Expired"
    
    body = f"""
    Hi {username},
    
    Your Benefactor badge has expired as of the 1st of this month.
    
    🔒 Your referral system is now locked:
    • You can no longer earn new referral credits
    • Existing redeemable balance is preserved but frozen
    • To unlock, donate $1+ to renew your badge
    
    💝 Renew Your Badge:
    Visit http://localhost:5000/donate to make a donation and reactivate your referral system.
    
    As long as you donate $1+ each month before the 1st, your badge stays active!
    
    Best regards,
    SlushAI Team
    """
    
    try:
        self._send_email(email, subject, body)
    except Exception as e:
        print(f"Failed to send expiration email to {email}: {e}")
```

### 4. Referral System Access Control

**Update `get_referral_stats()` method:**

```python
def get_referral_stats(self, user_id: int) -> Dict:
    """Get referral statistics for a user."""
    try:
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get benefactor status
        cursor.execute('''
            SELECT referral_code, benefactor_badge_unlocked, benefactor_badge_expires 
            FROM users WHERE id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return {'error': 'User not found'}
        
        referral_code, has_badge, expires_at = row
        
        # Check if badge is expired
        badge_expired = False
        if has_badge and expires_at:
            expires_dt = datetime.fromisoformat(expires_at)
            if datetime.utcnow() >= expires_dt:
                badge_expired = True
        
        if not has_badge or badge_expired:
            conn.close()
            return {
                'has_badge': False,
                'badge_expired': badge_expired,
                'message': 'Donate $1+ to unlock/renew the Benefactor badge and referral system!',
                'expires_at': expires_at if badge_expired else None
            }
        
        # Badge is active, return full stats
        # ... rest of existing code ...
        
        return {
            'has_badge': True,
            'badge_active': True,
            'expires_at': expires_at,
            'referral_code': referral_code,
            # ... rest of stats ...
        }
        
    except Exception as e:
        return {'error': str(e)}
```

### 5. Weekly Earnings Calculation Update

**Update `calculate_weekly_referral_earnings()` to only process active badges:**

```python
def calculate_weekly_referral_earnings(self) -> int:
    """Calculate referral earnings only for users with active Benefactor badges."""
    try:
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow()
        week_number = now.isocalendar()[1]
        year = now.year
        
        # Get only users with ACTIVE Benefactor badges
        cursor.execute('''
            SELECT id, subscription_tier, referral_code
            FROM users
            WHERE benefactor_badge_unlocked = 1
            AND (benefactor_badge_expires IS NULL OR benefactor_badge_expires > ?)
        ''', (now.isoformat(),))
        
        active_benefactors = cursor.fetchall()
        
        # ... rest of earnings calculation logic ...
```

## Implementation Checklist

- [ ] Add database columns (`benefactor_badge_expires`, `benefactor_last_renewal`)
- [ ] Update `record_donation()` to set expiration date
- [ ] Create `expire_benefactor_badges()` method
- [ ] Create `_send_badge_expiration_email()` method
- [ ] Update `get_referral_stats()` to check expiration
- [ ] Update `calculate_weekly_referral_earnings()` to filter expired badges
- [ ] Add daily cron job to run `expire_benefactor_badges()`
- [ ] Update frontend Account tab to show badge expiration date
- [ ] Add "Renew Badge" button in UI when expired
- [ ] Test full renewal cycle

## Cron Job Setup

**Add to server crontab:**
```bash
# Run daily at 00:05 UTC to expire badges
5 0 * * * cd /path/to/AI3DModeller && python -c "from src.ai3d.utils.user_manager import UserManager; um = UserManager('logs/users.db'); um.expire_benefactor_badges()"
```

## User Experience Flow

### New Donation
1. User donates $1+
2. Badge unlocked, expires set to 1st of next month
3. Referral code generated
4. User can start earning

### Badge Expiration
1. Daily job runs on 1st of month at 00:05 UTC
2. All badges with `benefactor_badge_expires <= now` are revoked
3. Email sent to affected users
4. Referral system locked (earnings frozen)
5. User must donate again to reactivate

### Badge Renewal
1. User donates $1+ before expiration
2. Badge expiration extended to 1st of next month
3. Continuous earning access maintained

## Earnings & Redemption Logic

### With Active Badge
- Earns $1/week per paying referral
- Earnings first pay subscription bill
- Excess becomes redeemable balance
- Can cash out when balance >= $5

### With Expired Badge
- No new earnings accrue
- Existing redeemable balance preserved but frozen
- Cannot cash out until badge renewed
- Paying referrals still tracked (earnings resume upon renewal)

## Database Queries

### Check if badge is active:
```sql
SELECT benefactor_badge_unlocked, benefactor_badge_expires
FROM users
WHERE id = ?
AND benefactor_badge_unlocked = 1
AND (benefactor_badge_expires IS NULL OR benefactor_badge_expires > datetime('now'));
```

### Get all expired badges:
```sql
SELECT id, email, username
FROM users
WHERE benefactor_badge_unlocked = 1
AND benefactor_badge_expires <= datetime('now');
```

### Get users needing renewal reminder (3 days before expiration):
```sql
SELECT id, email, username, benefactor_badge_expires
FROM users
WHERE benefactor_badge_unlocked = 1
AND benefactor_badge_expires BETWEEN datetime('now') AND datetime('now', '+3 days');
```

## Notes

- Badge expiration always happens at 00:00 UTC on the 1st of each month
- Minimum donation of $1 required for renewal
- Users are notified via email when badge expires
- Optional: Send reminder emails 3 days before expiration
- Redeemable balance is never lost, only frozen until renewal
- This creates recurring revenue stream while being low-cost for users ($1/month = $12/year)
