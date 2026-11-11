# Security & Features Documentation

## 🔒 Security Implementation

### Multi-Layer DDoS Protection

#### 1. **Rate Limiting**
- **Global**: 100 requests/minute per IP
- **API Generate**: 5 requests/minute per user
- **API Screenshot**: 1 request/minute per user (60s cooldown)
- **API Issues**: 20 requests/minute per user
- **API Crypto**: 10 requests/minute per user
- **API Favorites**: 30 requests/minute per user
- **Auth Endpoints**: 5 attempts per 5 minutes
- Auto-blocking: 5 minutes on rate limit breach

#### 2. **Connection Limits**
- Max 10 concurrent connections per IP
- 5-minute connection timeout
- Automatic connection cleanup

#### 3. **Request Size Limits**
- Max upload: 50MB
- Max JSON: 5MB (auto-enforced)
- Max screenshot: 10MB

### Attack Prevention

#### 1. **Input Validation**
Blocks patterns for:
- SQL injection (`union`, `select`, `drop`, etc.)
- XSS attacks (`<script>`, `javascript:`, `onerror`)
- Path traversal (`../`, `../../`, `/etc/passwd`)
- Command injection (`eval`, `exec`, `system`)

#### 2. **User Agent Filtering**
Blocks known attack tools:
- sqlmap, nikto, nmap, masscan
- metasploit, havij, acunetix
- w3af, netsparker, webinspect

#### 3. **IP Blocking**
- Automatic blocking on suspicious activity
- Temporary blocks: 24 hours
- Permanent blocks for severe attacks
- Attack logging with payload capture

### Security Headers

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: (configured for app needs)
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### Data Protection

#### 1. **Error Sanitization**
- File paths redacted → `[PATH]`
- SQL details redacted → `[DB]`
- Internal code references redacted → `[CODE]`
- Server version header removed

#### 2. **Session Security**
- HTTPOnly cookies
- SameSite: Lax
- 30-day session lifetime
- Secure flag (production with HTTPS)

#### 3. **Authentication**
- OAuth 2.0 with Google
- Server-side session management
- No client-side credential storage

## 📂 Favorites & Storage Management

### Favorites System

#### Limits
- **10 favorites per user** (free accounts)
- **32 total models saved per user**
- Auto-replacement of oldest non-favorited model when limit reached

#### Timer System
- **36-hour auto-deletion** for non-favorited models
- **∞ (Unlimited)** for favorited models
- Timer display:
  - `36h` → hours remaining
  - `1d`, `2d` → days remaining
  - `45m` → minutes remaining
  - `Expired` → pending deletion
  - `∞` → favorited (protected)

#### Timer Restart
- When unfavoriting a model, timer **resets to 36 hours**
- Allows re-evaluation before permanent deletion

### Auto-Cleanup

#### Background Process
- Runs every hour
- Deletes non-favorited models older than 36 hours
- Cleans orphaned database entries
- Logs cleanup statistics

#### Storage Stats
Per-user tracking:
- Total models and size
- Favorited models and size
- Pending cleanup count and size
- All accessible via API

## 📊 Storage Limits Enforcement

### Per-User Limits
1. **Registration**: New model registered when generated
2. **Count Check**: Current total models checked
3. **Enforcement**: If at 32 models:
   - Find oldest non-favorited model
   - Delete physical file
   - Remove from database
   - Insert new model

### Protection
- Favorited models **never auto-deleted**
- User must manually remove favorites to free space
- Prevents accidental data loss

## 🔍 Security Monitoring

### Attack Log Database
Tracks:
- IP address
- Attack type (SQL injection, XSS, suspicious UA, etc.)
- Target endpoint
- Payload (first 1000 chars)
- Timestamp

### Rate Limit Database
Tracks:
- Identifier (user ID or IP)
- Endpoint
- Request count
- Window start
- Block expiry

### Blocked IPs Database
Tracks:
- IP address
- Block reason
- Block timestamp
- Block expiry
- Permanent flag

## 🛡️ Best Practices Implemented

### 1. **Defense in Depth**
- Multiple security layers
- Redundant protections
- Fail-safe defaults

### 2. **Principle of Least Privilege**
- User-scoped operations
- Admin-only endpoints (issues status updates)
- Path ownership verification

### 3. **Secure Defaults**
- All errors sanitized by default
- Rate limits on all endpoints
- Input validation on all POST data

### 4. **Logging & Auditing**
- All attacks logged
- Rate limit hits tracked
- Admin actions audited

### 5. **Data Minimization**
- Auto-cleanup prevents data accumulation
- Old logs archived and truncated
- Temporary files deleted after processing

## 🚀 API Endpoints

### Favorites
```
POST   /api/favorites/add       - Add to favorites (max 10)
POST   /api/favorites/remove    - Remove & restart timer
GET    /api/favorites/list      - List all favorites
GET    /api/models/recent       - Recent models with timer
GET    /api/favorites/stats     - Storage statistics
```

### Security Monitoring (Admin)
```
GET    /api/security/attacks    - Attack log
GET    /api/security/blocked    - Blocked IPs
POST   /api/security/unblock    - Unblock IP (admin)
```

## 🔧 Configuration

### Environment Variables
```bash
# Security
SECRET_KEY=<random-key>

# Database Paths (auto-created)
SECURITY_DB=logs/security.db
FAVORITES_DB=logs/favorites.db

# Cleanup Settings (in code)
CLEANUP_HOURS=36
CLEANUP_INTERVAL=3600  # 1 hour
MAX_FAVORITES=10
MAX_SAVED_MODELS=32
```

## 📈 Performance Impact

### Minimal Overhead
- Security checks: <5ms per request
- Database queries: Indexed for speed
- Background cleanup: Runs off-thread
- Connection tracking: In-memory only

### Scalability
- SQLite for simplicity (10K+ requests/day capable)
- Can migrate to PostgreSQL for larger scale
- Redis for distributed rate limiting (future)

## ✅ Security Checklist

- [x] DDoS protection with multi-tier rate limiting
- [x] SQL injection prevention
- [x] XSS attack prevention
- [x] Path traversal prevention
- [x] Command injection prevention
- [x] User agent filtering
- [x] IP blocking system
- [x] Security headers
- [x] Error sanitization
- [x] Session security
- [x] Input validation
- [x] Attack logging
- [x] Auto-cleanup to prevent data leaks
- [x] Request size limits
- [x] Connection limits
- [x] CSRF protection (via SameSite cookies)

## 🎯 Future Enhancements

1. **CAPTCHA** on repeated failures
2. **2FA** for admin accounts
3. **Honeypot endpoints** to detect scanners
4. **IP geofencing** for high-risk regions
5. **Web Application Firewall (WAF)** integration
6. **Real-time threat feed** integration
7. **Anomaly detection** with ML
