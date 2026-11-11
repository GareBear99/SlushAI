"""User authentication, quota tracking, and badge management system."""
import sqlite3
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
from flask_login import UserMixin

try:
    import bcrypt
except ImportError:
    bcrypt = None

try:
    import jwt
except ImportError:
    jwt = None

try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
except ImportError:
    smtplib = None
    MIMEText = None
    MIMEMultipart = None


@dataclass
class User(UserMixin):
    user_id: int
    google_id: Optional[str]
    email: str
    name: str
    picture: str
    email_verified: bool = False

    def get_id(self):
        return str(self.user_id)


class UserManager:
    """Manages users, authentication, quotas, badges, and subscriptions."""
    
    # Badge levels based on lifetime model completions
    BADGE_LEVELS = {
        0: {"name": "Newcomer", "color": "#94a3b8", "min": 0, "max": 9},
        1: {"name": "Creator", "color": "#3b82f6", "min": 10, "max": 49},
        2: {"name": "Artist", "color": "#8b5cf6", "min": 50, "max": 199},
        3: {"name": "Master", "color": "#f59e0b", "min": 200, "max": 499},
        4: {"name": "Legend", "color": "#ef4444", "min": 500, "max": 999999},
        5: {"name": "Benefactor", "color": "#a855f7", "min": 0, "max": 999999}  # Mystery badge - unlocked by donating
    }
    
    # Subscription plans (USD pricing)
    SUBSCRIPTION_PLANS = {
        'free': {
            'name': 'Free Plan',
            'price_usd': 0.0,
            'billing_cycle': 'weekly',
            'models_per_week': 10,
            'max_favorites': 10,
            'max_saved_models': 32,
            'deletion_hours': 36,
            'features': ['10 models/week', 'Standard queue', 'Basic resolution', '10 favorites max', '32 total models', '36-hour deletion']
        },
        'standard_weekly': {
            'name': 'Standard Plan',
            'price_usd': 3.47,
            'billing_cycle': 'weekly',
            'models_per_week': 40,
            'max_favorites': 50,
            'max_saved_models': 150,
            'deletion_hours': 336,  # 14 days
            'features': ['40 models/week', 'Priority queue', 'Higher resolution', 'Email support', '50 favorites', '150 saved models', '14-day deletion']
        },
        'pro_weekly': {
            'name': 'Pro Plan',
            'price_usd': 7.89,
            'billing_cycle': 'weekly',
            'models_per_week': 120,
            'max_favorites': 150,
            'max_saved_models': 500,
            'deletion_hours': 720,  # 30 days
            'features': ['120 models/week', 'Highest priority', 'Max resolution', 'API access', 'Premium support', '150 favorites', '500 saved models', '30-day deletion']
        },
        'standard_yearly': {
            'name': 'Standard Plan (Yearly)',
            'price_usd': 3.47 * 52 * 0.4,  # 60% off
            'billing_cycle': 'yearly',
            'models_per_week': 40,
            'max_favorites': 50,
            'max_saved_models': 150,
            'deletion_hours': 336,  # 14 days
            'features': ['40 models/week', 'Priority queue', 'Higher resolution', 'Email support', '60% savings', '50 favorites', '150 saved models', '14-day deletion']
        },
        'pro_yearly': {
            'name': 'Pro Plan (Yearly)',
            'price_usd': 7.89 * 52 * 0.4,  # 60% off
            'billing_cycle': 'yearly',
            'models_per_week': 120,
            'max_favorites': 150,
            'max_saved_models': 500,
            'deletion_hours': 720,  # 30 days
            'features': ['120 models/week', 'Highest priority', 'Max resolution', 'API access', 'Premium support', '60% savings', '150 favorites', '500 saved models', '30-day deletion']
        },
        'founder': {
            'name': 'Founder',
            'price_usd': 0.0,
            'billing_cycle': 'lifetime',
            'models_per_week': 999999,  # Unlimited
            'max_favorites': 999999,  # Unlimited
            'max_saved_models': 999999,  # Unlimited
            'deletion_hours': 999999,  # Never delete
            'features': ['Unlimited everything', 'Platform founder', 'All permissions', 'System owner', 'Unlimited storage', 'Never deleted']
        },
        'moderator': {
            'name': 'Moderator',
            'price_usd': 0.0,
            'billing_cycle': 'permanent',
            'models_per_week': 999999,  # Unlimited
            'max_favorites': 1000,
            'max_saved_models': 5000,  # ~50GB at 10MB per model
            'deletion_hours': 999999,  # Never delete
            'features': ['Unlimited models', 'Moderation tools', 'User management', 'Content review', '1000 favorites', '5000 models (~50GB)', 'Never deleted']
        },
        'admin': {
            'name': 'Administrator',
            'price_usd': 0.0,
            'billing_cycle': 'permanent',
            'models_per_week': 999999,  # Unlimited
            'max_favorites': 1000,
            'max_saved_models': 5000,  # ~50GB at 10MB per model
            'deletion_hours': 999999,  # Never delete
            'features': ['Unlimited models', 'Full admin access', 'System management', 'All permissions', '1000 favorites', '5000 models (~50GB)', 'Never deleted']
        },
        'refill': {
            'name': 'Quick Refill',
            'price_usd': 1.0,
            'billing_cycle': 'one-time',
            'models_added': 10,
            'features': ['+10 models instantly', 'No subscription', 'Max 10 refills/week']
        }
    }
    
    FREE_WEEKLY_QUOTA = 10  # Free models per week
    
    # User capacity limits (1000GB infrastructure)
    MAX_FREE_USERS = 200
    MAX_STANDARD_USERS = 50
    MAX_PRO_USERS = 20
    MAX_MODERATORS = 5
    MAX_ADMINS = 3
    
    # Badge rewards (granted once per badge level)
    BADGE_REWARDS = {
        1: {'type': 'quota_reset', 'value': 'reset', 'message': 'Weekly quota reset as reward!'},
        2: {'type': 'quota_reset', 'value': 'reset', 'message': 'Weekly quota reset as reward!'},
        3: {'type': 'quota_reset', 'value': 'reset', 'message': 'Weekly quota reset as reward!'},
        4: {'type': 'quota_reset', 'value': 'reset', 'message': 'Weekly quota reset as reward!'}
    }
    
    # Badge display names and colors (for convenience)
    BADGE_NAMES = ["Newcomer", "Creator", "Artist", "Master", "Legend", "Benefactor"]
    BADGE_COLORS = ["#94a3b8", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444", "#a855f7"]
    
    def __init__(self, db_path: str, jwt_secret: str = None, email_manager=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Use provided secret or generate one (should be set from env var in production)
        self.jwt_secret = jwt_secret or secrets.token_hex(32)
        
        # Email configuration from environment variables
        import os
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.smtp_from_email = os.getenv('SMTP_FROM_EMAIL', self.smtp_user)
        self.smtp_from_name = os.getenv('SMTP_FROM_NAME', 'SlushAI 3D Modeller')
        
        # Email manager for logging (optional)
        self.email_manager = email_manager
        
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                username TEXT UNIQUE,
                avatar_url TEXT,
                email_verified BOOLEAN DEFAULT 0,
                verification_token TEXT,
                verification_token_expires TIMESTAMP,
                newsletter_subscribed BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subscription_tier TEXT DEFAULT 'free',
                badge_level INTEGER DEFAULT 0,
                lifetime_completions INTEGER DEFAULT 0
            )
        ''')
        
        # Migrate existing table if needed (add new columns)
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'password_hash' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN password_hash TEXT')
        if 'email_verified' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0')
        if 'verification_token' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN verification_token TEXT')
        if 'verification_token_expires' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN verification_token_expires TIMESTAMP')
        if 'newsletter_subscribed' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN newsletter_subscribed BOOLEAN DEFAULT 1')
        if 'last_code_sent_at' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN last_code_sent_at TIMESTAMP')
        if 'signup_ip' not in columns:
            # Used by create_email_user for the 3-accounts-per-IP signup cap;
            # previously only added ad hoc by the signup route.
            cursor.execute('ALTER TABLE users ADD COLUMN signup_ip TEXT')
        if 'benefactor_badge_expires' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN benefactor_badge_expires TIMESTAMP')
        if 'benefactor_last_renewal' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN benefactor_last_renewal TIMESTAMP')
        if 'username' not in columns:
            # Add username column without UNIQUE (will be enforced via application logic)
            cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
            # Auto-generate usernames for existing users
            cursor.execute('SELECT id, email, subscription_tier FROM users WHERE username IS NULL')
            existing_users = cursor.fetchall()
            for user_id, email, tier in existing_users:
                # Set founder account username
                if email == 'gdoman99@gmail.com':
                    base_username = 'garebearproductionz'
                else:
                    # Generate from email
                    base_username = email.split('@')[0].replace('.', '').replace('-', '').replace('+', '')[:15]
                
                # Ensure uniqueness
                username = base_username.lower()
                counter = 1
                while True:
                    cursor.execute('SELECT id FROM users WHERE LOWER(username) = ?', (username,))
                    if not cursor.fetchone():
                        break
                    username = f"{base_username}{counter}".lower()
                    counter += 1
                
                cursor.execute('UPDATE users SET username = ? WHERE id = ?', (username, user_id))
            
            # Create index for uniqueness constraint (application-level enforcement)
            try:
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_username_unique ON users(username)')
            except:
                pass  # Index might already exist
        
        # Usage tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                week_number INTEGER,
                year INTEGER,
                counted_towards_quota BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Weekly quotas table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weekly_quotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                week_number INTEGER NOT NULL,
                year INTEGER NOT NULL,
                models_used INTEGER DEFAULT 0,
                textures_used INTEGER DEFAULT 0,
                quota_limit INTEGER DEFAULT 10,
                UNIQUE(user_id, week_number, year),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Screenshot gallery table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_gallery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Badge rewards table (one-time rewards per badge)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS badge_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_level INTEGER NOT NULL,
                badge_name TEXT NOT NULL,
                reward_type TEXT NOT NULL,
                reward_value TEXT,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_level),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_type TEXT NOT NULL,
                billing_cycle TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                currency TEXT NOT NULL,
                amount_local REAL NOT NULL,
                stripe_subscription_id TEXT,
                status TEXT DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Stripe webhook events (idempotency: each event processed once).
        # Stripe redelivers events it thinks were not acknowledged; the
        # event ID is recorded after a successful dispatch so a redelivery
        # is skipped instead of double-applying a tier change or refill.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stripe_webhook_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Rate limiting table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier TEXT NOT NULL,
                identifier_type TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_count INTEGER DEFAULT 0,
                window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(identifier, identifier_type, endpoint)
            )
        ''')
        
        # Refills table (for $1 quick refills)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS refills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_usd REAL NOT NULL,
                models_added INTEGER NOT NULL,
                week_number INTEGER NOT NULL,
                year INTEGER NOT NULL,
                stripe_payment_id TEXT,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # PIN attempt tracking (for privileged accounts)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pin_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                ip_address TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Add PIN ban tracking column to users if not exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'pin_ban_until' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN pin_ban_until TIMESTAMP')
        
        # Add password reset token columns if not exists
        if 'reset_token' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN reset_token TEXT')
        if 'reset_token_expires' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP')
        if 'last_reset_request_at' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN last_reset_request_at TIMESTAMP')
        
        # Add referral code column if not exists (without UNIQUE for ALTER TABLE)
        if 'referral_code' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN referral_code TEXT')
        if 'referred_by_user_id' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN referred_by_user_id INTEGER')
        
        
        if 'has_donated' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN has_donated BOOLEAN DEFAULT 0')
        if 'benefactor_badge_unlocked' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN benefactor_badge_unlocked BOOLEAN DEFAULT 0')
        
        # Donations table (tracks all donations)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_usd REAL NOT NULL,
                payment_method TEXT NOT NULL,
                stripe_payment_id TEXT,
                crypto_tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Referrals table (tracks referred users)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_user_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL,
                referral_code TEXT NOT NULL,
                referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(referrer_user_id) REFERENCES users(id),
                FOREIGN KEY(referred_user_id) REFERENCES users(id)
            )
        ''')
        
        # Referral earnings table (tracks weekly $1 payouts)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                week_number INTEGER NOT NULL,
                year INTEGER NOT NULL,
                paying_referrals_count INTEGER NOT NULL,
                earnings_usd REAL NOT NULL,
                paid BOOLEAN DEFAULT 0,
                paid_at TIMESTAMP,
                UNIQUE(user_id, week_number, year),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_or_create_user(self, google_id: str, email: str, name: str = None, 
                          avatar_url: str = None) -> Dict:
        """Get existing user or create new one from Google OAuth data."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Dict-like access by column name
        cursor = conn.cursor()
        
        # Try to get existing user
        cursor.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
        row = cursor.fetchone()
        
        if row:
            # Update last login and info
            cursor.execute('''
                UPDATE users 
                SET last_login = CURRENT_TIMESTAMP, name = ?, avatar_url = ?
                WHERE google_id = ?
            ''', (name, avatar_url, google_id))
            conn.commit()
            
            # Fetch updated user
            cursor.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
            row = cursor.fetchone()
        else:
            # Create new user - generate username from email
            base_username = email.split('@')[0].replace('.', '').replace('-', '').replace('+', '')[:15].lower()
            username = base_username
            counter = 1
            # Ensure username uniqueness
            while True:
                cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,))
                if not cursor.fetchone():
                    break
                username = f"{base_username}{counter}"
                counter += 1
            
            cursor.execute('''
                INSERT INTO users (google_id, email, name, username, avatar_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (google_id, email, name, username, avatar_url))
            conn.commit()
            
            cursor.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
            row = cursor.fetchone()
        
        conn.close()
        
        # Map by column name, never by position (see _canonical_user_dict).
        return self._canonical_user_dict(dict(row))
    
    @staticmethod
    def _canonical_user_dict(row: Dict) -> Dict:
        """Return one canonical user dict.

        The users table uses DB column names (id, avatar_url,
        lifetime_completions); the rest of the code uses the API names
        (user_id, picture, total_models_generated). Provide both, so every
        consumer sees the keys it expects. Built from column names, never
        by positional row indexes — the username column shifted every
        position after it once already, which silently corrupted
        get_user_by_google_id / get_user_by_email.
        """
        d = dict(row)
        d['user_id'] = d.get('id')
        d['picture'] = d.get('avatar_url', '')
        d['total_models_generated'] = d.get('lifetime_completions', 0)
        return d

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Use Row factory for dict-like access
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Convert Row to dict with all columns, plus canonical API keys
        return self._canonical_user_dict(dict(row))
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username (case-insensitive)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._canonical_user_dict(dict(row))
    
    def validate_username(self, username: str) -> Tuple[bool, str]:
        """Validate username format and availability.
        
        Returns:
            (is_valid, error_message)
        """
        # Check length
        if len(username) < 3 or len(username) > 20:
            return False, "Username must be 3-20 characters"
        
        # Check format (alphanumeric + underscore, starts with letter)
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            return False, "Username must start with letter and contain only letters, numbers, and underscores"
        
        # Check reserved names
        reserved = ['admin', 'moderator', 'founder', 'root', 'system', 'api', 'support', 'slush', 'slushai']
        if username.lower() in reserved:
            return False, "Username is reserved"
        
        # Check if username already exists (case-insensitive)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,))
        exists = cursor.fetchone() is not None
        conn.close()
        
        if exists:
            return False, "Username already taken"
        
        return True, ""
    
    def get_user_storage_limits(self, user_id: int) -> Dict:
        """Get user's storage limits based on subscription tier.
        
        Returns:
            Dict with max_favorites, max_saved_models, deletion_hours
        """
        user = self.get_user_by_id(user_id)
        if not user:
            # Default to free plan limits
            return {
                'max_favorites': 10,
                'max_saved_models': 32,
                'deletion_hours': 36
            }
        
        tier = user['subscription_tier']
        
        # Map tier to plan key
        if tier in ['standard_weekly', 'standard_yearly']:
            plan_key = 'standard_weekly'
        elif tier in ['pro_weekly', 'pro_yearly']:
            plan_key = 'pro_weekly'
        else:
            plan_key = 'free'
        
        plan = self.SUBSCRIPTION_PLANS.get(plan_key, self.SUBSCRIPTION_PLANS['free'])
        
        return {
            'max_favorites': plan.get('max_favorites', 10),
            'max_saved_models': plan.get('max_saved_models', 32),
            'deletion_hours': plan.get('deletion_hours', 36)
        }
    
    def get_user_counts_by_tier(self) -> Dict:
        """Get current count of users per subscription tier.
        
        Returns:
            Dict with free_count, standard_count, pro_count, total_count
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count founder (should always be 1 - gdoman99@gmail.com)
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_tier = 'founder' OR email = 'gdoman99@gmail.com'")
        founder_count = cursor.fetchone()[0]
        
        # Count free users
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_tier = 'free'")
        free_count = cursor.fetchone()[0]
        
        # Count standard users (both weekly and yearly)
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE subscription_tier IN ('standard_weekly', 'standard_yearly')"
        )
        standard_count = cursor.fetchone()[0]
        
        # Count pro users (both weekly and yearly)
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE subscription_tier IN ('pro_weekly', 'pro_yearly')"
        )
        pro_count = cursor.fetchone()[0]
        
        # Count moderators
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_tier = 'moderator'")
        moderator_count = cursor.fetchone()[0]
        
        # Count admins
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_tier = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'founder_count': founder_count,
            'founder_email': 'gdoman99@gmail.com',
            'free_count': free_count,
            'free_max': self.MAX_FREE_USERS,
            'free_available': max(0, self.MAX_FREE_USERS - free_count),
            'standard_count': standard_count,
            'standard_max': self.MAX_STANDARD_USERS,
            'standard_available': max(0, self.MAX_STANDARD_USERS - standard_count),
            'pro_count': pro_count,
            'pro_max': self.MAX_PRO_USERS,
            'pro_available': max(0, self.MAX_PRO_USERS - pro_count),
            'moderator_count': moderator_count,
            'moderator_max': self.MAX_MODERATORS,
            'moderator_available': max(0, self.MAX_MODERATORS - moderator_count),
            'admin_count': admin_count,
            'admin_max': self.MAX_ADMINS,
            'admin_available': max(0, self.MAX_ADMINS - admin_count),
            'total_count': total_count,
            'total_max': self.MAX_FREE_USERS + self.MAX_STANDARD_USERS + self.MAX_PRO_USERS + self.MAX_MODERATORS + self.MAX_ADMINS
        }
    
    def check_registration_capacity(self, tier: str = 'free') -> Tuple[bool, str]:
        """Check if new user registration is allowed for specified tier.
        
        Args:
            tier: 'free', 'standard', or 'pro'
        
        Returns:
            (can_register, message) tuple
        """
        counts = self.get_user_counts_by_tier()
        
        if tier == 'free':
            if counts['free_count'] >= self.MAX_FREE_USERS:
                return False, f"Free tier at capacity ({counts['free_count']}/{self.MAX_FREE_USERS} users). Upgrade to Standard ($3.47/week) or Pro ($7.89/week) to join!"
            return True, f"Free tier available ({counts['free_count']}/{self.MAX_FREE_USERS} users)"
        
        elif tier in ['standard', 'standard_weekly', 'standard_yearly']:
            if counts['standard_count'] >= self.MAX_STANDARD_USERS:
                return False, f"Standard tier at capacity ({counts['standard_count']}/{self.MAX_STANDARD_USERS} users). Upgrade to Pro ($7.89/week) to join!"
            return True, f"Standard tier available ({counts['standard_count']}/{self.MAX_STANDARD_USERS} users)"
        
        elif tier in ['pro', 'pro_weekly', 'pro_yearly']:
            if counts['pro_count'] >= self.MAX_PRO_USERS:
                return False, f"Pro tier at capacity ({counts['pro_count']}/{self.MAX_PRO_USERS} users). Please check back later as we expand capacity."
            return True, f"Pro tier available ({counts['pro_count']}/{self.MAX_PRO_USERS} users)"
        
        return False, "Invalid tier specified"
    
    def check_quota(self, user_id: int) -> Tuple[bool, Dict]:
        """Check if user has quota remaining this week."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False, {'error': 'User not found'}
        
        # Determine quota limit based on tier
        tier = user['subscription_tier']
        if tier == 'standard_weekly' or tier == 'standard_yearly':
            tier_quota = 40
        elif tier == 'pro_weekly' or tier == 'pro_yearly':
            tier_quota = 120
        else:  # free
            tier_quota = self.FREE_WEEKLY_QUOTA
        
        # Get current week
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year
        
        # Get or create weekly quota
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO weekly_quotas (user_id, week_number, year, quota_limit)
            VALUES (?, ?, ?, ?)
        ''', (user_id, week_number, year, tier_quota))
        
        cursor.execute('''
            SELECT models_used, quota_limit FROM weekly_quotas
            WHERE user_id = ? AND week_number = ? AND year = ?
        ''', (user_id, week_number, year))
        
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        
        if not row:
            # Keys match what viewer.html reads (used_this_week/weekly_limit);
            # 'used'/'limit' kept as aliases for older callers.
            return True, {'used': 0, 'used_this_week': 0, 'limit': self.FREE_WEEKLY_QUOTA, 'weekly_limit': self.FREE_WEEKLY_QUOTA, 'remaining': self.FREE_WEEKLY_QUOTA}
        
        models_used, quota_limit = row
        remaining = quota_limit - models_used
        
        if models_used >= quota_limit:
            return False, {
                'used': models_used,
                'used_this_week': models_used,
                'limit': quota_limit,
                'weekly_limit': quota_limit,
                'remaining': 0,
                'message': f'Weekly quota exceeded ({models_used}/{quota_limit} used)'
            }
        
        return True, {
            'used': models_used,
            'used_this_week': models_used,
            'limit': quota_limit,
            'weekly_limit': quota_limit,
            'remaining': remaining
        }
    
    def log_task_start(self, user_id: int, task_id: str, task_type: str):
        """Log when a task starts (doesn't count towards quota yet)."""
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO usage_log (user_id, task_id, task_type, status, week_number, year)
            VALUES (?, ?, ?, 'started', ?, ?)
        ''', (user_id, task_id, task_type, week_number, year))
        
        conn.commit()
        conn.close()
    
    def log_task_complete(self, user_id: int, task_id: str, status: str):
        """Log task completion and update quota ONLY if successful."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update usage log
        cursor.execute('''
            UPDATE usage_log 
            SET status = ?, completed_at = CURRENT_TIMESTAMP,
                counted_towards_quota = ?
            WHERE user_id = ? AND task_id = ?
        ''', (status, 1 if status == 'completed' else 0, user_id, task_id))
        
        # Only count completed tasks towards quota
        if status == 'completed':
            # Get task type
            cursor.execute('''
                SELECT task_type, week_number, year FROM usage_log
                WHERE user_id = ? AND task_id = ?
            ''', (user_id, task_id))
            row = cursor.fetchone()
            
            if row:
                task_type, week_number, year = row
                
                # Increment weekly quota
                if task_type == 'model':
                    cursor.execute('''
                        UPDATE weekly_quotas
                        SET models_used = models_used + 1
                        WHERE user_id = ? AND week_number = ? AND year = ?
                    ''', (user_id, week_number, year))
                elif task_type == 'texture':
                    cursor.execute('''
                        UPDATE weekly_quotas
                        SET textures_used = textures_used + 1
                        WHERE user_id = ? AND week_number = ? AND year = ?
                    ''', (user_id, week_number, year))
                
                # Increment lifetime completions
                cursor.execute('''
                    UPDATE users
                    SET lifetime_completions = lifetime_completions + 1
                    WHERE id = ?
                ''', (user_id,))
                
                # Update badge level
                self._update_badge_level(cursor, user_id)
        
        conn.commit()
        conn.close()
    
    def _update_badge_level(self, cursor, user_id: int):
        """Update user's badge level based on lifetime completions and grant rewards."""
        # Get current badge level
        cursor.execute('SELECT badge_level, lifetime_completions FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return
        
        old_level, completions = row
        
        # Determine new badge level
        new_level = 0
        for level, info in self.BADGE_LEVELS.items():
            if info['min'] <= completions <= info['max']:
                new_level = level
                break
        
        # Check if badge level increased
        if new_level > old_level:
            cursor.execute('UPDATE users SET badge_level = ? WHERE id = ?', (new_level, user_id))
            
            # Grant badge reward if available and not already claimed
            if new_level in self.BADGE_REWARDS:
                # Check if reward already claimed
                cursor.execute('''
                    SELECT id FROM badge_rewards
                    WHERE user_id = ? AND badge_level = ?
                ''', (user_id, new_level))
                
                if not cursor.fetchone():
                    # Grant reward
                    reward = self.BADGE_REWARDS[new_level]
                    badge_name = self.BADGE_LEVELS[new_level]['name']
                    
                    # Record reward
                    cursor.execute('''
                        INSERT INTO badge_rewards (user_id, badge_level, badge_name, reward_type, reward_value)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, new_level, badge_name, reward['type'], reward['value']))
                    
                    # Apply reward (quota reset)
                    if reward['type'] == 'quota_reset':
                        self._reset_weekly_quota(cursor, user_id)
                    
                    print(f"🎉 User {user_id} reached {badge_name} level! {reward['message']}")
        elif new_level != old_level:
            # Just update level without reward
            cursor.execute('UPDATE users SET badge_level = ? WHERE id = ?', (new_level, user_id))
    
    def get_badge_info(self, user_id: int) -> Dict:
        """Get badge information for user."""
        user = self.get_user_by_id(user_id)
        if not user:
            return {}
        
        level = user['badge_level']
        completions = user['lifetime_completions']
        badge_info = self.BADGE_LEVELS[level]
        
        # Calculate progress to next level
        if level < max(self.BADGE_LEVELS.keys()):
            next_level_info = self.BADGE_LEVELS[level + 1]
            progress_percent = (completions - badge_info['min']) / (next_level_info['min'] - badge_info['min']) * 100
            progress_percent = min(100, max(0, progress_percent))
        else:
            progress_percent = 100  # Max level
            next_level_info = None
        
        return {
            'level': level,
            'name': badge_info['name'],
            'color': badge_info['color'],
            'completions': completions,
            'progress_percent': progress_percent,
            'next_level': next_level_info['name'] if next_level_info else 'Max Level'
        }
    
    def save_screenshot(self, user_id: int, filename: str, file_path: str):
        """Save screenshot to user's gallery."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO user_gallery (user_id, filename, file_path)
            VALUES (?, ?, ?)
        ''', (user_id, filename, file_path))
        
        conn.commit()
        conn.close()
    
    def get_user_gallery(self, user_id: int, limit: int = 50) -> list:
        """Get user's screenshot gallery."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT filename, file_path, created_at
            FROM user_gallery
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {'filename': row[0], 'file_path': row[1], 'created_at': row[2]}
            for row in rows
        ]

    # --------------------- Utility Methods ---------------------
    def _reset_weekly_quota(self, cursor, user_id: int):
        """Reset the current week's quota for a user."""
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year
        cursor.execute('''
            UPDATE weekly_quotas
            SET models_used = 0, textures_used = 0
            WHERE user_id = ? AND week_number = ? AND year = ?
        ''', (user_id, week_number, year))

    def get_pricing(self):
        """Return subscription plans with formatted prices."""
        def format_plan(key, plan):
            return {
                'key': key,
                'name': plan['name'],
                'price_usd': round(plan['price_usd'], 2),
                'billing_cycle': plan['billing_cycle'],
                'features': plan['features'],
                'models_per_week': plan.get('models_per_week'),
                'models_added': plan.get('models_added')
            }
        return [format_plan(k, v) for k, v in self.SUBSCRIPTION_PLANS.items()]
    
    def purchase_refill(self, user_id: int, stripe_payment_id: str = None) -> Tuple[bool, str]:
        """Purchase a $1 refill (adds 10 models to current week quota)."""
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check refill limit (max 10 per week)
        cursor.execute('''
            SELECT COUNT(*) FROM refills
            WHERE user_id = ? AND week_number = ? AND year = ?
        ''', (user_id, week_number, year))
        
        refill_count = cursor.fetchone()[0]
        
        if refill_count >= 10:
            conn.close()
            return False, 'Maximum 10 refills per week reached'
        
        # Record refill purchase
        cursor.execute('''
            INSERT INTO refills (user_id, amount_usd, models_added, week_number, year, stripe_payment_id)
            VALUES (?, 1.0, 10, ?, ?, ?)
        ''', (user_id, week_number, year, stripe_payment_id))
        
        # Add 10 models to quota limit (not resetting usage, just increasing limit)
        cursor.execute('''
            UPDATE weekly_quotas
            SET quota_limit = quota_limit + 10
            WHERE user_id = ? AND week_number = ? AND year = ?
        ''', (user_id, week_number, year))
        
        # If no quota record exists, create one
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO weekly_quotas (user_id, week_number, year, quota_limit)
                VALUES (?, ?, ?, ?)
            ''', (user_id, week_number, year, self.FREE_WEEKLY_QUOTA + 10))
        
        conn.commit()
        conn.close()
        
        return True, f'Successfully added 10 models! ({10 - refill_count - 1} refills remaining this week)'
    
    def update_subscription(self, user_id: int, tier: str, yearly: bool = False,
                            stripe_subscription_id: str = None) -> Tuple[bool, str]:
        """Set a user's subscription tier (Stripe webhook / crypto verify).

        The crypto payment verify route already calls this exact 3-arg
        signature (viewer/app.py) — it did not exist before, so a completed
        crypto payment would raise AttributeError (500). This implements
        it, which fixes that path too.

        tier: 'free' | 'standard' | 'pro'. yearly: billing cycle.
        Sets users.subscription_tier to 'free', '<tier>_weekly' or
        '<tier>_yearly', records the subscription in the subscriptions
        table (price + cycle from SUBSCRIPTION_PLANS), and raises the
        current week's quota limit to the new tier's limit when the new
        limit is higher — an upgrade applies immediately, not next week.
        A downgrade to free cancels the active subscription record but
        does not lower the current week's limit.
        Returns (True, message) or (False, reason).
        """
        tier = (tier or '').lower()
        if tier not in ('free', 'standard', 'pro'):
            return False, f'Invalid tier: {tier!r}'
        tier_value = 'free' if tier == 'free' else f"{tier}_{'yearly' if yearly else 'weekly'}"
        plan = self.SUBSCRIPTION_PLANS.get(tier_value, {})
        amount_usd = round(plan.get('price_usd', 0.0), 2)
        billing_cycle = plan.get('billing_cycle', 'weekly')

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE users SET subscription_tier = ? WHERE id = ?',
                (tier_value, user_id))
            if cursor.rowcount == 0:
                return False, 'User not found'

            if tier == 'free':
                cursor.execute(
                    """UPDATE subscriptions
                       SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
                       WHERE user_id = ? AND status = 'active'""",
                    (user_id,))
            else:
                cursor.execute(
                    "SELECT id FROM subscriptions WHERE user_id = ? AND status = 'active'",
                    (user_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """UPDATE subscriptions
                           SET plan_type = ?, billing_cycle = ?, amount_usd = ?,
                               currency = 'USD', amount_local = ?,
                               stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                               status = 'active', cancelled_at = NULL
                           WHERE id = ?""",
                        (tier, billing_cycle, amount_usd, amount_usd,
                         stripe_subscription_id, row[0]))
                else:
                    cursor.execute(
                        """INSERT INTO subscriptions
                           (user_id, plan_type, billing_cycle, amount_usd, currency,
                            amount_local, stripe_subscription_id, status)
                           VALUES (?, ?, ?, ?, 'USD', ?, ?, 'active')""",
                        (user_id, tier, billing_cycle, amount_usd, amount_usd,
                         stripe_subscription_id))

                # Raise the current week's quota limit to the new tier's
                # limit when higher (an upgrade applies immediately).
                new_limit = plan.get('models_per_week') or self.FREE_WEEKLY_QUOTA
                now = datetime.now()
                week_number = now.isocalendar()[1]
                year = now.year
                cursor.execute(
                    """UPDATE weekly_quotas SET quota_limit = ?
                       WHERE user_id = ? AND week_number = ? AND year = ?
                       AND quota_limit < ?""",
                    (new_limit, user_id, week_number, year, new_limit))
            conn.commit()
            return True, f'Subscription updated to {tier_value}'
        except Exception as e:
            conn.rollback()
            return False, f'Failed to update subscription: {str(e)}'
        finally:
            conn.close()
    
    def record_stripe_event(self, event_id: str, event_type: str) -> bool:
        """Record a processed Stripe webhook event ID (idempotency).

        Returns True if the event is new, False if it was already seen.
        Stripe redelivers events it thinks were not acknowledged; a
        redelivery must never double-apply a tier change or a refill.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO stripe_webhook_events (event_id, event_type) VALUES (?, ?)',
                (event_id, event_type))
            conn.commit()
            return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def has_stripe_event(self, event_id: str) -> bool:
        """True if a Stripe webhook event ID was already processed."""
        if not event_id:
            return False
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT 1 FROM stripe_webhook_events WHERE event_id = ?',
                (event_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def has_stripe_refill(self, stripe_payment_id: str) -> bool:
        """True if a refill was already recorded for a Stripe payment.

        Guards the one-time refill against a duplicate webhook delivery
        (purchase_refill itself is not idempotent — it would +10 twice).
        """
        if not stripe_payment_id:
            return False
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT COUNT(*) FROM refills WHERE stripe_payment_id = ?',
                (stripe_payment_id,))
            return cursor.fetchone()[0] > 0
        finally:
            conn.close()
    
    def get_user_id_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Optional[int]:
        """User ID for a Stripe subscription ID (webhook fallback).

        Used for customer.subscription.* events whose metadata is missing
        (e.g. a subscription created directly in the Stripe Dashboard).
        """
        if not stripe_subscription_id:
            return None
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT user_id FROM subscriptions
                   WHERE stripe_subscription_id = ? ORDER BY id DESC LIMIT 1""",
                (stripe_subscription_id,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    
    def get_refill_count(self, user_id: int) -> Dict:
        """Get refill count for current week."""
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM refills
            WHERE user_id = ? AND week_number = ? AND year = ?
        ''', (user_id, week_number, year))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return {
            'used': count,
            'remaining': max(0, 10 - count),
            'max': 10
        }
    
    # --------------------- Email Authentication Methods ---------------------
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        if bcrypt is None:
            raise RuntimeError("bcrypt is required for email authentication. Install with: pip install bcrypt")
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        if bcrypt is None:
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    
    def _validate_email(self, email: str) -> Tuple[bool, str]:
        """Validate email format."""
        email = email.strip().lower()
        if not email or len(email) < 3:
            return False, "Email is too short"
        if len(email) > 254:
            return False, "Email is too long"
        # Simple regex for email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "Invalid email format"
        return True, ""
    
    def _validate_password(self, password: str) -> Tuple[bool, str]:
        """Validate password strength."""
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if len(password) > 128:
            return False, "Password is too long"
        if not re.search(r'[a-z]', password):
            return False, "Password must contain lowercase letters"
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain uppercase letters"
        if not re.search(r'[0-9]', password):
            return False, "Password must contain numbers"
        return True, ""
    
    def create_email_user(self, email: str, password: str, name: str, username: str, newsletter_subscribed: bool = True, signup_ip: str = None) -> Tuple[bool, str, Optional[int]]:
        """Create a new user with email/password authentication."""
        # Validate email
        email = email.strip().lower()
        valid_email, email_error = self._validate_email(email)
        if not valid_email:
            return False, email_error, None
        
        # Validate password
        valid_password, password_error = self._validate_password(password)
        if not valid_password:
            return False, password_error, None
        
        # Validate name
        name = name.strip()
        if not name or len(name) < 2:
            return False, "Name must be at least 2 characters", None
        if len(name) > 100:
            return False, "Name is too long", None
        
        # Validate username
        username = username.strip()
        valid_username, username_error = self.validate_username(username)
        if not valid_username:
            return False, username_error, None
        
        # Store username in lowercase for consistency
        username_lower = username.lower()
        
        # Hash password
        try:
            password_hash = self._hash_password(password)
        except RuntimeError as e:
            return False, str(e), None
        
        # Create user
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Use email-based google_id for email-only accounts
            google_id = f'email_{email}'
            
            cursor.execute('''
                INSERT INTO users (google_id, email, password_hash, name, username, email_verified, newsletter_subscribed, signup_ip)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            ''', (google_id, email, password_hash, name, username_lower, 1 if newsletter_subscribed else 0, signup_ip))
            
            user_id = cursor.lastrowid
            conn.commit()
            
            return True, "Account created successfully", user_id
            
        except sqlite3.IntegrityError as e:
            conn.close()
            error_msg = str(e).lower()
            if 'email' in error_msg:
                return False, "Email already registered", None
            elif 'username' in error_msg:
                return False, "Username already taken", None
            else:
                return False, "Account already exists", None
        except Exception as e:
            conn.close()
            return False, f"Database error: {str(e)}", None
        finally:
            if conn:
                conn.close()
    
    def verify_email_password(self, email_or_username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """Verify email/username and password credentials.
        
        Args:
            email_or_username: Can be either email address or username
            password: User's password
        
        Returns:
            (success, user_data) tuple
        """
        email_or_username = email_or_username.strip().lower()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Try to find user by email first
        cursor.execute('''
            SELECT id, password_hash, email_verified
            FROM users
            WHERE email = ? AND password_hash IS NOT NULL
        ''', (email_or_username,))
        
        row = cursor.fetchone()
        
        # If not found by email, try by username
        if not row:
            cursor.execute('''
                SELECT id, password_hash, email_verified
                FROM users
                WHERE LOWER(username) = ? AND password_hash IS NOT NULL
            ''', (email_or_username,))
            row = cursor.fetchone()
        
        conn.close()
        
        if not row:
            return False, None
        
        user_id, password_hash, email_verified = row
        
        # Verify password
        if not self._verify_password(password, password_hash):
            return False, None
        
        # Get full user data
        user_data = self.get_user_by_id(user_id)
        return True, user_data
    
    def generate_verification_code(self, user_id: int) -> Optional[str]:
        """Generate a 6-digit verification code that expires in 10 minutes.
        
        Returns:
            6-digit code string, or None if user not found
        """
        # Generate a 6-digit code with a CSPRNG (random.randint is predictable).
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        
        # Code expires in 10 minutes
        expires_at = datetime.now() + timedelta(minutes=10)
        
        # Store code in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
        if not cursor.fetchone():
            conn.close()
            return None
        
        cursor.execute('''
            UPDATE users
            SET verification_token = ?, verification_token_expires = ?
            WHERE id = ?
        ''', (code, expires_at.isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        return code
    
    def verify_email_code(self, user_id: int, code: str) -> Tuple[bool, str]:
        """Verify a 6-digit email verification code or PIN.
        
        Args:
            user_id: User ID
            code: 6-digit verification code or PIN
        
        Returns:
            (success, message) tuple
        """
        try:
            code = code.strip()
            
            # Validate code format
            if not code.isdigit() or len(code) != 6:
                return False, "Invalid code format"
            
            # Get user's verification code and expiry
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT verification_token, verification_token_expires, email_verified, subscription_tier
                FROM users
                WHERE id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return False, "User not found"
            
            stored_code, expires_at_str, already_verified, tier = row
            
            # For staff PINs (founder/admin/moderator), don't check already_verified
            # They use PINs for login security, not email verification
            is_staff = tier in ['founder', 'admin', 'moderator']
            
            if not stored_code:
                conn.close()
                return False, "No verification code found. Please request a new code."
            
            # Check if code expired
            if not expires_at_str:
                conn.close()
                return False, "Verification code expired. Please request a new code."
                
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return False, "Verification code expired. Please request a new code."
            
            # Verify code FIRST: an already-verified account must still present
            # the right code (previously any 6 digits returned success here).
            if stored_code != code:
                conn.close()
                return False, "Incorrect verification code"
            
            if already_verified and not is_staff:
                conn.close()
                return True, "Email already verified"
            
            # For staff, just clear the PIN without marking email as verified (already is)
            # For regular users, mark email as verified
            if is_staff:
                cursor.execute('''
                    UPDATE users
                    SET verification_token = NULL, verification_token_expires = NULL
                    WHERE id = ?
                ''', (user_id,))
            else:
                cursor.execute('''
                    UPDATE users
                    SET email_verified = 1, verification_token = NULL, verification_token_expires = NULL
                    WHERE id = ?
                ''', (user_id,))
            
            conn.commit()
            conn.close()
            
            if is_staff:
                return True, "PIN verified successfully"
            else:
                return True, "Email verified successfully"
            
        except Exception as e:
            return False, f"Verification error: {str(e)}"
    
    def send_verification_email(self, email: str, code: str) -> Tuple[bool, str]:
        """Send verification code email to user.
        
        Args:
            email: Recipient email address
            code: 6-digit verification code
        
        Returns:
            (success, message) tuple
        """
        if smtplib is None or MIMEText is None or MIMEMultipart is None:
            return False, "Email libraries not available"
        
        if not self.smtp_user or not self.smtp_password:
            return False, "SMTP credentials not configured"
        
        try:
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Verify your SlushAI account'
            msg['From'] = f"{self.smtp_from_name} <{self.smtp_from_email}>"
            msg['To'] = email
            
            # Plain text version
            text = f"""Welcome to SlushAI 3D Modeller!

Your verification code is: {code}

This code will expire in 10 minutes.

If you didn't create an account, you can safely ignore this email.

Best regards,
The SlushAI Team
"""
            
            # HTML version
            html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9fafb; padding: 40px 30px; }}
        .code-box {{ background: white; border: 2px solid #667eea; border-radius: 10px; padding: 30px; text-align: center; margin: 20px 0; }}
        .code {{ font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #667eea; font-family: monospace; }}
        .footer {{ background: #374151; color: #9ca3af; padding: 20px; text-align: center; font-size: 12px; border-radius: 0 0 10px 10px; }}
        .warning {{ color: #ef4444; font-size: 14px; margin-top: 15px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎨 Welcome to SlushAI!</h1>
            <p>Verify your email to start creating amazing 3D models</p>
        </div>
        <div class="content">
            <p>Hello!</p>
            <p>Thank you for signing up for SlushAI 3D Modeller. To complete your registration, please use the verification code below:</p>
            <div class="code-box">
                <div class="code">{code}</div>
                <p class="warning">⏱️ This code expires in 10 minutes</p>
            </div>
            <p>Enter this code on the verification page to activate your account and start creating 3D models from images.</p>
            <p>If you didn't create an account with SlushAI, you can safely ignore this email.</p>
        </div>
        <div class="footer">
            <p>&copy; 2024 SlushAI 3D Modeller. All rights reserved.</p>
            <p>Spatial Latent Understanding & Synthetic Hyper-Accuracy Intelligence</p>
        </div>
    </div>
</body>
</html>
"""
            
            # Attach both versions
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            # Log email if email_manager is available
            if self.email_manager:
                try:
                    self.email_manager.log_outbound_email(
                        recipient_email=email,
                        sender_email=self.smtp_from_email,
                        subject='Verify your SlushAI account',
                        body_text=text,
                        body_html=html,
                        email_type='verification'
                    )
                except Exception as log_error:
                    # Don't fail email send if logging fails
                    pass
            
            return True, "Verification email sent successfully"
            
        except Exception as e:
            return False, f"Failed to send email: {str(e)}"
    
    def resend_verification_code(self, user_id: int) -> Tuple[bool, str, Optional[str]]:
        """Resend verification code with 60-second throttling.
        
        Args:
            user_id: User ID
        
        Returns:
            (success, message, code) tuple. Code is None if throttled or failed.
        """
        try:
            # Get user info
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT email, email_verified, last_code_sent_at
                FROM users
                WHERE id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return False, "User not found", None
            
            email, already_verified, last_sent_str = row
            
            if already_verified:
                return False, "Email already verified", None
            
            # Check throttling (60 seconds)
            if last_sent_str:
                last_sent = datetime.fromisoformat(last_sent_str)
                time_since_last = (datetime.now() - last_sent).total_seconds()
                
                if time_since_last < 60:
                    wait_seconds = int(60 - time_since_last)
                    return False, f"Please wait {wait_seconds} seconds before requesting a new code", None
            
            # Generate new code
            code = self.generate_verification_code(user_id)
            if not code:
                return False, "Failed to generate verification code", None
            
            # Update last_code_sent_at
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET last_code_sent_at = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
            
            # Send email
            email_success, email_message = self.send_verification_email(email, code)
            
            if not email_success:
                return False, email_message, None
            
            return True, "Verification code sent successfully", code
            
        except Exception as e:
            return False, f"Error: {str(e)}", None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email address."""
        email = email.strip().lower()
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Dict-like access by column name
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Map by column name, never by position (see _canonical_user_dict).
        return self._canonical_user_dict(dict(row))
    
    def get_user_by_google_id(self, google_id: str) -> Optional[Dict]:
        """Get user by Google OAuth ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Dict-like access by column name
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Map by column name, never by position (see _canonical_user_dict).
        return self._canonical_user_dict(dict(row))
    
    def create_user(self, google_id: str, email: str, name: str, picture: str = '') -> int:
        """Create a new OAuth user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users (google_id, email, name, avatar_url, email_verified)
            VALUES (?, ?, ?, ?, 1)
        ''', (google_id, email, name, picture))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return user_id
    
    def update_user(self, user_id: int, updates: Dict) -> bool:
        """Update user information."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Build dynamic update query
        allowed_fields = ['name', 'email', 'avatar_url', 'picture']
        set_clauses = []
        values = []
        
        for field, value in updates.items():
            if field in allowed_fields:
                # Handle picture -> avatar_url mapping
                if field == 'picture':
                    field = 'avatar_url'
                set_clauses.append(f"{field} = ?")
                values.append(value)
        
        if not set_clauses:
            conn.close()
            return False
        
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?"
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        
        return True
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection (used internally)."""
        return sqlite3.connect(self.db_path)
    
    def check_pin_ban(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user is currently banned from PIN attempts.
        
        Args:
            user_id: User ID
        
        Returns:
            (is_banned, unban_time) tuple
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT pin_ban_until FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return False, None
        
        ban_until = datetime.fromisoformat(row[0])
        
        if datetime.now() < ban_until:
            return True, row[0]
        else:
            # Ban expired, clear it
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET pin_ban_until = NULL WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()
            return False, None
    
    def record_pin_attempt(self, user_id: int, success: bool, ip_address: str = None) -> Tuple[bool, Optional[str]]:
        """Record a PIN attempt and enforce 2-hour ban after 5 failures.
        
        Args:
            user_id: User ID
            success: Whether the PIN was correct
            ip_address: IP address of attempt
        
        Returns:
            (should_ban, ban_message) tuple. should_ban=True if user should be banned.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Record the attempt
        cursor.execute('''
            INSERT INTO pin_attempts (user_id, success, ip_address)
            VALUES (?, ?, ?)
        ''', (user_id, success, ip_address))
        
        if success:
            # Clear any existing ban on successful login
            cursor.execute('UPDATE users SET pin_ban_until = NULL WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()
            return False, None
        
        # Count failed attempts in last 10 minutes
        cursor.execute('''
            SELECT COUNT(*) FROM pin_attempts
            WHERE user_id = ?
              AND success = 0
              AND attempt_time >= datetime('now', '-10 minutes')
        ''', (user_id,))
        
        failed_count = cursor.fetchone()[0]
        
        if failed_count >= 5:
            # Ban for 2 hours
            ban_until = datetime.now() + timedelta(hours=2)
            cursor.execute('''
                UPDATE users SET pin_ban_until = ?
                WHERE id = ?
            ''', (ban_until.isoformat(), user_id))
            conn.commit()
            conn.close()
            
            return True, f"Too many failed attempts. Account temporarily locked until {ban_until.strftime('%I:%M %p')}"
        
        conn.commit()
        conn.close()
        
        attempts_left = 5 - failed_count
        return False, f"{attempts_left} attempt(s) remaining before 2-hour lockout"
    
    def get_pin_attempt_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get PIN attempt history for a user.
        
        Args:
            user_id: User ID
            limit: Max number of attempts to return
        
        Returns:
            List of attempt dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM pin_attempts
            WHERE user_id = ?
            ORDER BY attempt_time DESC
            LIMIT ?
        ''', (user_id, limit))
        
        rows = cursor.fetchall()
        attempts = [dict(row) for row in rows]
        
        conn.close()
        return attempts
    
    def generate_password_reset_token(self, email: str) -> Tuple[bool, str, Optional[str]]:
        """Generate password reset token and send email.
        
        Args:
            email: User's email address
        
        Returns:
            (success, message, token) tuple. Token is None if failed or throttled.
        """
        try:
            email = email.strip().lower()
            
            # Get user
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, last_reset_request_at
                FROM users
                WHERE email = ?
            ''', (email,))
            
            row = cursor.fetchone()
            
            if not row:
                # Don't reveal if email exists or not
                conn.close()
                return True, "If that email exists, we've sent a password reset link", None
            
            user_id, name, last_reset_str = row
            
            # Check throttling (60 seconds between requests)
            if last_reset_str:
                last_reset = datetime.fromisoformat(last_reset_str)
                time_since_last = (datetime.now() - last_reset).total_seconds()
                
                if time_since_last < 60:
                    wait_seconds = int(60 - time_since_last)
                    conn.close()
                    return False, f"Please wait {wait_seconds} seconds before requesting another reset", None
            
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=1)  # 1 hour expiry
            
            # Store token
            cursor.execute('''
                UPDATE users
                SET reset_token = ?,
                    reset_token_expires = ?,
                    last_reset_request_at = ?
                WHERE id = ?
            ''', (token, expires_at.isoformat(), datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
            return True, "Password reset email sent", token
            
        except Exception as e:
            return False, f"Error: {str(e)}", None
    
    def verify_reset_token(self, token: str) -> Tuple[bool, str, Optional[int]]:
        """Verify password reset token.
        
        Args:
            token: Reset token from email
        
        Returns:
            (success, message, user_id) tuple. user_id is None if invalid/expired.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, email, reset_token_expires
                FROM users
                WHERE reset_token = ?
            ''', (token,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return False, "Invalid or expired reset link", None
            
            user_id, email, expires_str = row
            
            # Check if expired
            expires_at = datetime.fromisoformat(expires_str)
            if datetime.now() > expires_at:
                return False, "Reset link has expired. Please request a new one.", None
            
            return True, "Token valid", user_id
            
        except Exception as e:
            return False, f"Error: {str(e)}", None
    
    def reset_password(self, token: str, new_password: str) -> Tuple[bool, str]:
        """Reset user password with valid token.
        
        Args:
            token: Reset token from email
            new_password: New password (will be hashed)
        
        Returns:
            (success, message) tuple
        """
        try:
            # Verify token first
            valid, message, user_id = self.verify_reset_token(token)
            
            if not valid:
                return False, message
            
            # Validate password strength (same rules as signup, not just length)
            valid_password, password_error = self._validate_password(new_password)
            if not valid_password:
                return False, password_error
            
            # Hash password
            if bcrypt:
                password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            else:
                # Fallback to SHA-256 if bcrypt not available
                password_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
            
            # Update password and clear reset token
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users
                SET password_hash = ?,
                    reset_token = NULL,
                    reset_token_expires = NULL
                WHERE id = ?
            ''', (password_hash, user_id))
            
            conn.commit()
            conn.close()
            
            return True, "Password successfully reset"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def send_password_reset_email(self, email: str, token: str, name: str = None) -> Tuple[bool, str]:
        """Send password reset email with reset link.
        
        Args:
            email: Recipient email address
            token: Reset token
            name: User's name (optional)
        
        Returns:
            (success, message) tuple
        """
        if smtplib is None or MIMEText is None or MIMEMultipart is None:
            return False, "Email libraries not available"
        
        if not self.smtp_user or not self.smtp_password:
            return False, "SMTP credentials not configured"
        
        try:
            # Create reset link
            reset_link = f"http://localhost:5000/password-reset?token={token}"
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Reset your SlushAI password'
            msg['From'] = f"{self.smtp_from_name} <{self.smtp_from_email}>"
            msg['To'] = email
            
            # Plain text version
            text = f"""Hi{' ' + name if name else ''},

We received a request to reset your password for your SlushAI account.

To reset your password, click the link below:
{reset_link}

This link will expire in 1 hour.

If you didn't request a password reset, you can safely ignore this email.
Your password will not be changed unless you click the link above.

Best regards,
The SlushAI Team
"""
            
            # HTML version
            html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9fafb; padding: 40px 30px; }}
        .button {{ display: inline-block; padding: 16px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0; }}
        .footer {{ background: #374151; color: #9ca3af; padding: 20px; text-align: center; font-size: 12px; border-radius: 0 0 10px 10px; }}
        .warning {{ color: #ef4444; font-size: 14px; margin-top: 15px; }}
        .info-box {{ background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); border-radius: 8px; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 Password Reset Request</h1>
            <p>SlushAI 3D Modeller</p>
        </div>
        <div class="content">
            <p>Hi{' ' + name if name else ''},</p>
            <p>We received a request to reset your password for your SlushAI account.</p>
            <p style="text-align: center;">
                <a href="{reset_link}" class="button">Reset Password</a>
            </p>
            <div class="info-box">
                <p style="margin: 0;"><strong>⏱️ This link expires in 1 hour</strong></p>
            </div>
            <p>If you didn't request a password reset, you can safely ignore this email. Your password will not be changed unless you click the button above.</p>
            <p style="font-size: 12px; color: #6b7280; margin-top: 30px;">Or copy and paste this link into your browser:<br>
            <a href="{reset_link}" style="color: #667eea; word-break: break-all;">{reset_link}</a></p>
        </div>
        <div class="footer">
            <p>&copy; 2024 SlushAI 3D Modeller. All rights reserved.</p>
            <p>Spatial Latent Understanding & Synthetic Hyper-Accuracy Intelligence</p>
        </div>
    </div>
</body>
</html>
"""
            
            # Attach both versions
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            # Log email if email_manager is available
            if self.email_manager:
                try:
                    self.email_manager.log_outbound_email(
                        recipient_email=email,
                        sender_email=self.smtp_from_email,
                        subject='Reset your SlushAI password',
                        body_text=text,
                        body_html=html,
                        email_type='password_reset'
                    )
                except Exception as log_error:
                    # Don't fail email send if logging fails
                    pass
            
            return True, "Password reset email sent successfully"
            
        except Exception as e:
            return False, f"Failed to send email: {str(e)}"
    
    # --------------------- Referral System Methods ---------------------
    
    def generate_referral_code(self, user_id: int) -> Optional[str]:
        """Generate a unique referral code for a user.
        
        Returns:
            Referral code string, or None if failed
        """
        import random
        import string
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if user already has a referral code
        cursor.execute('SELECT referral_code FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row and row[0]:
            conn.close()
            return row[0]  # Already has a code
        
        # Generate unique 8-character code
        max_attempts = 10
        for _ in range(max_attempts):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            # Check if code is unique
            cursor.execute('SELECT id FROM users WHERE referral_code = ?', (code,))
            if not cursor.fetchone():
                # Code is unique, assign it
                cursor.execute('UPDATE users SET referral_code = ? WHERE id = ?', (code, user_id))
                conn.commit()
                conn.close()
                return code
        
        conn.close()
        return None  # Failed to generate unique code
    
    def record_donation(self, user_id: int, amount_usd: float, payment_method: str, 
                       payment_id: str = None) -> bool:
        """Record a donation and unlock Benefactor badge.
        
        Args:
            user_id: User ID
            amount_usd: Donation amount in USD
            payment_method: 'stripe' or 'crypto'
            payment_id: Stripe payment ID or crypto transaction hash
        
        Returns:
            True if successful
        """
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
            
            # Mark user as donor and unlock Benefactor badge
            cursor.execute('''
                UPDATE users 
                SET has_donated = 1, benefactor_badge_unlocked = 1
                WHERE id = ?
            ''', (user_id,))
            
            # Generate referral code if they don't have one
            cursor.execute('SELECT referral_code FROM users WHERE id = ?', (user_id,))
            if not cursor.fetchone()[0]:
                self.generate_referral_code(user_id)
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error recording donation: {e}")
            return False
    
    def apply_referral_code(self, user_id: int, referral_code: str) -> Tuple[bool, str]:
        """Apply a referral code to a new user.
        
        Args:
            user_id: New user's ID
            referral_code: Referral code to apply
        
        Returns:
            (success, message) tuple
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Find referrer by code
            cursor.execute('SELECT id FROM users WHERE referral_code = ?', (referral_code.upper(),))
            referrer = cursor.fetchone()
            
            if not referrer:
                conn.close()
                return False, "Invalid referral code"
            
            referrer_id = referrer[0]
            
            # Can't refer yourself
            if referrer_id == user_id:
                conn.close()
                return False, "You cannot use your own referral code"
            
            # Check if user already has a referrer
            cursor.execute('SELECT referred_by_user_id FROM users WHERE id = ?', (user_id,))
            current_referrer = cursor.fetchone()[0]
            
            if current_referrer:
                conn.close()
                return False, "You've already been referred by someone"
            
            # Apply referral
            cursor.execute('UPDATE users SET referred_by_user_id = ? WHERE id = ?', (referrer_id, user_id))
            
            # Record in referrals table
            cursor.execute('''
                INSERT INTO referrals (referrer_user_id, referred_user_id, referral_code)
                VALUES (?, ?, ?)
            ''', (referrer_id, user_id, referral_code.upper()))
            
            conn.commit()
            conn.close()
            
            return True, "Referral code applied successfully"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def get_referral_stats(self, user_id: int) -> Dict:
        """Get referral statistics for a user.
        
        Returns:
            Dict with referral stats
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get referral code
            cursor.execute('SELECT referral_code, benefactor_badge_unlocked FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            referral_code = row[0] if row else None
            has_badge = row[1] if row else False
            
            if not has_badge:
                conn.close()
                return {
                    'has_badge': False,
                    'message': 'Donate any amount to unlock the Benefactor badge and referral system!'
                }
            
            # Count total referrals
            cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ?', (user_id,))
            total_referrals = cursor.fetchone()[0]
            
            # Count paying referrals (standard, pro, or refill users)
            cursor.execute('''
                SELECT COUNT(*) FROM users
                WHERE referred_by_user_id = ? 
                AND subscription_tier IN ('standard_weekly', 'standard_yearly', 'pro_weekly', 'pro_yearly')
            ''', (user_id,))
            paying_referrals = cursor.fetchone()[0]
            
            # Get current week earnings
            now = datetime.now()
            week_number = now.isocalendar()[1]
            year = now.year
            
            cursor.execute('''
                SELECT earnings_usd, paid FROM referral_earnings
                WHERE user_id = ? AND week_number = ? AND year = ?
            ''', (user_id, week_number, year))
            earnings_row = cursor.fetchone()
            
            if earnings_row:
                this_week_earnings = earnings_row[0]
                paid = earnings_row[1]
            else:
                this_week_earnings = paying_referrals * 1.0
                paid = False
            
            # Get total lifetime earnings
            cursor.execute('SELECT SUM(earnings_usd) FROM referral_earnings WHERE user_id = ?', (user_id,))
            lifetime_earnings = cursor.fetchone()[0] or 0.0
            
            conn.close()
            
            return {
                'has_badge': True,
                'referral_code': referral_code,
                'referral_link': f'http://localhost:5000/?ref={referral_code}',
                'total_referrals': total_referrals,
                'paying_referrals': paying_referrals,
                'this_week_earnings': this_week_earnings,
                'this_week_paid': paid,
                'lifetime_earnings': lifetime_earnings
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def calculate_weekly_referral_earnings(self) -> int:
        """Calculate and record referral earnings for all users (run weekly).
        
        Returns:
            Number of users processed
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.now()
            week_number = now.isocalendar()[1]
            year = now.year
            
            # Get all users with Benefactor badge
            cursor.execute('SELECT id FROM users WHERE benefactor_badge_unlocked = 1')
            benefactors = cursor.fetchall()
            
            processed = 0
            for (benefactor_id,) in benefactors:
                # Count paying referrals for this benefactor
                cursor.execute('''
                    SELECT COUNT(*) FROM users
                    WHERE referred_by_user_id = ?
                    AND subscription_tier IN ('standard_weekly', 'standard_yearly', 'pro_weekly', 'pro_yearly')
                ''', (benefactor_id,))
                
                paying_count = cursor.fetchone()[0]
                earnings = paying_count * 1.0  # $1 per paying member
                
                if earnings > 0:
                    # Record or update earnings
                    cursor.execute('''
                        INSERT OR REPLACE INTO referral_earnings 
                        (user_id, week_number, year, paying_referrals_count, earnings_usd, paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (benefactor_id, week_number, year, paying_count, earnings))
                    processed += 1
            
            conn.commit()
            conn.close()
            
            return processed
            
        except Exception as e:
            print(f"Error calculating referral earnings: {e}")
            return 0
