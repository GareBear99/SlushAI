"""
User activity logging system for tracking generations, deletions, saves, and other events.
Auto-truncates logs older than 30 days.
"""
import sqlite3
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class ActivityLogger:
    """Logs user activity events with automatic 30-day retention."""
    
    # Event types
    EVENT_GENERATION_STARTED = 'generation_started'
    EVENT_GENERATION_COMPLETED = 'generation_completed'
    EVENT_GENERATION_FAILED = 'generation_failed'
    EVENT_MODEL_SAVED = 'model_saved'
    EVENT_MODEL_UNSAVED = 'model_unsaved'
    EVENT_MODEL_FAVORITED = 'model_favorited'
    EVENT_MODEL_DELETED_MANUAL = 'model_deleted_manual'
    EVENT_MODEL_DELETED_AUTO = 'model_deleted_auto'
    EVENT_MODEL_DELETED_LIMIT = 'model_deleted_limit'
    EVENT_STORAGE_LIMIT_REACHED = 'storage_limit_reached'
    
    # Cleanup runs daily at midnight
    LOG_RETENTION_DAYS = 30
    CLEANUP_INTERVAL = 86400  # 24 hours
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._init_db()
        self._start_cleanup_thread()
    
    def _init_db(self):
        """Initialize activity log database table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Activity log table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')
        
        # Index for fast user queries
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_activity_user_time 
        ON user_activity_log(user_id, timestamp DESC)
        ''')
        
        # Index for cleanup queries
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_activity_timestamp 
        ON user_activity_log(timestamp)
        ''')
        
        conn.commit()
        conn.close()
    
    def _start_cleanup_thread(self):
        """Start background thread for daily log cleanup."""
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_loop(self):
        """Background loop that runs cleanup daily."""
        while True:
            time.sleep(self.CLEANUP_INTERVAL)
            try:
                self.cleanup_old_logs()
            except Exception as e:
                print(f"Activity log cleanup error: {e}")
    
    def log_event(self, user_id: int, event_type: str, event_data: Dict = None) -> bool:
        """
        Log a user activity event.
        
        Args:
            user_id: User ID
            event_type: Type of event (use EVENT_* constants)
            event_data: Optional dict with event details (will be stored as JSON)
        
        Returns:
            True if logged successfully
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert event_data to JSON string
            data_json = json.dumps(event_data) if event_data else None
            
            cursor.execute('''
            INSERT INTO user_activity_log (user_id, event_type, event_data, timestamp)
            VALUES (?, ?, ?, ?)
            ''', (user_id, event_type, data_json, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Failed to log activity: {e}")
            return False
    
    def get_user_activity(self, user_id: int, limit: int = 100, 
                          event_type: str = None) -> List[Dict]:
        """
        Get recent activity for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of events to return (default 100)
            event_type: Optional filter by event type
        
        Returns:
            List of activity events
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if event_type:
            cursor.execute('''
            SELECT id, event_type, event_data, timestamp
            FROM user_activity_log
            WHERE user_id = ? AND event_type = ?
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (user_id, event_type, limit))
        else:
            cursor.execute('''
            SELECT id, event_type, event_data, timestamp
            FROM user_activity_log
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts
        activity = []
        for row in rows:
            event = {
                'id': row[0],
                'event_type': row[1],
                'event_data': json.loads(row[2]) if row[2] else None,
                'timestamp': row[3]
            }
            activity.append(event)
        
        return activity
    
    def get_activity_stats(self, user_id: int, days: int = 30) -> Dict:
        """
        Get activity statistics for a user.
        
        Args:
            user_id: User ID
            days: Number of days to look back (default 30)
        
        Returns:
            Dict with statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Count events by type
        cursor.execute('''
        SELECT event_type, COUNT(*) 
        FROM user_activity_log
        WHERE user_id = ? AND timestamp >= ?
        GROUP BY event_type
        ''', (user_id, cutoff))
        
        event_counts = dict(cursor.fetchall())
        conn.close()
        
        # Calculate summary stats
        stats = {
            'total_generations': event_counts.get('generation_completed', 0),
            'failed_generations': event_counts.get('generation_failed', 0),
            'models_saved': event_counts.get('model_saved', 0),
            'models_unsaved': event_counts.get('model_unsaved', 0),
            'models_favorited': event_counts.get('model_favorited', 0),
            'manual_deletions': event_counts.get('model_deleted_manual', 0),
            'auto_deletions': event_counts.get('model_deleted_auto', 0),
            'limit_deletions': event_counts.get('model_deleted_limit', 0),
            'storage_limit_hits': event_counts.get('storage_limit_reached', 0),
            'period_days': days
        }
        
        return stats
    
    def cleanup_old_logs(self, days: int = None) -> int:
        """
        Remove activity logs older than specified days.
        
        Args:
            days: Age threshold in days (default: LOG_RETENTION_DAYS = 30)
        
        Returns:
            Number of deleted log entries
        """
        if days is None:
            days = self.LOG_RETENTION_DAYS
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        DELETE FROM user_activity_log WHERE timestamp < ?
        ''', (cutoff,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"Activity log cleanup: Deleted {deleted_count} entries older than {days} days")
        return deleted_count
    
    def get_recent_events(self, user_id: int, event_types: List[str], 
                         limit: int = 10) -> List[Dict]:
        """
        Get recent events of specific types.
        
        Args:
            user_id: User ID
            event_types: List of event types to fetch
            limit: Max results
        
        Returns:
            List of matching events
        """
        if not event_types:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(event_types))
        query = f'''
        SELECT id, event_type, event_data, timestamp
        FROM user_activity_log
        WHERE user_id = ? AND event_type IN ({placeholders})
        ORDER BY timestamp DESC
        LIMIT ?
        '''
        
        params = [user_id] + event_types + [limit]
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for row in rows:
            event = {
                'id': row[0],
                'event_type': row[1],
                'event_data': json.loads(row[2]) if row[2] else None,
                'timestamp': row[3]
            }
            events.append(event)
        
        return events
