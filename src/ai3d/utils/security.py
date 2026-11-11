"""
Security module for DDoS protection, rate limiting, and attack prevention.
Implements multiple layers of defense against common web attacks.
"""
import hashlib
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path
from functools import wraps
from flask import request, abort, g
import re


class SecurityManager:
    """
    Comprehensive security manager for protecting the application.
    Implements multiple defense layers against attacks.
    """
    
    # Multi-tier progressive blocking system
    # Format: (violation_threshold, block_duration_hours, tier_name)
    BLOCKING_TIERS = [
        (1, 0.083, 'warning'),        # 1st offense: 5 minutes
        (2, 0.5, 'minor'),            # 2nd offense: 30 minutes  
        (3, 2, 'moderate'),           # 3rd offense: 2 hours
        (5, 12, 'serious'),           # 5th offense: 12 hours
        (7, 24, 'severe'),            # 7th offense: 24 hours
        (10, 72, 'critical'),         # 10th offense: 3 days
        (15, 168, 'extreme'),         # 15th offense: 1 week
        (20, 720, 'persistent'),      # 20th offense: 30 days
    ]
    
    # Attack severity scoring for faster escalation
    ATTACK_SEVERITY = {
        'sql_injection': 3,           # High severity - instant tier jump
        'command_injection': 3,
        'path_traversal': 3,
        'xss_attempt': 2,             # Medium severity
        'suspicious_user_agent': 1,   # Low severity
        'rate_limit_exceeded': 1,
        'connection_limit': 1,
        'invalid_input': 1,
    }
    
    # Rate limiting thresholds (requests per window)
    RATE_LIMITS = {
        'api_generate': (5, 60),      # 5 requests per minute
        'api_screenshot': (1, 60),     # 1 request per minute
        'api_issues': (20, 60),        # 20 requests per minute
        'api_crypto': (10, 60),        # 10 requests per minute
        'auth': (5, 300),              # 5 auth attempts per 5 minutes
        'global': (100, 60),           # 100 total requests per minute
    }
    
    # Request size limits (bytes)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload
    MAX_JSON_SIZE = 5 * 1024 * 1024  # 5MB max JSON
    MAX_SCREENSHOT_SIZE = 10 * 1024 * 1024  # 10MB max screenshot
    
    # Connection limits
    MAX_CONNECTIONS_PER_IP = 50  # Increased from 10 to 50
    CONNECTION_TIMEOUT = 10  # Reduced from 300 to 10 seconds
    
    # Blocked patterns (potential attacks)
    BLOCKED_PATTERNS = [
        r'(?i)(union|select|insert|update|delete|drop|create|alter|exec|script)',  # SQL injection
        r'(?i)(<script|javascript:|onerror|onload)',  # XSS attempts
        r'(?i)(\.\.\/|\.\.\\|etc\/passwd|proc\/|sys\/)',  # Path traversal
        r'(?i)(cmd|eval|system|exec|shell)',  # Command injection
    ]
    
    # Suspicious user agents
    BLOCKED_USER_AGENTS = [
        'sqlmap', 'nikto', 'nmap', 'masscan', 'metasploit',
        'havij', 'acunetix', 'w3af', 'netsparker', 'webinspect',
    ]
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._init_db()
        self.connection_tracker = {}  # IP -> (count, last_reset)
        self.attack_stats_log = Path(db_path).parent / 'attack_stats_monthly.log'
        self.blocklist_json = Path(db_path).parent / 'blocklist.json'
        self.blocked_accounts_json = Path(db_path).parent / 'blocked_accounts.json'
        self._check_monthly_rollover()
        self._load_json_blocklists()
    
    def _init_db(self):
        """Initialize security tracking database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Rate limit tracking
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            request_count INTEGER DEFAULT 1,
            window_start REAL NOT NULL,
            blocked_until REAL
        )
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_identifier_endpoint 
        ON rate_limits(identifier, endpoint)
        ''')
        
        # Blocked IPs with violation tracking
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_ips (
            ip_address TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            blocked_at TEXT NOT NULL,
            blocked_until TEXT,
            permanent BOOLEAN DEFAULT 0,
            violation_count INTEGER DEFAULT 1,
            tier_level TEXT DEFAULT 'warning'
        )
        ''')
        
        # Attack log
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS attack_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            attack_type TEXT NOT NULL,
            endpoint TEXT,
            payload TEXT,
            timestamp TEXT NOT NULL
        )
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ip_timestamp 
        ON attack_log(ip_address, timestamp)
        ''')
        
        conn.commit()
        conn.close()
    
    def _check_monthly_rollover(self):
        """Check if we need to generate monthly report and reset."""
        try:
            current_month = datetime.now().strftime('%Y-%m')
            marker_file = Path(self.db_path).parent / f'.attack_stats_{current_month}'
            
            if not marker_file.exists():
                # Generate report for previous month
                self._generate_monthly_report()
                # Create marker for current month
                marker_file.touch()
                
                # Clean up old marker files
                for old_marker in Path(self.db_path).parent.glob('.attack_stats_*'):
                    if old_marker.name != f'.attack_stats_{current_month}':
                        old_marker.unlink()
        except Exception as e:
            print(f"Monthly rollover check failed: {e}")
    
    def _generate_monthly_report(self):
        """Generate monthly attack statistics report."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get stats from previous month
            last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
            
            # Attack type breakdown
            cursor.execute('''
            SELECT attack_type, COUNT(*) as count
            FROM attack_log
            WHERE timestamp LIKE ?
            GROUP BY attack_type
            ORDER BY count DESC
            ''', (f"{last_month}%",))
            
            attack_breakdown = cursor.fetchall()
            
            # Top attacking IPs
            cursor.execute('''
            SELECT ip_address, COUNT(*) as count
            FROM attack_log
            WHERE timestamp LIKE ?
            GROUP BY ip_address
            ORDER BY count DESC
            LIMIT 10
            ''', (f"{last_month}%",))
            
            top_ips = cursor.fetchall()
            
            # Total attacks
            cursor.execute('''
            SELECT COUNT(*) FROM attack_log WHERE timestamp LIKE ?
            ''', (f"{last_month}%",))
            
            total_attacks = cursor.fetchone()[0]
            
            # Blocked IPs count
            cursor.execute('''
            SELECT COUNT(*) FROM blocked_ips WHERE blocked_at LIKE ?
            ''', (f"{last_month}%",))
            
            blocked_ips_count = cursor.fetchone()[0]
            
            conn.close()
            
            # Write report
            if total_attacks > 0:
                with open(self.attack_stats_log, 'a') as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"MONTHLY SECURITY REPORT - {last_month}\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"Generated: {datetime.now().isoformat()}\n\n")
                    
                    f.write(f"📊 SUMMARY\n")
                    f.write(f"Total Attacks Blocked: {total_attacks}\n")
                    f.write(f"IPs Blocked: {blocked_ips_count}\n\n")
                    
                    f.write(f"🎯 ATTACK TYPE BREAKDOWN\n")
                    for attack_type, count in attack_breakdown:
                        percentage = (count / total_attacks) * 100
                        f.write(f"  {attack_type:30s}: {count:6d} ({percentage:5.1f}%)\n")
                    
                    f.write(f"\n🚨 TOP 10 ATTACKING IPs\n")
                    for ip, count in top_ips:
                        f.write(f"  {ip:20s}: {count:6d} attacks\n")
                    
                    f.write(f"\n{'='*60}\n")
                
                # Truncate old attack logs (keep only last 3 months)
                self._truncate_old_attacks()
                
        except Exception as e:
            print(f"Failed to generate monthly report: {e}")
    
    def _truncate_old_attacks(self):
        """Remove attack logs older than 3 months to prevent DB bloat."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            
            cursor.execute('''
            DELETE FROM attack_log WHERE timestamp < ?
            ''', (three_months_ago,))
            
            deleted = cursor.rowcount
            
            # Also clean up old blocked IPs
            cursor.execute('''
            DELETE FROM blocked_ips 
            WHERE permanent = 0 AND blocked_until < ?
            ''', (datetime.now().isoformat(),))
            
            conn.commit()
            conn.close()
            
            if deleted > 0:
                print(f"Truncated {deleted} old attack logs (>3 months)")
                
        except Exception as e:
            print(f"Failed to truncate old attacks: {e}")
    
    def get_attack_stats(self, days: int = 30) -> Dict:
        """Get attack statistics for the last N days."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Attack type breakdown
            cursor.execute('''
            SELECT attack_type, COUNT(*) as count
            FROM attack_log
            WHERE timestamp > ?
            GROUP BY attack_type
            ORDER BY count DESC
            ''', (cutoff,))
            
            attack_types = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total attacks
            cursor.execute('''
            SELECT COUNT(*) FROM attack_log WHERE timestamp > ?
            ''', (cutoff,))
            
            total = cursor.fetchone()[0]
            
            # Blocked IPs
            cursor.execute('''
            SELECT COUNT(*) FROM blocked_ips WHERE blocked_at > ?
            ''', (cutoff,))
            
            blocked = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'period_days': days,
                'total_attacks': total,
                'blocked_ips': blocked,
                'attack_types': attack_types
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def check_request_security(self, ip_address: str, endpoint: str,
                               user_agent: str = None) -> Tuple[bool, str]:
        """
        Comprehensive security check for incoming request.
        Returns (is_safe, reason_if_blocked)
        """
        # Whitelist localhost for development
        if ip_address in ['127.0.0.1', 'localhost', '::1']:
            return True, ""
        
        # Check if IP is blocked
        if self.is_ip_blocked(ip_address):
            return False, "IP blocked due to suspicious activity"
        
        # Check user agent
        if user_agent and self._is_suspicious_user_agent(user_agent):
            self._log_attack(ip_address, 'suspicious_user_agent', endpoint, user_agent)
            self._block_ip(ip_address, 'Suspicious user agent detected', hours=24)
            return False, "Suspicious user agent"
        
        # Check connection limits (blocks DDoS attacks, delays normal bursts)
        if not self._check_connection_limit(ip_address):
            return False, "DDoS attack detected - IP blocked"
        
        # Check rate limits
        can_proceed, retry_after = self.check_rate_limit(ip_address, endpoint)
        if not can_proceed:
            return False, f"Rate limit exceeded. Retry after {retry_after}s"
        
        return True, ""
    
    def validate_input(self, data: str, input_type: str = 'general') -> Tuple[bool, str]:
        """
        Validate input data for malicious patterns.
        Returns (is_safe, reason_if_unsafe)
        """
        if not isinstance(data, str):
            return True, ""  # Non-string data handled separately
        
        # Check for blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, data):
                return False, f"Potentially malicious pattern detected"
        
        # Type-specific validation
        if input_type == 'email':
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data):
                return False, "Invalid email format"
        
        elif input_type == 'filename':
            if re.search(r'[<>:"|?*\x00-\x1f]|\.\.|^\/|^\\', data):
                return False, "Invalid filename"
        
        elif input_type == 'path':
            # Prevent path traversal
            if '..' in data or data.startswith('/') or '\\' in data:
                return False, "Invalid path"
            # Shell metacharacters have no business in a model path. The
            # general patterns miss `; rm -rf /`, backticks and $(...),
            # which the old shell tests assumed were blocked (Stage 3, #15:
            # a unit test caught validate_input('test.obj; rm -rf /')
            # returning safe). Kept path-only on purpose: the same check
            # on every POST value would false-positive on passwords
            # containing ';' or '$'.
            if re.search(r'[;`|\n\r\x00]|\$\(|&&', data):
                return False, "Shell metacharacters not allowed in path"
        
        return True, ""
    
    def check_rate_limit(self, identifier: str, endpoint: str) -> Tuple[bool, int]:
        """
        Check if request is within rate limits.
        Returns (allowed, retry_after_seconds)
        """
        # Determine rate limit for endpoint
        limit_key = self._get_limit_key(endpoint)
        if limit_key not in self.RATE_LIMITS:
            limit_key = 'global'
        
        max_requests, window_seconds = self.RATE_LIMITS[limit_key]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = time.time()
        window_start = now - window_seconds
        
        # Clean old entries
        cursor.execute('''
        DELETE FROM rate_limits 
        WHERE window_start < ? AND (blocked_until IS NULL OR blocked_until < ?)
        ''', (window_start, now))
        
        # Check if currently blocked
        cursor.execute('''
        SELECT blocked_until FROM rate_limits
        WHERE identifier = ? AND endpoint = ? AND blocked_until > ?
        ''', (identifier, limit_key, now))
        
        blocked = cursor.fetchone()
        if blocked:
            retry_after = int(blocked[0] - now)
            conn.close()
            return False, retry_after
        
        # Count recent requests
        cursor.execute('''
        SELECT request_count FROM rate_limits
        WHERE identifier = ? AND endpoint = ? AND window_start > ?
        ''', (identifier, limit_key, window_start))
        
        result = cursor.fetchone()
        current_count = result[0] if result else 0
        
        if current_count >= max_requests:
            # Block for 5 minutes
            blocked_until = now + 300
            cursor.execute('''
            INSERT OR REPLACE INTO rate_limits 
            (identifier, endpoint, request_count, window_start, blocked_until)
            VALUES (?, ?, ?, ?, ?)
            ''', (identifier, limit_key, current_count + 1, now, blocked_until))
            
            conn.commit()
            conn.close()
            return False, 300
        
        # Update or insert counter
        if result:
            cursor.execute('''
            UPDATE rate_limits SET request_count = request_count + 1
            WHERE identifier = ? AND endpoint = ? AND window_start > ?
            ''', (identifier, limit_key, window_start))
        else:
            cursor.execute('''
            INSERT INTO rate_limits (identifier, endpoint, request_count, window_start)
            VALUES (?, ?, 1, ?)
            ''', (identifier, limit_key, now))
        
        conn.commit()
        conn.close()
        return True, 0
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP is currently blocked."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 1 FROM blocked_ips
        WHERE ip_address = ? AND (permanent = 1 OR blocked_until > ?)
        ''', (ip_address, datetime.now().isoformat()))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def _block_ip(self, ip_address: str, reason: str, hours: int = None, permanent: bool = False, attack_type: str = 'unknown'):
        """Block an IP address with progressive tier escalation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get current violation count for this IP (last 90 days)
        ninety_days_ago = (datetime.now() - timedelta(days=90)).isoformat()
        cursor.execute('''
        SELECT COUNT(*) FROM attack_log 
        WHERE ip_address = ? AND timestamp > ?
        ''', (ip_address, ninety_days_ago))
        
        violation_count = cursor.fetchone()[0]
        
        # Add severity multiplier based on attack type
        severity = self.ATTACK_SEVERITY.get(attack_type, 1)
        violation_count += severity
        
        # Determine blocking tier
        tier_name = 'warning'
        block_hours = 0.083  # Default: 5 minutes
        
        for threshold, duration, tier in self.BLOCKING_TIERS:
            if violation_count >= threshold:
                tier_name = tier
                block_hours = duration
        
        # Permanent block for extreme persistent offenders
        if permanent or violation_count >= 30:
            blocked_until = None
            permanent = True
            tier_name = 'permanent'
        else:
            blocked_until = (datetime.now() + timedelta(hours=block_hours)).isoformat()
        
        # Update or insert block record
        cursor.execute('''
        INSERT OR REPLACE INTO blocked_ips 
        (ip_address, reason, blocked_at, blocked_until, permanent, violation_count, tier_level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ip_address, f"{reason} (Tier: {tier_name})", datetime.now().isoformat(), 
              blocked_until, permanent, violation_count, tier_name))
        
        conn.commit()
        conn.close()
        
        # Log the block action
        duration_str = "PERMANENT" if permanent else f"{block_hours}h"
        print(f"🚫 BLOCKED: {ip_address} | Tier: {tier_name} ({violation_count} violations) | Duration: {duration_str} | Reason: {attack_type}")
        
        # Auto-export to JSON for persistent blocklist
        try:
            self.export_blocklist_to_json()
        except Exception as e:
            print(f"Warning: Failed to export blocklist: {e}")
    
    def _log_attack(self, ip_address: str, attack_type: str, endpoint: str, payload: str = None):
        """Log potential attack attempt."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO attack_log (ip_address, attack_type, endpoint, payload, timestamp)
        VALUES (?, ?, ?, ?, ?)
        ''', (ip_address, attack_type, endpoint, payload[:1000] if payload else None, 
              datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def _is_suspicious_user_agent(self, user_agent: str) -> bool:
        """Check if user agent is from known attack tools."""
        if not user_agent:
            return True  # No user agent is suspicious
        
        user_agent_lower = user_agent.lower()
        return any(blocked in user_agent_lower for blocked in self.BLOCKED_USER_AGENTS)
    
    def _check_connection_limit(self, ip_address: str) -> bool:
        """Check if IP has too many concurrent connections."""
        now = time.time()
        
        # Clean old connections (10 second window)
        self.connection_tracker = {
            ip: (count, last) for ip, (count, last) in self.connection_tracker.items()
            if now - last < self.CONNECTION_TIMEOUT
        }
        
        # Check current connections
        if ip_address in self.connection_tracker:
            count, last_time = self.connection_tracker[ip_address]
            
            # DDoS detection: 1000+ requests in 10 seconds = block
            if count >= 1000:
                self._log_attack(ip_address, 'ddos_attempt', 'connection_limit', f'{count} requests in 10 seconds')
                self._block_ip(ip_address, f'DDoS attack detected: {count} requests in 10 seconds', hours=24, attack_type='ddos_attempt')
                return False  # Block the request
            
            # Normal rate limiting: 50+ requests in 10 seconds = 1s delay
            elif count >= self.MAX_CONNECTIONS_PER_IP:
                # Add a 1-second delay but don't block
                print(f"⏱️  Connection rate-limit: {ip_address} ({count}/{self.MAX_CONNECTIONS_PER_IP}) - 1s delay applied")
                time.sleep(1)
            
            self.connection_tracker[ip_address] = (count + 1, now)
        else:
            self.connection_tracker[ip_address] = (1, now)
        
        return True  # Return True unless DDoS detected
    
    def _get_limit_key(self, endpoint: str) -> str:
        """Map endpoint to rate limit key."""
        if '/api/generate' in endpoint or '/generate' in endpoint:
            return 'api_generate'
        elif '/api/screenshot' in endpoint:
            return 'api_screenshot'
        elif '/api/issues' in endpoint:
            return 'api_issues'
        elif '/api/crypto' in endpoint:
            return 'api_crypto'
        elif '/auth/' in endpoint:
            return 'auth'
        return 'global'
    
    def sanitize_error_message(self, error: str) -> str:
        """Remove sensitive information from error messages."""
        # Remove file paths
        error = re.sub(r'(/[\w/]+/[\w/.]+)', '[PATH]', error)
        # Remove SQL details
        error = re.sub(r'(sqlite3\.|SQL|database)', '[DB]', error, flags=re.IGNORECASE)
        # Remove internal details
        error = re.sub(r'(File ".*?", line \d+)', '[CODE]', error)
        return error
    
    def _load_json_blocklists(self):
        """Load blocked IPs and accounts from JSON files on startup."""
        import json
        
        try:
            # Load blocked IPs
            if self.blocklist_json.exists():
                with open(self.blocklist_json, 'r') as f:
                    data = json.load(f)
                    print(f"Loaded {len(data.get('blocked_ips', []))} blocked IPs from JSON")
                    
                    # Import into database
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    
                    for entry in data.get('blocked_ips', []):
                        cursor.execute('''
                        INSERT OR IGNORE INTO blocked_ips 
                        (ip_address, reason, blocked_at, blocked_until, permanent, violation_count, tier_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            entry['ip'],
                            entry.get('reason', 'Imported from blocklist'),
                            entry.get('blocked_at', datetime.now().isoformat()),
                            entry.get('blocked_until'),
                            entry.get('permanent', 0),
                            entry.get('violations', 1),
                            entry.get('tier', 'warning')
                        ))
                    
                    conn.commit()
                    conn.close()
        except Exception as e:
            print(f"Failed to load JSON blocklists: {e}")
    
    def export_blocklist_to_json(self):
        """Export blocked IPs and accounts to JSON files."""
        import json
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Export blocked IPs
            cursor.execute('''
            SELECT ip_address, reason, blocked_at, blocked_until, permanent, violation_count, tier_level
            FROM blocked_ips
            WHERE permanent = 1 OR blocked_until > ?
            ''', (datetime.now().isoformat(),))
            
            blocked_ips = []
            for row in cursor.fetchall():
                blocked_ips.append({
                    'ip': row[0],
                    'reason': row[1],
                    'blocked_at': row[2],
                    'blocked_until': row[3],
                    'permanent': bool(row[4]),
                    'violations': row[5],
                    'tier': row[6]
                })
            
            conn.close()
            
            # Write to JSON
            with open(self.blocklist_json, 'w') as f:
                json.dump({
                    'last_updated': datetime.now().isoformat(),
                    'blocked_ips': blocked_ips
                }, f, indent=2)
            
            print(f"✅ Exported {len(blocked_ips)} blocked IPs to {self.blocklist_json}")
            return len(blocked_ips)
            
        except Exception as e:
            print(f"Failed to export blocklist: {e}")
            return 0


def create_security_headers():
    """Generate secure HTTP headers."""
    return {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.socket.io; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss: https:;",
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
    }
