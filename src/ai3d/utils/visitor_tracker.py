"""Visitor tracking and analytics for AI3DModeller."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from flask import request
import hashlib


class VisitorTracker:
    """Track visitor sessions, IPs, and request patterns."""
    
    MAX_REQUESTS = 2560  # Max request entries to keep in DB
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = {}  # In-memory cache for visitor IDs
        self._request_counter = 0
        self._init_database()
        self._optimize_database()
    
    def _init_database(self):
        """Initialize SQLite database for visitor tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Visitors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_hash TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                user_agent TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER DEFAULT 1,
                UNIQUE(ip_hash)
            )
        ''')
        
        # Requests table (detailed log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                method TEXT,
                endpoint TEXT,
                path TEXT,
                query_string TEXT,
                status_code INTEGER,
                response_time_ms REAL,
                user_agent TEXT,
                referer TEXT,
                FOREIGN KEY(visitor_id) REFERENCES visitors(id)
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id INTEGER,
                session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_end TIMESTAMP,
                page_views INTEGER DEFAULT 0,
                actions INTEGER DEFAULT 0,
                models_generated INTEGER DEFAULT 0,
                screenshots_taken INTEGER DEFAULT 0,
                FOREIGN KEY(visitor_id) REFERENCES visitors(id)
            )
        ''')
        
        # Analytics aggregates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                unique_visitors INTEGER DEFAULT 0,
                total_requests INTEGER DEFAULT 0,
                models_generated INTEGER DEFAULT 0,
                screenshots_taken INTEGER DEFAULT 0,
                avg_response_time_ms REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _optimize_database(self):
        """Optimize database for minimal resource usage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Enable WAL mode for better concurrency and less locking
        cursor.execute('PRAGMA journal_mode=WAL')
        
        # Reduce sync overhead (safe for analytics data)
        cursor.execute('PRAGMA synchronous=NORMAL')
        
        # Increase cache size for better performance
        cursor.execute('PRAGMA cache_size=-8000')  # 8MB cache
        
        # Enable memory-mapped I/O
        cursor.execute('PRAGMA mmap_size=268435456')  # 256MB
        
        conn.commit()
        conn.close()
    
    def _hash_ip(self, ip: str) -> str:
        """Hash IP address for privacy (GDPR-friendly)."""
        return hashlib.sha256(ip.encode()).hexdigest()[:16]
    
    def track_request(self, 
                     ip_address: str,
                     method: str,
                     endpoint: str,
                     path: str,
                     query_string: str = "",
                     status_code: int = 200,
                     response_time_ms: float = 0,
                     user_agent: str = "",
                     referer: str = "") -> int:
        """Track a request and return visitor ID (optimized for low overhead)."""
        ip_hash = self._hash_ip(ip_address)
        
        # Check cache first to avoid DB hit
        if ip_hash in self._cache:
            visitor_id = self._cache[ip_hash]
        else:
            # Quick connection for visitor lookup
            conn = sqlite3.connect(self.db_path, timeout=1.0)
            conn.execute('PRAGMA synchronous=OFF')  # Fast write
            cursor = conn.cursor()
            
            # Get or create visitor
            cursor.execute('''
                INSERT INTO visitors (ip_hash, ip_address, user_agent, last_seen, visit_count)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(ip_hash) DO UPDATE SET
                    last_seen = CURRENT_TIMESTAMP,
                    visit_count = visit_count + 1
            ''', (ip_hash, ip_address, user_agent))
            
            cursor.execute('SELECT id FROM visitors WHERE ip_hash = ?', (ip_hash,))
            visitor_id = cursor.fetchone()[0]
            
            # Cache for future requests
            self._cache[ip_hash] = visitor_id
            
            conn.commit()
            conn.close()
        
        # Async-style: write request log without blocking
        # Use a separate lightweight connection
        try:
            conn = sqlite3.connect(self.db_path, timeout=0.5)
            conn.execute('PRAGMA synchronous=OFF')
            cursor = conn.cursor()
            
            # Single transaction for both operations
            cursor.execute('''
                INSERT INTO requests 
                (visitor_id, method, endpoint, path, query_string, status_code, 
                 response_time_ms, user_agent, referer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (visitor_id, method, endpoint, path, query_string, status_code,
                  response_time_ms, user_agent, referer))
            
            # Update daily stats
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                INSERT INTO daily_stats (date, total_requests)
                VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_requests = total_requests + 1
            ''', (today,))
            
            conn.commit()
            conn.close()
            
            # Auto-cleanup: truncate old requests every 100 new entries
            self._request_counter += 1
            if self._request_counter >= 100:
                self._truncate_requests()
                self._request_counter = 0
        except sqlite3.OperationalError:
            # If DB is locked, skip this log entry (analytics data is non-critical)
            pass
        
        return visitor_id
    
    def _truncate_requests(self):
        """Keep only the last MAX_REQUESTS entries to prevent unbounded growth."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=0.5)
            cursor = conn.cursor()
            
            # Count total requests
            cursor.execute('SELECT COUNT(*) FROM requests')
            total = cursor.fetchone()[0]
            
            # If over limit, delete oldest entries
            if total > self.MAX_REQUESTS:
                delete_count = total - self.MAX_REQUESTS
                cursor.execute('''
                    DELETE FROM requests WHERE id IN (
                        SELECT id FROM requests ORDER BY id ASC LIMIT ?
                    )
                ''', (delete_count,))
                conn.commit()
            
            conn.close()
        except Exception:
            # Non-critical operation, fail silently
            pass
    
    def log_action(self, visitor_id: int, action_type: str, details: Dict = None):
        """Log specific user actions (model generation, screenshot, etc)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        if action_type == 'model_generated':
            cursor.execute('''
                UPDATE daily_stats SET models_generated = models_generated + 1
                WHERE date = ?
            ''', (today,))
        elif action_type == 'screenshot':
            cursor.execute('''
                UPDATE daily_stats SET screenshots_taken = screenshots_taken + 1
                WHERE date = ?
            ''', (today,))
        
        conn.commit()
        conn.close()
    
    def get_stats(self, days: int = 7) -> Dict:
        """Get analytics for the last N days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total visitors
        cursor.execute('SELECT COUNT(*) FROM visitors')
        total_visitors = cursor.fetchone()[0]
        
        # Active today
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(DISTINCT visitor_id) FROM requests
            WHERE DATE(timestamp) = ?
        ''', (today,))
        active_today = cursor.fetchone()[0]
        
        # Recent stats
        cursor.execute('''
            SELECT date, unique_visitors, total_requests, models_generated, 
                   screenshots_taken, avg_response_time_ms
            FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))
        recent_stats = cursor.fetchall()
        
        # Top endpoints
        cursor.execute('''
            SELECT endpoint, COUNT(*) as count
            FROM requests
            WHERE DATE(timestamp) >= DATE('now', '-7 days')
            GROUP BY endpoint
            ORDER BY count DESC
            LIMIT 10
        ''')
        top_endpoints = cursor.fetchall()
        
        conn.close()
        
        return {
            'total_visitors': total_visitors,
            'active_today': active_today,
            'recent_days': [
                {
                    'date': row[0],
                    'unique_visitors': row[1],
                    'total_requests': row[2],
                    'models_generated': row[3],
                    'screenshots_taken': row[4],
                    'avg_response_time': row[5]
                }
                for row in recent_stats
            ],
            'top_endpoints': [
                {'endpoint': row[0], 'count': row[1]}
                for row in top_endpoints
            ]
        }
    
    def get_visitor_history(self, ip_address: str) -> Dict:
        """Get history for a specific visitor."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        ip_hash = self._hash_ip(ip_address)
        
        cursor.execute('''
            SELECT id, first_seen, last_seen, visit_count
            FROM visitors
            WHERE ip_hash = ?
        ''', (ip_hash,))
        
        visitor = cursor.fetchone()
        if not visitor:
            conn.close()
            return None
        
        visitor_id = visitor[0]
        
        # Get recent requests
        cursor.execute('''
            SELECT timestamp, method, endpoint, path, status_code
            FROM requests
            WHERE visitor_id = ?
            ORDER BY timestamp DESC
            LIMIT 50
        ''', (visitor_id,))
        
        requests = cursor.fetchall()
        conn.close()
        
        return {
            'first_seen': visitor[1],
            'last_seen': visitor[2],
            'visit_count': visitor[3],
            'recent_requests': [
                {
                    'timestamp': req[0],
                    'method': req[1],
                    'endpoint': req[2],
                    'path': req[3],
                    'status_code': req[4]
                }
                for req in requests
            ]
        }
