# Rate Limits & Security

**Last Updated: November 27, 2025**

> **Canonical source (Stage 3, 2026-11-10):** this document is the single
> source of truth for quotas and blocking. Every number below was checked
> against the code (`user_manager.py` SUBSCRIPTION_PLANS,
> `security.py` BLOCKING_TIERS / ATTACK_SEVERITY / RATE_LIMITS, and the
> Flask-Limiter decorators in `viewer/app.py`). Other docs defer to this
> one — if another doc disagrees with it, this one wins.

## Overview

SlushAI implements a comprehensive fair-use rate limiting system to prevent abuse while ensuring reliable service for all users. Limits are applied per IP address and per user account, with a multi-tier progressive blocking system that automatically detects and prevents malicious activity.

## Per-Endpoint Rate Limits

### Public Endpoints (No Limit)
- **`/api/health`** - Server health check
- **`/api/capacity`** - Platform capacity statistics
- **Purpose:** Public monitoring endpoints for infrastructure tracking

### Public Pages (High Limit)
- **`/docs`, `/users`, Landing Pages**
- **Limit:** 100 requests/minute + 256,000 requests/day per IP
- **Purpose:** General browsing and documentation access

### Username Validation
- **`/api/check-username`**
- **Limit:** 30 requests/minute per IP
- **Purpose:** Real-time username availability checking during signup

### Email Signup
- **`/auth/email/signup`**
- **Limit:** 5 signups/hour, **3 accounts maximum per IP**
- **Purpose:** Prevents spam accounts and abuse
- **Note:** IP tracking enforced at database level - attempting to create 4th account returns error page

### Protected User Endpoints
- **`/api/user/*` and other authenticated endpoints**
- **Limit:** 30-60 requests/minute per user (varies by endpoint)
- **Purpose:** General API usage for authenticated users

### Support System
- **`/api/support/submit`**
- **Limit:** 5 requests/hour per user/IP
- **Purpose:** Prevents support ticket spam

## Weekly Generation Quotas

### Quota System
Quotas reset every Monday at 00:00 UTC. Only **successful model completions** count towards quota - failed or cancelled generations do not consume your limit.

| Tier | Models/Week | Notes |
|------|-------------|-------|
| **Free** | 10 | Resets Monday 00:00 UTC |
| **Standard** | 40 | Resets Monday 00:00 UTC |
| **Pro** | 120 | Resets Monday 00:00 UTC |
| **Staff** | Unlimited | Founder/Admin/Moderator tiers (code: 999999 = no limit) |

### Quick Refills
- **Cost:** $1.00 USD
- **Adds:** +10 models instantly to current week quota
- **Limit:** Maximum 10 refills per week (enforced in `purchase_refill`)
- **Note:** Refills increase quota limit, not reset usage

## Multi-Tier Progressive Blocking System

> **Stage 3 correction (2026-11-10):** this section previously described a
> 4-level system (warning / 1-hour / 24-hour / permanent). That was wrong.
> The code (`security.py` BLOCKING_TIERS + ATTACK_SEVERITY) escalates on a
> **violation count**, not on the attack type alone — and a single attack
> adds its severity to the count, so one SQL injection (severity 3) lands
> on "moderate", not "warning".

**How it works:** every logged attack adds its severity to the IP's
violation count (counted over the last 90 days). The count selects the
tier; the tier sets the block duration. Counts are cumulative across
attack types.

| Violations | Tier | Block duration |
|---|---|---|
| 1 | warning | 5 minutes |
| 2 | minor | 30 minutes |
| 3 | moderate | 2 hours |
| 5 | serious | 12 hours |
| 7 | severe | 24 hours |
| 10 | critical | 3 days |
| 15 | extreme | 1 week |
| 20 | persistent | 30 days |
| 30+ | permanent | permanent (manual review to lift) |

**Attack severities** (each attack adds this much to the count):

| Attack | Severity added |
|---|---|
| SQL injection, command injection, path traversal | +3 |
| XSS attempt | +2 |
| Suspicious user agent, rate-limit hit, connection abuse, invalid input | +1 |

