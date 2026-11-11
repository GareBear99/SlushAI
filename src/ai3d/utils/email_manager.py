"""Email management system for tracking and viewing all platform emails."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple


class EmailManager:
    """Manages email tracking, viewing, and sending for privileged users."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize email tracking database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Emails table - tracks all sent emails
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL,  -- 'outbound' or 'inbound'
                recipient_email TEXT NOT NULL,
                recipient_name TEXT,
                sender_email TEXT NOT NULL,
                sender_name TEXT,
                subject TEXT NOT NULL,
                body_text TEXT,
                body_html TEXT,
                email_type TEXT,  -- 'verification', 'pin', 'support', 'notification', 'manual'
                related_user_id INTEGER,
                status TEXT DEFAULT 'sent',  -- 'sent', 'failed', 'pending'
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT  -- JSON for additional data
            )
        ''')
        
        # Email threads for grouping related emails
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_subject TEXT NOT NULL,
                participant_email TEXT NOT NULL,
                last_email_id INTEGER,
                email_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (last_email_id) REFERENCES emails(id)
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_recipient ON emails(recipient_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_type ON emails(email_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_created ON emails(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_participant ON email_threads(participant_email)')
        
        conn.commit()
        conn.close()
    
    def log_outbound_email(self, recipient_email: str, subject: str, body_text: str, 
                          body_html: str = None, email_type: str = 'notification',
                          recipient_name: str = None, sender_email: str = None,
                          sender_name: str = 'SlushAI 3D Modeller', user_id: int = None,
                          metadata: dict = None) -> int:
        """Log an outbound email to the database.
        
        Args:
            recipient_email: Email address of recipient
            subject: Email subject line
            body_text: Plain text body
            body_html: HTML body (optional)
            email_type: Type of email (verification, pin, support, etc.)
            recipient_name: Name of recipient (optional)
            sender_email: Sender email (optional, uses default)
            sender_name: Sender name
            user_id: Related user ID (optional)
            metadata: Additional data as dict (optional)
        
        Returns:
            Email ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO emails (
                direction, recipient_email, recipient_name, sender_email, sender_name,
                subject, body_text, body_html, email_type, related_user_id, status, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'sent', ?)
        ''', (
            'outbound',
            recipient_email,
            recipient_name,
            sender_email or 'noreply@slushai.com',
            sender_name,
            subject,
            body_text,
            body_html,
            email_type,
            user_id,
            json.dumps(metadata) if metadata else None
        ))
        
        email_id = cursor.lastrowid
        
        # Update or create thread
        self._update_thread(cursor, recipient_email, subject, email_id)
        
        conn.commit()
        conn.close()
        
        return email_id
    
    def log_inbound_email(self, sender_email: str, subject: str, body_text: str,
                         sender_name: str = None, metadata: dict = None) -> int:
        """Log an inbound email (for future email receiving capability).
        
        Args:
            sender_email: Email address of sender
            subject: Email subject line
            body_text: Email body
            sender_name: Name of sender (optional)
            metadata: Additional data as dict (optional)
        
        Returns:
            Email ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO emails (
                direction, recipient_email, sender_email, sender_name,
                subject, body_text, email_type, status, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, 'support', 'received', ?)
        ''', (
            'inbound',
            'support@slushai.com',  # Our receiving address
            sender_email,
            sender_name,
            subject,
            body_text,
            json.dumps(metadata) if metadata else None
        ))
        
        email_id = cursor.lastrowid
        
        # Update or create thread
        self._update_thread(cursor, sender_email, subject, email_id)
        
        conn.commit()
        conn.close()
        
        return email_id
    
    def _update_thread(self, cursor, participant_email: str, subject: str, email_id: int):
        """Update or create email thread."""
        # Clean subject for threading (remove Re:, Fwd:, etc.)
        clean_subject = subject
        for prefix in ['Re:', 'RE:', 'Fwd:', 'FWD:', 'Fw:']:
            clean_subject = clean_subject.replace(prefix, '').strip()
        
        # Check if thread exists
        cursor.execute('''
            SELECT id FROM email_threads
            WHERE participant_email = ? AND thread_subject = ?
        ''', (participant_email, clean_subject))
        
        thread = cursor.fetchone()
        
        if thread:
            # Update existing thread
            cursor.execute('''
                UPDATE email_threads
                SET last_email_id = ?,
                    email_count = email_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (email_id, thread[0]))
        else:
            # Create new thread
            cursor.execute('''
                INSERT INTO email_threads (
                    thread_subject, participant_email, last_email_id, email_count
                ) VALUES (?, ?, ?, 1)
            ''', (clean_subject, participant_email, email_id))
    
    def get_emails(self, direction: str = None, email_type: str = None, 
                   limit: int = 100, offset: int = 0, 
                   unread_only: bool = False) -> List[Dict]:
        """Get emails with optional filtering.
        
        Args:
            direction: Filter by 'outbound' or 'inbound'
            email_type: Filter by email type
            limit: Max number of emails to return
            offset: Offset for pagination
            unread_only: Only return unread emails
        
        Returns:
            List of email dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = 'SELECT * FROM emails WHERE 1=1'
        params = []
        
        if direction:
            query += ' AND direction = ?'
            params.append(direction)
        
        if email_type:
            query += ' AND email_type = ?'
            params.append(email_type)
        
        if unread_only:
            query += ' AND read_at IS NULL'
        
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        emails = []
        for row in rows:
            email = dict(row)
            if email['metadata']:
                email['metadata'] = json.loads(email['metadata'])
            emails.append(email)
        
        conn.close()
        return emails
    
    def get_email_by_id(self, email_id: int) -> Optional[Dict]:
        """Get a single email by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM emails WHERE id = ?', (email_id,))
        row = cursor.fetchone()
        
        if row:
            email = dict(row)
            if email['metadata']:
                email['metadata'] = json.loads(email['metadata'])
            conn.close()
            return email
        
        conn.close()
        return None
    
    def mark_as_read(self, email_id: int) -> bool:
        """Mark an email as read."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE emails SET read_at = CURRENT_TIMESTAMP
            WHERE id = ? AND read_at IS NULL
        ''', (email_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def get_threads(self, limit: int = 50) -> List[Dict]:
        """Get email threads sorted by most recent activity."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                t.*,
                e.subject as last_subject,
                e.created_at as last_email_at,
                e.direction as last_direction
            FROM email_threads t
            JOIN emails e ON t.last_email_id = e.id
            ORDER BY t.updated_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        threads = [dict(row) for row in rows]
        
        conn.close()
        return threads
    
    def get_thread_emails(self, thread_id: int) -> List[Dict]:
        """Get all emails in a thread."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get thread info
        cursor.execute('SELECT * FROM email_threads WHERE id = ?', (thread_id,))
        thread = cursor.fetchone()
        
        if not thread:
            conn.close()
            return []
        
        # Get all emails matching thread criteria
        cursor.execute('''
            SELECT * FROM emails
            WHERE (recipient_email = ? OR sender_email = ?)
              AND (subject LIKE ? OR subject LIKE ?)
            ORDER BY created_at ASC
        ''', (
            thread['participant_email'],
            thread['participant_email'],
            f"%{thread['thread_subject']}%",
            f"Re: %{thread['thread_subject']}%"
        ))
        
        rows = cursor.fetchall()
        emails = []
        for row in rows:
            email = dict(row)
            if email['metadata']:
                email['metadata'] = json.loads(email['metadata'])
            emails.append(email)
        
        conn.close()
        return emails
    
    def get_email_stats(self) -> Dict:
        """Get email statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total emails
        cursor.execute('SELECT COUNT(*) FROM emails')
        total = cursor.fetchone()[0]
        
        # Outbound vs inbound
        cursor.execute('SELECT direction, COUNT(*) FROM emails GROUP BY direction')
        direction_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By type
        cursor.execute('SELECT email_type, COUNT(*) FROM emails GROUP BY email_type')
        type_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Unread count
        cursor.execute('SELECT COUNT(*) FROM emails WHERE read_at IS NULL AND direction = "inbound"')
        unread = cursor.fetchone()[0]
        
        # Today's count
        cursor.execute('''
            SELECT COUNT(*) FROM emails 
            WHERE DATE(created_at) = DATE('now')
        ''')
        today = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'outbound': direction_stats.get('outbound', 0),
            'inbound': direction_stats.get('inbound', 0),
            'unread': unread,
            'today': today,
            'by_type': type_stats
        }
