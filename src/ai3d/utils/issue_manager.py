"""Issue tracking system for community bug reports and feature requests."""
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class IssueManager:
    """Manages community issue tracking and admin responses."""
    
    def __init__(self, db_path: str):
        """Initialize issue manager with database path."""
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables for issue tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Issues table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            user_email TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by INTEGER,
            resolution_note TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # Issue comments table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS issue_comments (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            comment TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (issue_id) REFERENCES issues(issue_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # Admin users table (simple email-based admin list)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            added_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def _get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT admin_id FROM admin_users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    
    def add_admin(self, user_id: int, email: str) -> bool:
        """Add a user as admin."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            INSERT INTO admin_users (user_id, email, added_at)
            VALUES (?, ?, ?)
            ''', (user_id, email, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False  # Already admin
    
    def create_issue(self, user_id: int, user_name: str, user_email: str,
                     title: str, description: str) -> int:
        """Create a new issue."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
        INSERT INTO issues (user_id, user_name, user_email, title, description, 
                           status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
        ''', (user_id, user_name, user_email, title, description, now, now))
        
        issue_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return issue_id
    
    def get_all_issues(self, status_filter: Optional[str] = None,
                       limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all issues, optionally filtered by status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if status_filter:
            cursor.execute('''
            SELECT issue_id, user_id, user_name, user_email, title, description,
                   status, created_at, updated_at, resolved_at, resolved_by, resolution_note
            FROM issues
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''', (status_filter, limit, offset))
        else:
            cursor.execute('''
            SELECT issue_id, user_id, user_name, user_email, title, description,
                   status, created_at, updated_at, resolved_at, resolved_by, resolution_note
            FROM issues
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''', (limit, offset))
        
        issues = []
        for row in cursor.fetchall():
            # Get comment count
            cursor.execute('SELECT COUNT(*) FROM issue_comments WHERE issue_id = ?', (row[0],))
            comment_count = cursor.fetchone()[0]
            
            issues.append({
                'issue_id': row[0],
                'user_id': row[1],
                'user_name': row[2],
                'user_email': row[3],
                'title': row[4],
                'description': row[5],
                'status': row[6],
                'created_at': row[7],
                'updated_at': row[8],
                'resolved_at': row[9],
                'resolved_by': row[10],
                'resolution_note': row[11],
                'comment_count': comment_count
            })
        
        conn.close()
        return issues
    
    def get_recent_issues(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """Get issues from the last N days."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
        SELECT issue_id, user_id, user_name, user_email, title, description,
               status, created_at, updated_at, resolved_at, resolved_by, resolution_note
        FROM issues
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT ?
        ''', (cutoff, limit))
        
        issues = []
        for row in cursor.fetchall():
            cursor.execute('SELECT COUNT(*) FROM issue_comments WHERE issue_id = ?', (row[0],))
            comment_count = cursor.fetchone()[0]
            
            issues.append({
                'issue_id': row[0],
                'user_id': row[1],
                'user_name': row[2],
                'user_email': row[3],
                'title': row[4],
                'description': row[5],
                'status': row[6],
                'created_at': row[7],
                'updated_at': row[8],
                'resolved_at': row[9],
                'resolved_by': row[10],
                'resolution_note': row[11],
                'comment_count': comment_count
            })
        
        conn.close()
        return issues
    
    def get_issue_by_id(self, issue_id: int) -> Optional[Dict]:
        """Get a single issue by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT issue_id, user_id, user_name, user_email, title, description,
               status, created_at, updated_at, resolved_at, resolved_by, resolution_note
        FROM issues
        WHERE issue_id = ?
        ''', (issue_id,))
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        # Get comments
        cursor.execute('''
        SELECT comment_id, user_id, user_name, comment, is_admin, created_at
        FROM issue_comments
        WHERE issue_id = ?
        ORDER BY created_at ASC
        ''', (issue_id,))
        
        comments = []
        for comment_row in cursor.fetchall():
            comments.append({
                'comment_id': comment_row[0],
                'user_id': comment_row[1],
                'user_name': comment_row[2],
                'comment': comment_row[3],
                'is_admin': bool(comment_row[4]),
                'created_at': comment_row[5]
            })
        
        conn.close()
        
        return {
            'issue_id': row[0],
            'user_id': row[1],
            'user_name': row[2],
            'user_email': row[3],
            'title': row[4],
            'description': row[5],
            'status': row[6],
            'created_at': row[7],
            'updated_at': row[8],
            'resolved_at': row[9],
            'resolved_by': row[10],
            'resolution_note': row[11],
            'comments': comments
        }
    
    def update_issue_status(self, issue_id: int, status: str, admin_user_id: int,
                           resolution_note: str = None) -> bool:
        """Update issue status (admin only)."""
        if status not in ['open', 'fixed', 'ignored']:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if status in ['fixed', 'ignored']:
            cursor.execute('''
            UPDATE issues
            SET status = ?, updated_at = ?, resolved_at = ?, 
                resolved_by = ?, resolution_note = ?
            WHERE issue_id = ?
            ''', (status, now, now, admin_user_id, resolution_note, issue_id))
        else:
            # Reopening issue
            cursor.execute('''
            UPDATE issues
            SET status = ?, updated_at = ?, resolved_at = NULL,
                resolved_by = NULL, resolution_note = NULL
            WHERE issue_id = ?
            ''', (status, now, issue_id))
        
        conn.commit()
        conn.close()
        
        return cursor.rowcount > 0
    
    def add_comment(self, issue_id: int, user_id: int, user_name: str,
                    comment: str) -> int:
        """Add a comment to an issue."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        is_admin = self.is_admin(user_id)
        now = datetime.now().isoformat()
        
        cursor.execute('''
        INSERT INTO issue_comments (issue_id, user_id, user_name, comment, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (issue_id, user_id, user_name, comment, is_admin, now))
        
        comment_id = cursor.lastrowid
        
        # Update issue updated_at timestamp
        cursor.execute('''
        UPDATE issues SET updated_at = ? WHERE issue_id = ?
        ''', (now, issue_id))
        
        conn.commit()
        conn.close()
        
        return comment_id
    
    def get_issue_stats(self) -> Dict:
        """Get statistics about issues."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM issues WHERE status = "open"')
        open_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM issues WHERE status = "fixed"')
        fixed_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM issues WHERE status = "ignored"')
        ignored_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM issues')
        total_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'open': open_count,
            'fixed': fixed_count,
            'ignored': ignored_count,
            'total': total_count
        }
