"""
Favorites manager for storing user's favorite 3D models.
Enforces plan-specific limits with automatic replacement of oldest unsaved models.
Auto-deletes unsaved, non-favorited models older than retention period.
"""
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import threading
import time

try:
    from .activity_logger import ActivityLogger
except ImportError:
    ActivityLogger = None


class FavoritesManager:
    """Manages user favorites with plan-specific limits and auto-cleanup."""
    
    # Default limits for free plan
    DEFAULT_MAX_FAVORITES = 10
    DEFAULT_MAX_SAVED_MODELS = 32
    DEFAULT_CLEANUP_HOURS = 36
    CLEANUP_INTERVAL = 3600  # Run cleanup every hour
    
    def __init__(self, db_path: str, generated_models_dir: str, user_manager=None, activity_logger=None):
        self.db_path = Path(db_path)
        self.generated_models_dir = Path(generated_models_dir)
        self.user_manager = user_manager  # Optional: for plan-specific limits
        self.activity_logger = activity_logger  # Optional: for activity logging
        self._init_db()
        self._start_cleanup_thread()
    
    def _get_user_limits(self, user_id: str) -> Dict:
        """Get storage limits for user based on their plan."""
        if self.user_manager:
            try:
                # Convert string user_id to int if needed
                uid = int(user_id) if isinstance(user_id, str) else user_id
                return self.user_manager.get_user_storage_limits(uid)
            except Exception:
                pass
        
        # Default to free plan limits
        return {
            'max_favorites': self.DEFAULT_MAX_FAVORITES,
            'max_saved_models': self.DEFAULT_MAX_SAVED_MODELS,
            'deletion_hours': self.DEFAULT_CLEANUP_HOURS
        }
    
    def _init_db(self):
        """Initialize favorites database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            model_path TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(user_id, model_path)
        )
        ''')
        
        # Track all generated models for cleanup
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS generated_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            model_path TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            file_size INTEGER,
            is_saved BOOLEAN DEFAULT 0,
            is_favorited BOOLEAN DEFAULT 0,
            UNIQUE(model_path)
        )
        ''')
        
        # Migrate existing table to add new columns
        cursor.execute("PRAGMA table_info(generated_models)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'is_saved' not in columns:
            cursor.execute('ALTER TABLE generated_models ADD COLUMN is_saved BOOLEAN DEFAULT 0')
        if 'is_favorited' not in columns:
            cursor.execute('ALTER TABLE generated_models ADD COLUMN is_favorited BOOLEAN DEFAULT 0')
        
        # Index for faster queries
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_id ON user_favorites(user_id)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_generated_user ON generated_models(user_id)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_generated_at ON generated_models(generated_at)
        ''')
        
        conn.commit()
        conn.close()
    
    def _start_cleanup_thread(self):
        """Start background thread for auto-cleanup."""
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_loop(self):
        """Background loop that runs cleanup periodically."""
        while True:
            time.sleep(self.CLEANUP_INTERVAL)
            try:
                self.cleanup_old_models()
            except Exception as e:
                print(f"Cleanup error: {e}")
    
    def get_user_model_paths(self, user_id: str):
        """Absolute paths of every model registered to this user (Stage 3,
        #9 — the ownership source for /api/models and /outputs/)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT model_path FROM generated_models WHERE user_id = ?',
                (user_id,))
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def user_owns_model(self, user_id: str, model_path: str) -> bool:
        """True if this exact model path is registered to this user."""
        try:
            import os as _os
            wanted = _os.path.realpath(str(model_path))
            return any(_os.path.realpath(p) == wanted
                       for p in self.get_user_model_paths(user_id))
        except Exception:
            return False

    def register_generated_model(self, user_id: str, model_path: str):
        """Register a newly generated model for tracking. Enforces plan-specific model limit per user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Get user's plan limits
            limits = self._get_user_limits(user_id)
            max_saved = limits['max_saved_models']
            
            file_size = 0
            if os.path.exists(model_path):
                file_size = os.path.getsize(model_path)
            
            # Check total saved models count (including favorites)
            cursor.execute('''
            SELECT COUNT(*) FROM generated_models WHERE user_id = ?
            ''', (user_id,))
            total_count = cursor.fetchone()[0]
            
            # If at limit, try to remove oldest UNSAVED model first
            if total_count >= max_saved:
                # Priority: Remove unsaved, unfavorited models first
                cursor.execute('''
                SELECT g.model_path FROM generated_models g
                WHERE g.user_id = ? AND g.is_saved = 0 AND g.is_favorited = 0
                ORDER BY g.generated_at ASC
                LIMIT 1
                ''', (user_id,))
                
                oldest = cursor.fetchone()
                if oldest:
                    oldest_path = oldest[0]
                    # Delete physical file
                    if os.path.exists(oldest_path):
                        try:
                            os.remove(oldest_path)
                            # Log deletion
                            if self.activity_logger:
                                self.activity_logger.log_event(
                                    int(user_id), 
                                    ActivityLogger.EVENT_MODEL_DELETED_LIMIT,
                                    {'model_path': oldest_path, 'reason': 'storage_limit_reached'}
                                )
                        except Exception:
                            pass
                    # Remove from database
                    cursor.execute('DELETE FROM generated_models WHERE model_path = ?', (oldest_path,))
                else:
                    # No unsaved models available - user must manually unsave/delete
                    conn.close()
                    # Log storage limit hit
                    if self.activity_logger:
                        self.activity_logger.log_event(
                            int(user_id),
                            ActivityLogger.EVENT_STORAGE_LIMIT_REACHED,
                            {'max_saved_models': max_saved, 'message': 'All models are saved or favorited'}
                        )
                    raise Exception(f"Storage limit reached ({max_saved} models). Please unsave or delete some models to continue.")
            
            # Insert new model
            cursor.execute('''
            INSERT OR REPLACE INTO generated_models 
            (user_id, model_path, generated_at, file_size)
            VALUES (?, ?, ?, ?)
            ''', (user_id, model_path, datetime.now().isoformat(), file_size))
            
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
    
    def cleanup_old_models(self, user_id: str = None) -> Dict:
        """
        Delete non-favorited models older than plan-specific hours.
        If user_id provided, only clean that user's models.
        Returns cleanup stats.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        deleted_count = 0
        freed_bytes = 0
        
        # If specific user, use their plan's deletion hours
        if user_id:
            limits = self._get_user_limits(user_id)
            cutoff_time = (datetime.now() - timedelta(hours=limits['deletion_hours'])).isoformat()
            
            cursor.execute('''
            SELECT g.model_path, g.file_size, g.user_id
            FROM generated_models g
            WHERE g.user_id = ? AND g.generated_at < ? AND g.is_saved = 0 AND g.is_favorited = 0
            ''', (user_id, cutoff_time))
            
            old_models = cursor.fetchall()
        else:
            # Clean all users with their respective limits
            # Get all unique users
            cursor.execute('SELECT DISTINCT user_id FROM generated_models')
            user_ids = [row[0] for row in cursor.fetchall()]
            
            all_old_models = []
            for uid in user_ids:
                limits = self._get_user_limits(uid)
                cutoff = (datetime.now() - timedelta(hours=limits['deletion_hours'])).isoformat()
                
                cursor.execute('''
                SELECT g.model_path, g.file_size, g.user_id
                FROM generated_models g
                WHERE g.user_id = ? AND g.generated_at < ? AND g.is_saved = 0 AND g.is_favorited = 0
                ''', (uid, cutoff))
                
                all_old_models.extend(cursor.fetchall())
            
            old_models = all_old_models
        
        try:
            # Process the old models we found
            for model_path, file_size, uid in old_models:
                # Delete physical file
                if os.path.exists(model_path):
                    try:
                        os.remove(model_path)
                        freed_bytes += file_size or 0
                        deleted_count += 1
                        # Log automatic deletion
                        if self.activity_logger:
                            self.activity_logger.log_event(
                                int(uid),
                                ActivityLogger.EVENT_MODEL_DELETED_AUTO,
                                {'model_path': model_path, 'reason': 'retention_period_expired'}
                            )
                    except Exception as e:
                        print(f"Failed to delete {model_path}: {e}")
                
                # Remove from database
                cursor.execute('''
                DELETE FROM generated_models WHERE model_path = ?
                ''', (model_path,))
            
            # Also clean up database entries for files that no longer exist
            cursor.execute('SELECT model_path FROM generated_models')
            all_models = cursor.fetchall()
            
            for (model_path,) in all_models:
                if not os.path.exists(model_path):
                    cursor.execute('DELETE FROM generated_models WHERE model_path = ?', (model_path,))
                    # Also remove from favorites if it doesn't exist
                    cursor.execute('DELETE FROM user_favorites WHERE model_path = ?', (model_path,))
            
            conn.commit()
            
            # Return appropriate cutoff time
            return_cutoff = cutoff_time if user_id else 'variable_by_user'
            
            return {
                'deleted_count': deleted_count,
                'freed_mb': round(freed_bytes / (1024 * 1024), 2),
                'cutoff_time': return_cutoff
            }
            
        except Exception as e:
            conn.rollback()
            return {'error': str(e)}
        finally:
            conn.close()
    
    def add_favorite(self, user_id: str, model_path: str) -> Dict:
        """
        Add model to favorites. Auto-removes oldest if limit reached.
        Returns dict with status and message.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Verify model exists and belongs to user
            cursor.execute('''
            SELECT user_id FROM generated_models WHERE model_path = ?
            ''', (model_path,))
            
            result = cursor.fetchone()
            if not result:
                return {'success': False, 'message': 'Model not found'}
            
            if result[0] != user_id:
                return {'success': False, 'message': 'Access denied'}
            
            # Check if already favorited
            cursor.execute('''
            SELECT id FROM user_favorites WHERE user_id = ? AND model_path = ?
            ''', (user_id, model_path))
            
            if cursor.fetchone():
                return {'success': True, 'message': 'Already in favorites', 'replaced': False}
            
            # Get user's plan limits
            limits = self._get_user_limits(user_id)
            max_favs = limits['max_favorites']
            
            # Count current favorites
            cursor.execute('''
            SELECT COUNT(*) FROM user_favorites WHERE user_id = ?
            ''', (user_id,))
            count = cursor.fetchone()[0]
            
            replaced_model = None
            if count >= max_favs:
                # Remove oldest favorite
                cursor.execute('''
                SELECT model_path FROM user_favorites 
                WHERE user_id = ? 
                ORDER BY added_at ASC 
                LIMIT 1
                ''', (user_id,))
                replaced_model = cursor.fetchone()[0]
                
                cursor.execute('''
                DELETE FROM user_favorites 
                WHERE user_id = ? AND model_path = ?
                ''', (user_id, replaced_model))
            
            # Add new favorite
            cursor.execute('''
            INSERT INTO user_favorites (user_id, model_path, added_at)
            VALUES (?, ?, ?)
            ''', (user_id, model_path, datetime.now().isoformat()))
            
            # Mark as favorited and saved in generated_models
            cursor.execute('''
            UPDATE generated_models
            SET is_favorited = 1, is_saved = 1
            WHERE model_path = ?
            ''', (model_path,))
            
            conn.commit()
            
            # Log favorite action
            if self.activity_logger:
                self.activity_logger.log_event(
                    int(user_id),
                    ActivityLogger.EVENT_MODEL_FAVORITED,
                    {'model_path': model_path, 'permanent': True}
                )
            
            result = {
                'success': True,
                'message': 'Added to favorites',
                'replaced': replaced_model is not None
            }
            if replaced_model:
                result['replaced_model'] = replaced_model
            
            return result
            
        except Exception as e:
            conn.rollback()
            return {'success': False, 'message': str(e)}
        finally:
            conn.close()
    
    def remove_favorite(self, user_id: str, model_path: str) -> Dict:
        """Remove model from favorites and restart deletion timer."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            DELETE FROM user_favorites 
            WHERE user_id = ? AND model_path = ?
            ''', (user_id, model_path))
            
            if cursor.rowcount == 0:
                return {'success': False, 'message': 'Not in favorites'}
            
            # Restart timer by updating generated_at timestamp
            cursor.execute('''
            UPDATE generated_models
            SET generated_at = ?
            WHERE model_path = ?
            ''', (datetime.now().isoformat(), model_path))
            
            conn.commit()
            return {'success': True, 'message': 'Removed from favorites (timer restarted)'}
            
        except Exception as e:
            conn.rollback()
            return {'success': False, 'message': str(e)}
        finally:
            conn.close()
    
    def get_favorites(self, user_id: str) -> List[Dict]:
        """Get all favorites for user, ordered by newest first."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT f.model_path, f.added_at, g.file_size
        FROM user_favorites f
        LEFT JOIN generated_models g ON f.model_path = g.model_path
        WHERE f.user_id = ?
        ORDER BY f.added_at DESC
        ''', (user_id,))
        
        favorites = [
            {
                'model_path': row[0], 
                'added_at': row[1],
                'file_size': row[2],
                'exists': os.path.exists(row[0])
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return favorites
    
    def get_recent_models(self, user_id: str, limit: int = 20) -> List[Dict]:
        """Get recent models for user with favorite status and time remaining."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT g.model_path, g.generated_at, g.file_size,
               CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_favorited
        FROM generated_models g
        LEFT JOIN user_favorites f ON g.model_path = f.model_path AND f.user_id = ?
        WHERE g.user_id = ?
        ORDER BY g.generated_at DESC
        LIMIT ?
        ''', (user_id, user_id, limit))
        
        # Get user's plan limits for deletion hours
        limits = self._get_user_limits(user_id)
        cleanup_delta = timedelta(hours=limits['deletion_hours'])
        
        now = datetime.now()
        
        models = []
        for row in cursor.fetchall():
            model_path, generated_at, file_size, is_favorited = row
            is_favorited = bool(is_favorited)
            
            # Calculate time remaining
            time_remaining_hours = None
            time_remaining_display = "∞"  # Unlimited symbol for favorites
            
            if not is_favorited:
                generated_dt = datetime.fromisoformat(generated_at)
                deletion_time = generated_dt + cleanup_delta
                time_remaining = deletion_time - now
                
                if time_remaining.total_seconds() > 0:
                    time_remaining_hours = time_remaining.total_seconds() / 3600
                    
                    # Format display
                    if time_remaining_hours >= 24:
                        days = int(time_remaining_hours / 24)
                        time_remaining_display = f"{days}d"
                    elif time_remaining_hours >= 1:
                        hours = int(time_remaining_hours)
                        time_remaining_display = f"{hours}h"
                    else:
                        minutes = int(time_remaining_hours * 60)
                        time_remaining_display = f"{minutes}m"
                else:
                    time_remaining_display = "Expired"
            
            models.append({
                'model_path': model_path,
                'generated_at': generated_at,
                'file_size': file_size,
                'is_favorited': is_favorited,
                'exists': os.path.exists(model_path),
                'time_remaining_hours': time_remaining_hours,
                'time_remaining_display': time_remaining_display
            })
        
        conn.close()
        return models
    
    def is_favorited(self, user_id: str, model_path: str) -> bool:
        """Check if model is in user's favorites."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 1 FROM user_favorites 
        WHERE user_id = ? AND model_path = ?
        ''', (user_id, model_path))
        
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def get_favorites_count(self, user_id: str) -> int:
        """Get count of favorites for user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT COUNT(*) FROM user_favorites WHERE user_id = ?
        ''', (user_id,))
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_user_storage_stats(self, user_id: str) -> Dict:
        """Get storage statistics for user (data leak prevention monitoring)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total models
        cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM generated_models WHERE user_id = ?
        ''', (user_id,))
        total_count, total_size = cursor.fetchone()
        
        # Favorited models
        cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(g.file_size), 0)
        FROM user_favorites f
        JOIN generated_models g ON f.model_path = g.model_path
        WHERE f.user_id = ?
        ''', (user_id,))
        fav_count, fav_size = cursor.fetchone()
        
        # Old models eligible for cleanup
        cutoff_time = (datetime.now() - timedelta(hours=self.CLEANUP_HOURS)).isoformat()
        cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(g.file_size), 0)
        FROM generated_models g
        LEFT JOIN user_favorites f ON g.model_path = f.model_path
        WHERE g.user_id = ? AND g.generated_at < ? AND f.id IS NULL
        ''', (user_id, cutoff_time))
        old_count, old_size = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_models': total_count,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'favorited_count': fav_count,
            'favorited_size_mb': round(fav_size / (1024 * 1024), 2),
            'pending_cleanup_count': old_count,
            'pending_cleanup_mb': round(old_size / (1024 * 1024), 2),
            'cleanup_hours': self.CLEANUP_HOURS
        }