**Examples:** one SQL injection = 3 violations = moderate (2 hours).
Two SQL injections = 6 violations = serious (12 hours). Thirty
suspicious-UA hits = 30 violations = permanent. Rate-limit 429s
themselves are *not* blocks — they are the per-endpoint limiter; a block
only follows from logged attacks.

**Two rate-limit layers (don't confuse them):**
- **Flask-Limiter (the live 429 gate):** per-endpoint decorators in
  `viewer/app.py` (e.g. 100/min + 256,000/day on public pages, 10/min on
  login, 5/hr on signup) plus the app-level global limit of 1,000/min
  (`check_global_rate_limit` in Stage 3 now returns 429 instead of
  sleeping through). These return 429; they do not block the IP.
- **SecurityManager counters:** `security.py` RATE_LIMITS (e.g. 100/min
  global, 5/min generate) feeds the progressive-blocking counters above
  and the attack log. Localhost (127.0.0.1 / ::1) is whitelisted before
  every SecurityManager check, by design.

## Real-Time Attack Detection

Our security system automatically detects and blocks the following attack types:

### SQL Injection
- **Patterns:** UNION, SELECT, DROP, INSERT, DELETE, etc.
- **Action:** Immediate Level 3 block (24 hours)
- **Logging:** Full attack logged for 3 months

### XSS (Cross-Site Scripting)
- **Patterns:** `<script>` tags, `javascript:` URIs, event handlers
- **Action:** Immediate Level 3 block (24 hours)
- **Logging:** Attack vector logged

### Path Traversal
- **Patterns:** `../` sequences, `/etc/` access attempts
- **Action:** Immediate Level 3 block (24 hours)
- **Logging:** Attempted path logged

### Command Injection
- **Patterns:** Shell metacharacters, `eval`, backticks, `$()`
- **Action:** Immediate Level 3 block (24 hours)
- **Logging:** Command attempt logged

### DDoS Attacks
- **Threshold:** Sustained >1,000 requests per 10 seconds
- **Action:** Immediate Level 4 permanent ban
- **Logging:** Full attack timeline logged

### Brute Force
- **Trigger:** Repeated failed login attempts
- **Action:** Progressive blocking (Level 2 → 3 → 4)
- **Logging:** Login attempts and IPs logged

## Error Log Retention

All attacks and security incidents are logged separately from regular logs:

- **Error Logs:** Kept for 3 months (90 days)
- **Regular Logs:** Truncated at 2,560 entries
- **Purpose:** Security audits, troubleshooting, pattern analysis
- **Auto-Cleanup:** Runs on server start

## Best Practices to Avoid Blocks

1. **Implement exponential backoff** when receiving 429 errors
   - First retry: Wait 1 second
   - Second retry: Wait 2 seconds
   - Third retry: Wait 4 seconds
   - Continue doubling up to maximum 60 seconds

2. **Cache API responses** where appropriate
   - Capacity data rarely changes - cache for 1 minute
   - Health check - cache for 30 seconds
   - User profile - cache for 5 minutes

3. **Use proper authentication** instead of relying on IP limits
   - Authenticated requests have higher per-user limits
   - IP limits are shared across all users on that IP

4. **Respect rate limit headers** in API responses
   - Check `X-RateLimit-Remaining` header
   - Check `X-RateLimit-Reset` timestamp
   - Stop making requests when remaining = 0

5. **Batch requests** when possible
   - Don't poll every second - use WebSocket for real-time updates
   - Fetch multiple resources in single requests when API supports it

6. **Handle errors gracefully**
   - Don't retry indefinitely on errors
   - Implement circuit breaker pattern
   - Log errors and alert on patterns

7. **Monitor your quota usage** via the Account tab
   - Check usage before generating models
   - Plan generations to stay within weekly quota
   - Consider upgrading if consistently hitting limits

## Response Headers

All rate-limited endpoints return the following headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1732618800
Retry-After: 60
```

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed in the current window |
| `X-RateLimit-Remaining` | Number of requests remaining in current window |
| `X-RateLimit-Reset` | Unix timestamp when the rate limit resets |
| `Retry-After` | Seconds to wait before retrying (only on 429 errors) |

## Error Responses

### 429 Too Many Requests

**Example Response:**
```json
{
  "error": "Rate limit exceeded",
  "reason": "You've exceeded 100 requests per minute",
  "explanation": "Your IP address has made too many requests in a short time. This limit helps protect our service from abuse.",
  "retry_after": "60 seconds"
}
```

### 403 Forbidden (IP Blocked)

**Example Response:**
```html
<!DOCTYPE html>
<html>
<head><title>Access Denied - SlushAI 3D Modeller</title></head>
<body>
  <h1>Access Denied</h1>
  <p>Your IP address has been blocked due to suspicious activity.</p>
  <p><strong>Block Type:</strong> Level 3 - Extended Block</p>
  <p><strong>Duration:</strong> 24 hours</p>
  <p><strong>Reason:</strong> SQL injection attempt detected</p>
</body>
</html>
```

## Monitoring and Alerts

### For Developers
Monitor these metrics to avoid blocks:

1. **Request rate per minute**
   - Track outgoing requests to SlushAI
   - Alert if approaching 100/min for public endpoints
   - Alert if approaching tier-specific limits for auth endpoints

2. **Error rate**
   - Track 429 responses
   - Alert on repeated 429s (indicates rate limit issues)
   - Track 403 responses (indicates potential block)

3. **Quota usage**
   - Monitor weekly generation count
   - Alert at 80% quota usage
   - Alert at 100% quota usage

### For System Administrators
Monitor these metrics for service health:

1. **Block rate**
   - Track number of IPs blocked per hour
   - Alert on sudden spikes (potential coordinated attack)

2. **Attack patterns**
   - Review error logs weekly
   - Identify repeat offenders
   - Update firewall rules as needed

3. **Capacity usage**
   - Monitor tier capacity (free, standard, pro)
   - Alert when tiers approach capacity limits

## FAQ

### Q: I got a 429 error. What should I do?
A: Wait for the time specified in the `Retry-After` header (usually 60 seconds), then retry your request. Implement exponential backoff in your code to handle this automatically.

### Q: My IP was blocked for 24 hours. How can I appeal?
A: If you believe your IP was blocked in error, contact support through the homepage with your IP address and timestamp. Legitimate blocks (SQL injection attempts, etc.) cannot be appealed.

### Q: Can I increase my rate limits?
A: Rate limits for public endpoints are fixed. For authenticated endpoints, limits scale with your subscription tier. Upgrade to Standard or Pro for higher weekly quotas.

### Q: What counts as "excessive requests"?
A: Sustained >100 requests/minute from a single IP for public endpoints, or exceeding per-user limits for authenticated endpoints. Occasional spikes are tolerated, but sustained high volume triggers blocks.

### Q: Do failed generations count towards my quota?
A: No! Only successful model completions count towards your weekly quota. Failed or cancelled generations do not consume your limit.

### Q: How do I check my current quota usage?
A: Log into your account and visit the Account tab. Your current usage and remaining quota are displayed prominently.

## Technical Implementation

### Rate Limiter
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_limiter_key,
    default_limits=["100 per minute", "256000 per day"]
)

def get_limiter_key():
    """Get rate limit key - use user_id if authenticated, otherwise IP."""
    if current_user.is_authenticated:
        return f'user:{current_user.user_id}'
    return f'ip:{get_remote_address()}'
```

### Security Manager
The security manager tracks all security events and manages progressive blocking:

```python
class SecurityManager:
    BLOCK_LEVELS = {
        1: {"duration": 60, "reason": "Rate limit exceeded"},
        2: {"duration": 3600, "reason": "Excessive requests"},
        3: {"duration": 86400, "reason": "Attack pattern detected"},
        4: {"duration": -1, "reason": "Permanent ban"}
    }
```

## Support

For questions about rate limits or to appeal a block:

1. Visit the SlushAI homepage
2. Review this documentation first
3. If issue persists, contact support with:
   - Your IP address
   - Timestamp of the block
   - What you were trying to do
   - Error message received

---

**Remember:** Rate limits exist to ensure fair access for all users. Following best practices helps keep the platform fast and reliable for everyone!

**SlushAI 3D Modeller - Rate Limiting and Security Documentation**

Last Updated: November 26, 2025

---

## Overview

SlushAI implements comprehensive rate limiting and security measures to ensure fair usage, prevent abuse, and protect our infrastructure. This document outlines all rate limits, quotas, and security policies.

---

## Rate Limiting System

### How Rate Limiting Works

Rate limits are applied **per IP address** for unauthenticated endpoints and **per user** for authenticated endpoints. When a rate limit is exceeded, you'll receive a `429 Too Many Requests` response.

**Response Format:**
```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests"
}
```

### Global Limits

**All Requests:**
- 100 requests per minute per IP
- Applies to all endpoints unless otherwise specified

---

## Endpoint-Specific Rate Limits

### API Endpoints

| Endpoint | Rate Limit | Window | Authentication | Delay |
|----------|------------|--------|----------------|-------|
| `/api/generate` | 1 request | 2 seconds | Required | None |
| `/api/task/<id>/cancel` | 1 request | 2 seconds | Required | None |
| `/api/screenshot` | 1 request | 1 minute | Required | None |
| `/api/favorites/add` | 30 requests | 1 minute | Required | None |
| `/api/favorites/remove` | 30 requests | 1 minute | Required | None |
| `/api/user/activity` | 30 requests | 1 minute | Required | **1 second** |
| `/api/user/activity/stats` | 30 requests | 1 minute | Required | **1 second** |
| `/api/user/activity/recent` | 30 requests | 1 minute | Required | **1 second** |
| `/api/security/stats` | 30 requests | 1 minute | Required | **1 second** |
| `/api/security/recent-attacks` | 30 requests | 1 minute | Required | **1 second** |

### Authentication Routes

| Route | Rate Limit | Window | Authentication |
|-------|------------|--------|----------------|
| `/auth/email/signup` | 5 requests | 1 hour | Not required (IP-based) |
| `/auth/email/login` | 10 requests | 1 minute | Not required (IP-based) |
| `/auth/email/verify-code` | 10 requests | 1 minute | Not required (IP-based) |
| `/auth/email/verify-pin` | 10 requests | 1 minute | Not required (IP-based) |
| `/auth/email/resend-code` | 5 requests | 1 hour | Not required (IP-based) |
| `/auth/password-reset/request` | 3 requests | 1 hour | Not required (IP-based) |
| `/auth/password-reset/complete` | 5 requests | 1 hour | Not required (IP-based) |
| `/api/check-username` | 30 requests | 1 minute | Not required (IP-based) |

### Support Routes

| Route | Rate Limit | Window | Authentication |
|-------|------------|--------|----------------|
| `/api/support/submit` | 5 requests | 1 hour | Optional (IP or User-based) |

### Documentation Routes

| Route | Rate Limit | Window | Authentication |
|-------|------------|--------|----------------|
| `/docs` | 100 requests | 1 minute; 256000/day | Not required (IP-based) |
| `/docs/terms` | 100 requests | 1 minute; 256000/day | Not required (IP-based) |
| `/docs/privacy` | 100 requests | 1 minute; 256000/day | Not required (IP-based) |
| `/docs/api` | 100 requests | 1 minute; 256000/day | Not required (IP-based) |
| `/docs/rate-limits` | 100 requests | 1 minute; 256000/day | Not required (IP-based) |

### Public Routes

| Route | Rate Limit | Window |
|-------|------------|--------|
| `/` (landing) | 100 requests | 1 minute; 256000/day (IP-based) |
| `/api/health` | No limit | - |
| `/api/queue/status` | No limit (login required) | - |
| `/api/capacity` | No limit | - |

### 1-Second Delay Rate Limiting

Endpoints marked with **1 second** delay implement an enforced minimum 1-second delay between requests:

**Purpose:**
- **Fair usage:** Ensures all users get equal access to resources
- **Abuse prevention:** Makes automated scraping/spam impractical
- **Server protection:** Prevents overload on database-intensive endpoints
- **Smooth experience:** Delay is imperceptible for normal human use

**Implementation:**
- 30 requests per minute = 1 request every 2 seconds maximum
- Server enforces `time.sleep(1)` at start of each request
- Rate limiter still applies (returns 429 if 30/min exceeded)
- Applies to:
  - All activity log endpoints (`/api/user/activity*`)
  - Security monitoring endpoints (`/api/security/*`)

**Example:**
If you make a request at `00:00:00`, the next request must wait until at least `00:00:01`.

---

## User Quotas

### Free Tier

**Weekly Generation Quota:**
- 10 model generations per week
- Week resets every Monday at 00:00 UTC
- Quota tracked per user account

**Storage Limits:**
- Maximum 10 favorites per user
- Maximum 32 total models per user (includes favorites)
- Non-favorited models auto-delete after 36 hours

**Screenshot Limits:**
- 1 screenshot per minute
- 60-second cooldown between captures
- Server-side cooldown tracking (persists across sessions)

---

## Multi-Tier Progressive Blocking System

### Overview

SlushAI uses an intelligent progressive blocking system that escalates based on violation severity and frequency. This protects against attacks while minimizing false positives.

### Blocking Tiers

| Tier | Violations | Block Duration | Description |
|------|-----------|----------------|-------------|
| Warning | 1 | 5 minutes | First offense |
| Minor | 2 | 30 minutes | Second offense |
| Moderate | 3 | 2 hours | Third offense |
| Serious | 5 | 12 hours | Fifth offense |
| Severe | 7 | 24 hours | Seventh offense |
| Critical | 10 | 3 days | Tenth offense |
| Extreme | 15 | 1 week | Fifteenth offense |
| Persistent | 20 | 30 days | Twentieth offense |
| **Permanent** | 30+ | Permanent | Extreme persistent offenders |

### Attack Severity Scoring

Different attack types add different violation counts:

| Attack Type | Severity | Violations Added |
|------------|----------|------------------|
| SQL Injection | High | +3 |
| Command Injection | High | +3 |
| Path Traversal | High | +3 |
| SSRF Attempt | High | +3 |
| XSS Attempt | Medium | +2 |
| Header Injection | Medium | +2 |
| Suspicious User Agent | Low | +1 |
| Rate Limit Exceeded | Low | +1 |
| Connection Limit | Low | +1 |
| Invalid Input | Low | +1 |

### Examples

**Example 1: Single SQL Injection Attempt**
- Severity: High (+3 violations)
- Result: Immediately escalates to **Moderate** tier (2 hours block)

**Example 2: Multiple Rate Limit Violations**
- 1st violation: **Warning** tier (5 minutes)
- 2nd violation: **Minor** tier (30 minutes)
- 3rd violation: **Moderate** tier (2 hours)
- 5th violation: **Serious** tier (12 hours)

**Example 3: Mixed Attacks**
- XSS attempt (+2) → **Minor** tier (30 minutes)
- Then SQL injection (+3) → Total 5 violations → **Serious** tier (12 hours)

---

## Connection Limits

### Maximum Connections

- **10 concurrent connections per IP address**
- Connections timeout after 5 minutes of inactivity
- Exceeding limit results in `403 Forbidden` response

---

## Request Size Limits

### Upload Limits

| Content Type | Maximum Size |
|--------------|--------------|
| Image uploads | 50 MB |
| JSON payloads | 5 MB |
| Screenshots | 10 MB |

Exceeding limits results in `413 Payload Too Large` response.

---

## Attack Detection

### Monitored Patterns

SlushAI automatically detects and blocks the following attack patterns:

#### SQL Injection
- Keywords: `UNION`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `EXEC`
- Patterns: `' OR '1'='1`, `'; DROP TABLE`, etc.

#### Cross-Site Scripting (XSS)
- Keywords: `<script>`, `javascript:`, `onerror`, `onload`
- Encoded variants: URL-encoded, Unicode, double-encoded

#### Path Traversal
- Patterns: `../`, `..\\`, `/etc/passwd`, `/proc/`, `/sys/`
- Null bytes and directory navigation attempts

#### Command Injection
- Keywords: `cmd`, `eval`, `system`, `exec`, `shell`
- Patterns: `$(command)`, `` `command` ``, `| command`

#### Header Injection
- CRLF sequences: `\r`, `\n` in HTTP headers
- Host header validation

#### SSRF (Server-Side Request Forgery)
- Attempts to access: `localhost`, `127.0.0.1`, AWS metadata
- URL redirection attacks

### Blocked User Agents

The following scanning/attack tools are automatically blocked:

- sqlmap
- nikto
- nmap
- masscan
- metasploit
- havij
- acunetix
- w3af
- netsparker
- webinspect

---

## Security Headers

All responses include comprehensive security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; ...
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## Blocklist Management

### JSON Blocklist Export

Blocked IPs are automatically exported to `logs/blocklist.json` for:
- Persistent blocking across server restarts
- Backup and disaster recovery
- Distributed deployment synchronization

**Blocklist Format:**
```json
{
  "last_updated": "2025-11-26T10:30:00",
  "blocked_ips": [
    {
      "ip": "192.168.1.100",
      "reason": "SQL injection (Tier: critical)",
      "blocked_at": "2025-11-26T10:00:00",
      "blocked_until": "2025-11-29T10:00:00",
      "permanent": false,
      "violations": 10,
      "tier": "critical"
    }
  ]
}
```

### Attack Statistics

Monthly attack statistics are logged to `logs/attack_stats_monthly.log`:
- Total attacks blocked
- IPs blocked count
- Attack type breakdown with percentages
- Top 10 attacking IPs

**Retention:** 90 days of detailed logs, monthly reports kept indefinitely

---

## Best Practices for API Users

### 1. Respect Rate Limits
```python
import time
from requests.exceptions import HTTPError

def make_request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response
        except HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### 2. Check Quota Before Generating
```python
# Check user quota
response = requests.get('/api/user/profile')
quota = response.json()['quota']

if quota['can_generate']:
    # Proceed with generation
    pass
else:
    print(f"Quota exceeded: {quota['weekly_used']}/{quota['weekly_limit']}")
```

### 3. Handle Rate Limit Responses
```python
response = requests.post('/api/generate', files=files)

if response.status_code == 429:
    # Rate limited - wait and retry
    time.sleep(60)
    response = requests.post('/api/generate', files=files)
```

### 4. Monitor Your Usage
```python
# Get security stats
response = requests.get('/api/security/stats?days=7')
stats = response.json()['stats']
print(f"Requests this week: {stats['total_attacks']}")
```

---

## Avoiding Blocks

### Do:
✅ Respect rate limits and quotas  
✅ Use appropriate user agents  
✅ Validate input data client-side  
✅ Cache responses when appropriate  
✅ Implement exponential backoff  
✅ Monitor your API usage  

### Don't:
❌ Send malformed or malicious requests  
❌ Use automated scanning tools  
❌ Attempt to bypass security measures  
❌ Spam endpoints with rapid requests  
❌ Share session tokens publicly  
❌ Ignore rate limit responses  

---

## What to Do If Blocked

### Temporary Blocks (Tiers 1-8)

1. **Wait for block to expire** - Check the tier duration
2. **Review your recent activity** - Identify what triggered the block
3. **Fix the issue** - Stop the problematic behavior
4. **Resume normal usage** - After block expires

### Permanent Blocks

1. **Contact support** via the issue reporting system
2. **Explain your situation** with specific details
3. **Wait for admin review** (typically 24-48 hours)
4. **Accept decision** - Appeals are reviewed case-by-case

---

## Monitoring and Logging

### What We Log

**Security Events:**
- Attack attempts with type, timestamp, IP, endpoint
- IP blocking events with tier and duration
- Rate limit violations
- Suspicious user agent detections

**Operational Events:**
- API request counts
- Generation queue status
- Error occurrences

### What We Don't Log

- User passwords (stored as hashes only)
- Full request/response bodies (except for attack payloads)
- Personal identifiable information beyond email
- OAuth tokens or session secrets

---

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do NOT exploit it**
2. **Report via issue system** - Mark as "Security" priority
3. **Provide details** - Steps to reproduce, impact assessment
4. **Wait for response** - We take security seriously

**Responsible disclosure is appreciated and may be rewarded.**

---

## Rate Limit Changes

We reserve the right to adjust rate limits as needed to:
- Prevent abuse
- Ensure service stability
- Improve user experience
- Respond to security threats

Changes will be announced via:
- Documentation updates
- In-app notifications (for major changes)
- Server logs

---

## Support

For rate limit or security questions:
- Check this documentation first
- Visit `/docs` for full documentation
- Report issues via the issue reporting system
- Check `/api/security/stats` for your usage patterns

**Remember:** Rate limits exist to protect everyone. Help us maintain a fair and secure service for all users! 🔒
