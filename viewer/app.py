#!/usr/bin/env python3
"""Flask server for AI3DModeller web viewer."""
import os
import sys
import secrets
import hashlib
import logging
import json
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from flask import Flask, jsonify, send_from_directory, send_file, request, g, redirect, url_for, session
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import visitor tracker, task queue, user manager, analytics, crypto payment, issue manager, security, favorites, activity logger, and email manager
from src.ai3d.utils.visitor_tracker import VisitorTracker
from src.ai3d.utils.task_queue import TaskQueue
from src.ai3d.utils.user_manager import UserManager, User
from src.ai3d.utils.analytics_tracker import AnalyticsTracker
from src.ai3d.utils.crypto_payment_manager import CryptoPaymentManager
from src.ai3d.utils.stripe_payment_manager import (
    PLANS as STRIPE_PLANS,
    StripePaymentManager,
    StripeWebhookError,
    handle_webhook_event,
)
from src.ai3d.utils.issue_manager import IssueManager
from src.ai3d.utils.security import SecurityManager, create_security_headers
from src.ai3d.utils.favorites_manager import FavoritesManager
from src.ai3d.utils.mesh_stats import count_obj_vertices_faces
from src.ai3d.utils.remesh import remesh_obj
from src.ai3d.utils.export_glb import (
    export_glbs_for_generation,
    parse_export_flag,
)
from src.ai3d.utils.pbr_textures import (
    apply_pbr_for_generation,
    parse_pbr_flag,
)
from src.ai3d.utils.activity_logger import ActivityLogger
from src.ai3d.utils.email_manager import EmailManager

app = Flask(__name__, static_folder='.')

# Port the server listens on (5000 is also macOS AirPlay Receiver's port;
# set SLUSHAI_PORT to a free port instead of breaking AirPlay).
PORT = int(os.environ.get('SLUSHAI_PORT', '5000'))

def _load_or_create_secret_key():
    """SECRET_KEY from env, else a key generated once and saved to disk.

    Previously this was os.urandom() on every restart, which invalidated
    every session and every 30-day 'remember me' cookie on each restart.
    The saved key file is local-only (logs/.secret_key, mode 0600).
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_file = Path(__file__).parent.parent / 'logs' / '.secret_key'
    try:
        if key_file.exists():
            saved = key_file.read_text().strip()
            if saved:
                return saved
    except OSError:
        pass
    new_key = secrets.token_hex(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return new_key

app.config['SECRET_KEY'] = _load_or_create_secret_key()
# Secure cookie flag: True in production (SESSION_COOKIE_SECURE=1 or
# SLUSHAI_ENV=production). Local dev server is plain HTTP on 127.0.0.1, so
# the flag stays False there or the session cookie would never be set and
# login would silently fail on localhost.
app.config['SESSION_COOKIE_SECURE'] = (
    os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
    or os.environ.get('SLUSHAI_ENV', '').lower() == 'production'
)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 2592000  # 30 days
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

# Localhost only: the viewer is served from this same server, so cross-origin
# access is restricted to local origins (the configured port only).
LOCAL_ORIGINS = [f'http://localhost:{PORT}', f'http://127.0.0.1:{PORT}']
CORS(app, resources={r"/*": {"origins": LOCAL_ORIGINS}})
# Socket.IO for real-time streaming (threading to avoid extra deps)
socketio = SocketIO(app, cors_allowed_origins=LOCAL_ORIGINS, async_mode='threading')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'landing'
login_manager.login_message = 'Please sign in to access this page.'

# Initialize OAuth
oauth = OAuth(app)

# Google OAuth
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Facebook OAuth
facebook = oauth.register(
    name='facebook',
    client_id=os.environ.get('FACEBOOK_CLIENT_ID'),
    client_secret=os.environ.get('FACEBOOK_CLIENT_SECRET'),
    access_token_url='https://graph.facebook.com/oauth/access_token',
    access_token_params=None,
    authorize_url='https://www.facebook.com/dialog/oauth',
    authorize_params=None,
    api_base_url='https://graph.facebook.com/',
    client_kwargs={'scope': 'email public_profile'}
)

# Initialize rate limiter
def get_limiter_key():
    """Get rate limit key - use user_id if authenticated, otherwise IP."""
    try:
        if current_user.is_authenticated and hasattr(current_user, 'user_id'):
            return f'user:{current_user.user_id}'
    except (AttributeError, KeyError):
        pass
    return f'ip:{get_remote_address()}'

def log_function_call(func_name, **kwargs):
    """Log a function call with comprehensive context."""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'event': 'function_call',
        'function': func_name,
        'path': request.path if request else None,
        'method': request.method if request else None,
        'endpoint': request.endpoint if request else None,
        'ip': get_remote_address() if request else None,
        'limiter_key': get_limiter_key() if request else None,
    }
    
    # Add user info if authenticated
    if request and current_user.is_authenticated:
        try:
            log_entry['user'] = {
                'user_id': current_user.user_id,
                'email': getattr(current_user, 'email', 'unknown')
            }
        except:
            pass
    
    # Add any additional kwargs
    log_entry.update(kwargs)
    
    # Safety check for session_logger (will be initialized later)
    try:
        session_logger.logger.info(f"ACTION: {json.dumps(log_entry)}")
    except NameError:
        # Session logger not yet initialized, skip logging
        pass
    
    return log_entry

def track_action(action_name):
    """Decorator to automatically log function calls."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Log function entry
            log_function_call(f.__name__, action=action_name, args_count=len(args), kwargs_keys=list(kwargs.keys()))
            
            # Execute function
            try:
                result = f(*args, **kwargs)
                # Log success
                log_function_call(f.__name__, action=f"{action_name}_success", status='completed')
                return result
            except Exception as e:
                # Log failure
                log_function_call(f.__name__, action=f"{action_name}_error", status='failed', error=str(e))
                raise
        return decorated_function
    return decorator

def rate_limit_exceeded_handler(e):
    """Custom handler for rate limit exceeded - add 2 second delay for global limits."""
    import time

    # The object reaching this handler is version-dependent: some
    # flask-limiter versions pass an HTTPException with .description, others
    # pass the internal RequestLimit object, which has none (Nov 28 2025:
    # "'RequestLimit' object has no attribute 'description'" x6 in ~60 ms,
    # turning every 429 into a 500). Read it defensively.
    limit_description = getattr(e, 'description', None) or str(getattr(e, 'limit', e))
    
    # Get comprehensive request context
    limiter_key = get_limiter_key()
    user_info = None
    if current_user.is_authenticated:
        try:
            user_info = {
                'user_id': current_user.user_id,
                'email': getattr(current_user, 'email', 'unknown'),
                'name': getattr(current_user, 'name', 'unknown')
            }
        except:
            pass
    
    # Log comprehensive rate limit hit details
    rate_limit_log = {
        'timestamp': datetime.now().isoformat(),
        'event': 'rate_limit_exceeded',
        'limiter_key': limiter_key,
        'ip': get_remote_address(),
        'user': user_info,
        'endpoint': request.endpoint,
        'path': request.path,
        'method': request.method,
        'limit_description': limit_description,
        'user_agent': request.headers.get('User-Agent', ''),
        'referer': request.headers.get('Referer', '')
    }
    
    # A global limit breach blocks like any other limit (Stage 3, A-16).
    # The old code slept 2s and returned None, letting the request through.
    if 'global' in limit_description.lower():
        rate_limit_log['action'] = 'global_limit_blocked'
        try:
            session_logger.logger.warning(f"RATE_LIMIT_BLOCKED: {json.dumps(rate_limit_log)}")
        except NameError:
            pass
        return jsonify({
            'error': 'Global rate limit exceeded',
            'reason': limit_description,
            'retry_after': 60
        }), 429
    
    # For per-IP limits, return detailed error with reason
    rate_limit_log['action'] = 'rate_limit_blocked'
    try:
        session_logger.logger.warning(f"RATE_LIMIT_BLOCKED: {json.dumps(rate_limit_log)}")
        analytics_tracker.log_rate_limit_hit()
    except NameError:
        # Loggers not yet initialized
        pass
    
    # Parse the limit that was exceeded
    limit_info = limit_description
    
    if 'per 1 minute' in limit_info or 'per minute' in limit_info:
        title = "Too Many Requests"
        reason = "You've exceeded 100 requests per minute"
        explanation = "Your IP address has made too many requests in a short time. This limit helps protect our service from abuse."
        retry_time = "60 seconds"
        icon = "⏱️"
    elif 'per 1 day' in limit_info or 'per day' in limit_info:
        title = "Daily Limit Reached"
        reason = "You've exceeded 256,000 requests per day"
        explanation = "Your IP address has reached the maximum daily request limit. This will reset in 24 hours."
        retry_time = "24 hours"
        icon = "📅"
    else:
        title = "Rate Limit Exceeded"
        reason = "Too many requests"
        explanation = "Please wait a moment before trying again."
        retry_time = "a few moments"
        icon = "⚠️"
    
    # Check if this is an API request (wants JSON)
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'error': 'Rate limit exceeded',
            'reason': reason,
            'explanation': explanation,
            'retry_after': retry_time
        }), 429
    
    # Return HTML page for browser requests
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - SlushAI 3D Modeller</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
                color: #fff;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                text-align: center;
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                padding: 60px 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }}
            .icon {{
                font-size: 80px;
                margin-bottom: 24px;
                animation: pulse 2s ease-in-out infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.1); }}
            }}
            h1 {{
                font-size: 36px;
                font-weight: 700;
                margin-bottom: 16px;
                background: linear-gradient(135deg, #f43f5e, #f97316);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .reason {{
                font-size: 20px;
                color: #fbbf24;
                margin-bottom: 20px;
                font-weight: 600;
            }}
            .explanation {{
                font-size: 16px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.8);
                margin-bottom: 30px;
            }}
            .info-box {{
                background: rgba(249, 115, 22, 0.1);
                border: 1px solid rgba(249, 115, 22, 0.3);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 30px;
            }}
            .info-box h3 {{
                font-size: 14px;
                color: #f97316;
                margin-bottom: 12px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .info-box p {{
                font-size: 15px;
                color: rgba(255, 255, 255, 0.9);
                line-height: 1.6;
            }}
            .retry-info {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 12px 24px;
                background: rgba(34, 197, 94, 0.1);
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 8px;
                color: #22c55e;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 30px;
            }}
            .actions {{
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
            }}
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 14px 28px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                font-size: 15px;
                transition: all 0.2s;
                cursor: pointer;
                border: none;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #f43f5e, #f97316);
                color: white;
            }}
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(249, 115, 22, 0.4);
            }}
            .btn-secondary {{
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
            .details {{
                margin-top: 30px;
                padding-top: 30px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                font-size: 13px;
                color: rgba(255, 255, 255, 0.5);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{icon}</div>
            <h1>{title}</h1>
            <div class="reason">{reason}</div>
            <div class="explanation">{explanation}</div>
            
            <div class="info-box">
                <h3>Why am I seeing this?</h3>
                <p>Rate limits help us maintain service quality and prevent abuse. Each IP address has a fair usage quota to ensure everyone can access our service.</p>
            </div>
            
            <div class="retry-info">
                ⏳ Retry after: <strong>{retry_time}</strong>
            </div>
            
            <div class="actions">
                <button class="btn btn-primary" onclick="window.location.reload()">🔄 Try Again</button>
                <a href="/" class="btn btn-secondary">🏠 Go Home</a>
            </div>
            
            <div class="details">
                Your IP address has been rate limited. If you believe this is an error, please contact support.
            </div>
        </div>
    </body>
    </html>
    ''', 429

limiter = Limiter(
    app=app,
    key_func=get_limiter_key,
    default_limits=[],
    storage_uri="memory://",
    strategy="fixed-window"
)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
LOGS_DIR = PROJECT_ROOT / 'logs'
SCREENSHOTS_DIR = PROJECT_ROOT / 'outputs' / 'screenshots'

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
class SessionLogger:
    """Custom logger with separate error log (3-month retention) and regular log (truncates at 2560 entries)."""
    
    MAX_REQUESTS = 2560  # Max request log entries to keep
    ERROR_LOG_DAYS = 90  # Keep error logs for 3 months
    
    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.request_count = 0
        
        # Create archive directory
        archive_dir = self.log_dir / 'archive'
        archive_dir.mkdir(exist_ok=True)
        
        # Archive old session log if it exists
        old_log = self.log_dir / 'viewer.log'
        if old_log.exists():
            timestamp = datetime.fromtimestamp(old_log.stat().st_mtime).strftime('%Y%m%d_%H%M%S')
            archive_path = archive_dir / f'viewer_{timestamp}.log'
            old_log.rename(archive_path)
        
        # Setup new session log
        self.log_file = self.log_dir / 'viewer.log'
        self.error_log_file = self.log_dir / 'errors.log'  # Separate error log
        
        # Configure logging (INFO level for debugging)
        logging.basicConfig(
            level=logging.INFO,  # Show all info, warnings, and errors
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()  # Also print to console
            ]
        )
        
        # Add separate error file handler that only logs ERROR and CRITICAL
        error_handler = logging.FileHandler(self.error_log_file)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        
        self.logger = logging.getLogger('AI3DModeller')
        self.logger.addHandler(error_handler)
        self.logger.info(f'=== Session Started: {self.session_id} ===')
        
        # Cleanup old error logs (keep only last 3 months)
        self._cleanup_old_error_logs()
        
    def log_action(self, action_type, details):
        """Log user action with structured data."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'session': self.session_id,
            'type': action_type,
            'details': details
        }
        self.logger.info(json.dumps(log_entry))
        
        # Track request count and truncate if needed
        self.request_count += 1
        if self.request_count >= self.MAX_REQUESTS:
            self._truncate_log()
        
        return log_entry
    
    def _truncate_log(self):
        """Keep only the last MAX_REQUESTS entries in the log."""
        try:
            if not self.log_file.exists():
                return
            
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            
            # Keep only last MAX_REQUESTS lines
            if len(lines) > self.MAX_REQUESTS:
                kept_lines = lines[-self.MAX_REQUESTS:]
                with open(self.log_file, 'w') as f:
                    f.writelines(kept_lines)
                self.logger.info(f'Log truncated to {self.MAX_REQUESTS} entries')
            
            # Reset counter
            self.request_count = len(kept_lines) if len(lines) > self.MAX_REQUESTS else len(lines)
        except Exception as e:
            self.logger.error(f'Failed to truncate log: {e}')
    
    def _cleanup_old_error_logs(self):
        """Remove error log entries older than ERROR_LOG_DAYS (3 months)."""
        try:
            if not self.error_log_file.exists():
                return
            
            # Read all error log lines
            with open(self.error_log_file, 'r') as f:
                lines = f.readlines()
            
            # Filter lines to keep only those from the last 3 months
            cutoff_date = datetime.now() - timedelta(days=self.ERROR_LOG_DAYS)
            kept_lines = []
            
            for line in lines:
                try:
                    # Extract timestamp from log line format: "2025-11-27 14:05:39,716 [ERROR] ..."
                    timestamp_str = line.split('[')[0].strip()
                    log_time = datetime.strptime(timestamp_str.split(',')[0], '%Y-%m-%d %H:%M:%S')
                    
                    if log_time >= cutoff_date:
                        kept_lines.append(line)
                except (ValueError, IndexError):
                    # If we can't parse the date, keep the line to be safe
                    kept_lines.append(line)
            
            # Write back kept lines
            if len(kept_lines) < len(lines):
                with open(self.error_log_file, 'w') as f:
                    f.writelines(kept_lines)
                self.logger.info(f'Error log cleaned: kept {len(kept_lines)}/{len(lines)} entries from last {self.ERROR_LOG_DAYS} days')
        except Exception as e:
            # Don't log error here to avoid recursion
            pass

# Initialize session logger
session_logger = SessionLogger(LOGS_DIR)

# Initialize visitor tracker
VISITOR_DB = PROJECT_ROOT / 'logs' / 'visitors.db'
visitor_tracker = VisitorTracker(str(VISITOR_DB))

# Initialize email manager (before user_manager so it can be passed in)
EMAIL_DB = PROJECT_ROOT / 'logs' / 'emails.db'
email_manager = EmailManager(str(EMAIL_DB))

# Initialize user manager with email_manager for logging
USER_DB = PROJECT_ROOT / 'logs' / 'users.db'
JWT_SECRET = os.environ.get('JWT_SECRET', app.config['SECRET_KEY'])
user_manager = UserManager(str(USER_DB), jwt_secret=JWT_SECRET, email_manager=email_manager)

# Initialize analytics tracker
ANALYTICS_DB = PROJECT_ROOT / 'logs' / 'analytics.db'
ANALYTICS_LOG = PROJECT_ROOT / 'logs' / 'monthly_analytics.log'
analytics_tracker = AnalyticsTracker(str(ANALYTICS_DB), str(ANALYTICS_LOG))

# Initialize crypto payment manager
CRYPTO_DB = PROJECT_ROOT / 'logs' / 'crypto_payments.db'
RECEIVER_WALLETS = {
    'btc': os.environ.get('BTC_RECEIVER_ADDRESS', 'bc1qexample...'),
    'eth': os.environ.get('ETH_RECEIVER_ADDRESS', '0xExample...')
}
crypto_manager = CryptoPaymentManager(str(CRYPTO_DB), RECEIVER_WALLETS)

# Stripe payment manager (card payments via Stripe Checkout).
# Keys and Price IDs come from env vars; all empty until Gary connects
# Stripe (test mode) and creates the products in the Dashboard. The app
# starts and runs normally without them — Stripe checkout returns
# "not configured" until then. Crypto (above) stays available alongside.
stripe_manager = StripePaymentManager(
    secret_key=os.environ.get('STRIPE_SECRET_KEY', ''),
    webhook_secret=os.environ.get('STRIPE_WEBHOOK_SECRET', ''),
    publishable_key=os.environ.get('STRIPE_PUBLISHABLE_KEY', ''),
    price_ids={
        'standard_weekly': os.environ.get('STRIPE_PRICE_STANDARD_WEEKLY', ''),
        'standard_yearly': os.environ.get('STRIPE_PRICE_STANDARD_YEARLY', ''),
        'pro_weekly': os.environ.get('STRIPE_PRICE_PRO_WEEKLY', ''),
        'pro_yearly': os.environ.get('STRIPE_PRICE_PRO_YEARLY', ''),
        'refill': os.environ.get('STRIPE_PRICE_REFILL', ''),
    },
)

# Initialize issue manager
ISSUE_DB = PROJECT_ROOT / 'logs' / 'issues.db'
issue_manager = IssueManager(str(ISSUE_DB))

# Initialize security manager
SECURITY_DB = PROJECT_ROOT / 'logs' / 'security.db'
security_manager = SecurityManager(str(SECURITY_DB))

# Initialize activity logger
ACTIVITY_DB = PROJECT_ROOT / 'logs' / 'activity.db'
activity_logger = ActivityLogger(str(ACTIVITY_DB))

# Initialize favorites manager (pass user_manager and activity_logger)
FAVORITES_DB = PROJECT_ROOT / 'logs' / 'favorites.db'
favorites_manager = FavoritesManager(str(FAVORITES_DB), str(OUTPUTS_DIR), user_manager=user_manager, activity_logger=activity_logger)

# Initialize task queue
task_queue = TaskQueue()

# Active users tracking (in-memory, resets on server restart)
active_users = set()  # Set of user_ids currently logged in

def get_active_users_by_role():
    """Get count of active users by role (founder, moderator, admin)."""
    active_founder = set()
    active_moderators = set()
    active_admins = set()
    
    for user_id in active_users:
        user_data = user_manager.get_user_by_id(user_id)
        if user_data:
            tier = user_data.get('subscription_tier', '')
            if tier == 'founder' or user_data.get('email') == 'gdoman99@gmail.com':
                active_founder.add(user_id)
            elif tier == 'moderator':
                active_moderators.add(user_id)
            elif tier == 'admin':
                active_admins.add(user_id)
    
    return {
        'founder': len(active_founder),
        'moderators': len(active_moderators),
        'admins': len(active_admins)
    }

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    """Load user from database by user_id."""
    try:
        user_data = user_manager.get_user_by_id(user_id)
        if user_data:
            # Discarded temps stop loading: an existing Flask-Login
            # session for a discarded temp no longer authenticates.
            if user_data.get('is_temp') and user_data.get('temp_discarded_at'):
                return None
            return User(
                user_id=user_data.get('user_id', user_id),  # Fallback to provided user_id
                google_id=user_data.get('google_id'),
                email=user_data.get('email', ''),
                name=user_data.get('name', 'User'),
                picture=user_data.get('picture', '')
            )
    except Exception as e:
        session_logger.logger.error(f"Error loading user {user_id}: {e}")
    return None

# Task executor function
def execute_generation_task(task):
    """Execute generation task (called by queue worker)."""
    params = task.params
    temp_path = Path(params['temp_path'])
    backend = params['backend']
    filename = params['filename']
    
    # Calculate concurrent factor based on active workers
    queue_status = task_queue.get_queue_status()
    active_workers = queue_status.get('active_workers', 1)
    third_worker_active = queue_status.get('third_worker_active', False)
    
    # Determine which worker this task is running on
    worker_id = None
    with task_queue.lock:
        for wid, t in task_queue.current_tasks.items():
            if t and t.task_id == task.task_id:
                worker_id = wid
                break
    
    # Calculate CPU allocation
    if active_workers == 3:
        # 3 workers: split 80% as 30%, 30%, 20% (3rd gets 10% less)
        if worker_id == 2:  # 3rd worker (backup)
            concurrent_factor = 0.25  # 20% CPU (10% less than others)
        else:  # Primary workers 0 and 1
            concurrent_factor = 0.375  # 30% CPU each
    else:
        # Normal split: 2 workers = 40% each, 1 worker = 80%
        concurrent_factor = 1.0 / max(1, active_workers)
    
    session_logger.logger.info(f"Executing queued task {task.task_id}: {filename}")
    session_logger.logger.info(f"Active workers: {active_workers}, Worker ID: {worker_id}, CPU factor: {concurrent_factor:.2%}")
    
    # Emit started event
    try:
        socketio.emit('generation_started', {
            'task_id': task.task_id,
            'filename': filename,
            'backend': backend
        })
    except Exception:
        pass
    
    # Progress monitoring
    stop_flag = {'stop': False}
    def progress_loop():
        start = time.time()
        target_vertices = 120000.0
        tex_target = 1.5 * 1024 * 1024
        while not stop_flag['stop']:
            try:
                percent = 10
                stage = 'loading'
                elapsed = time.time() - start
                trip_path = OUTPUTS_DIR / 'triposr_temp' / '0'
                mesh_path = trip_path / 'mesh.obj'
                tex_path = trip_path / 'texture.png'
                
                if mesh_path.exists():
                    v = 0
                    with open(mesh_path, 'r', errors='ignore') as f:
                        for line in f:
                            if line.startswith('v '):
                                v += 1
                            if v >= target_vertices:
                                break
                    stage = 'extract'
                    percent = 30 + int(min(65, (v / target_vertices) * 65))
                if tex_path.exists():
                    stage = 'texture'
                    size = tex_path.stat().st_size
                    percent = 95 + int(min(4, (size / tex_target) * 4))
                
                socketio.emit('progress', {
                    'task_id': task.task_id,
                    'stage': stage,
                    'percent': int(min(99, max(10, percent))),
                    'elapsed': int(elapsed)
                })
            except Exception:
                pass
            time.sleep(0.5)
    
    import threading
    progress_thread = threading.Thread(target=progress_loop, daemon=True)
    progress_thread.start()
    
    # Run pipeline
    result = _run_pipeline(temp_path, backend, filename,
                           texture=params.get('texture', 'native'))
    stop_flag['stop'] = True
    progress_thread.join(timeout=1.0)
    
    # Cleanup temp file
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass
    
    if result.returncode != 0:
        raise Exception(f"Generation failed: {result.stderr}")

    # Surface a backend fallback in the task result (Stage 3, #13
    # honesty — found 2026-11-10 by the TripoSR diagnostic run): the CLI
    # prints e.g. "TripoSR timeout (30 minutes exceeded) ->
    # Fallback(native): ..." when TripoSR fails and native substitutes a
    # real mesh. The task completes, but the user asked for TripoSR — the
    # result must say which backend actually produced the mesh, not
    # silently present a native mesh as a TripoSR one. The message lives
    # in the CLI's stdout, which this function previously ignored.
    backend_used = backend
    result_note = None
    for _line in (result.stdout or '').splitlines():
        if 'Fallback(native)' in _line:
            result_note = _line.strip()
            backend_used = 'native'
            break

    # Find generated model
    candidates = [
        OUTPUTS_DIR / f"{temp_path.stem}_preview.obj",
        OUTPUTS_DIR / f"{Path(filename).stem}_preview.obj",
        OUTPUTS_DIR / f"{temp_path.stem}_refined.obj",
        OUTPUTS_DIR / f"{Path(filename).stem}_refined.obj"
    ]
    
    found = None
    for c in candidates:
        if c.exists():
            found = c
            break
    
    # No global-newest fallback (Stage 3, #13): picking the newest *.obj
    # anywhere under outputs/ could hand this user another user's model.
    # Only this task's own candidate outputs count.
    if not found or not found.exists():
        raise Exception("Generated model not found")
    
    session_logger.log_action('generate_success', {
        'task_id': task.task_id,
        'filename': filename,
        'output': found.name
    })

    # Vertex/face counts on the task result (Meshy surfaces these on
    # every task object; SlushAI only had them on /api/models). Counted
    # from this task's own output file, same helper as /api/models.
    vertices, faces = count_obj_vertices_faces(found)

    # Optional local remesh to a target face budget (Meshy Remesh,
    # local + free): the remeshed file sits next to the original
    # (<stem>_remeshed.obj) and the result carries the remeshed
    # counts alongside the original ones. A remesh failure never
    # fails the generation -- it logs and leaves the original mesh
    # and counts in place.
    remesh_result = None
    _remesh_target = params.get('remesh_target_faces')
    if _remesh_target:
        try:
            _remeshed_path = found.with_name(f"{found.stem}_remeshed.obj")
            remesh_result = remesh_obj(
                str(found), str(_remeshed_path),
                target_faces=int(_remesh_target),
                topology=params.get('remesh_topology', 'triangle'),
            )
        except Exception as _e:
            session_logger.logger.warning(
                f"Remesh failed for task {task.task_id}: {_e}")
            remesh_result = None

    # Optional local GLB export (Meshy export, local + free): the
    # generated mesh -- and the remeshed variant when one ran -- as
    # .glb next to the OBJ. An export failure never fails the
    # generation -- it logs and leaves the OBJ and counts in place,
    # the same guarantee the remesh step carries.
    _glb = export_glbs_for_generation(
        found,
        found.with_name(f"{found.stem}_remeshed.obj") if remesh_result else None,
        params.get('export_glb'),
        session_logger.logger.warning,
    )

    # Optional local PBR textures (Meshy PBR texture, local +
    # free): a textured OBJ (<stem>_textured.obj) with planar UVs
    # plus base-colour and metallic-roughness PNGs next to it, and
    # -- when a GLB was exported -- the textures embedded into
    # that GLB. A texturing failure never fails the generation --
    # it logs and leaves the untextured mesh and GLB in place,
    # the same guarantee the remesh and GLB steps carry.
    _pbr = apply_pbr_for_generation(
        found,
        found.with_name(f"{found.stem}_remeshed.obj") if remesh_result else None,
        _glb,
        params.get('pbr_textures'),
        session_logger.logger.warning,
    )
    _pbr_path = _pbr['textured_path']
    _pbr_remeshed_path = _pbr['remeshed_textured_path']
    
    # Register model with favorites manager for tracking
    if 'user_id' in params:
        favorites_manager.register_generated_model(params['user_id'], str(found.absolute()))
    
    # Calculate processing time
    processing_time = time.time() - task.params.get('start_time', time.time())
    analytics_tracker.log_model_generation(processing_time, True)  # Track successful generation
    
    # Log completion for quota tracking (only successful completions count)
    if 'user_id' in params:
        user_manager.log_task_complete(
            user_id=params['user_id'],
            task_id=task.task_id,
            status='completed'
        )
    
    return {
        'success': True,
        'preview_path': str(found.relative_to(PROJECT_ROOT)),
        'backend_requested': backend,
        'backend_used': backend_used,
        'note': result_note,
        'vertices': vertices,
        'faces': faces,
        'remeshed_vertices': remesh_result['output_vertices'] if remesh_result else None,
        'remeshed_faces': remesh_result['output_faces'] if remesh_result else None,
        'remesh_target_faces': remesh_result['target_faces'] if remesh_result else None,
        'remesh_topology': remesh_result['topology'] if remesh_result else None,
        'remeshed_path': str(_remeshed_path.relative_to(PROJECT_ROOT)) if remesh_result else None,
        'glb_path': str(_glb['glb_path'].relative_to(PROJECT_ROOT)) if _glb['glb_path'] else None,
        'glb_bytes': _glb['glb_bytes'],
        'remeshed_glb_path': str(_glb['remeshed_glb_path'].relative_to(PROJECT_ROOT)) if _glb['remeshed_glb_path'] else None,
        'remeshed_glb_bytes': _glb['remeshed_glb_bytes'],
        'pbr_textures': bool(_pbr['textured_path']),
        'textured_path': str(_pbr_path.relative_to(PROJECT_ROOT)) if _pbr_path else None,
        'pbr_basecolor_path': str(_pbr['basecolor_path'].relative_to(PROJECT_ROOT)) if _pbr['basecolor_path'] else None,
        'pbr_basecolor_bytes': _pbr['basecolor_bytes'],
        'pbr_metallic_roughness_path': str(_pbr['metallic_roughness_path'].relative_to(PROJECT_ROOT)) if _pbr['metallic_roughness_path'] else None,
        'pbr_metallic_roughness_bytes': _pbr['metallic_roughness_bytes'],
        'pbr_uv_count': _pbr['uv_count'],
        'remeshed_textured_path': str(_pbr_remeshed_path.relative_to(PROJECT_ROOT)) if _pbr_remeshed_path else None,
        'remeshed_pbr_basecolor_path': str(_pbr['remeshed_basecolor_path'].relative_to(PROJECT_ROOT)) if _pbr['remeshed_basecolor_path'] else None,
        'remeshed_pbr_basecolor_bytes': _pbr['remeshed_basecolor_bytes'],
        'remeshed_pbr_metallic_roughness_path': str(_pbr['remeshed_metallic_roughness_path'].relative_to(PROJECT_ROOT)) if _pbr['remeshed_metallic_roughness_path'] else None,
        'remeshed_pbr_metallic_roughness_bytes': _pbr['remeshed_metallic_roughness_bytes'],
        'remeshed_pbr_uv_count': _pbr['remeshed_uv_count'],
        'glb_pbr_embedded': _pbr['glb_pbr_embedded'],
        'remeshed_glb_pbr_embedded': _pbr['remeshed_glb_pbr_embedded'],
    }

# Wire up the executor
task_queue.set_executor(execute_generation_task)

# Global rate limit tracking
global_request_count = {'minute': 0, 'minute_start': time.time(), 'ten_min': 0, 'ten_min_start': time.time()}

def check_global_rate_limit():
    """Check global rate limits. Returns a 429 response when the global
    limit is breached, else None. (Stage 3 fix for A-16: the old code slept
    2s and let the request through, so the "global" limit never blocked.)"""
    now = time.time()

    # Reset counters if windows expired
    if now - global_request_count['minute_start'] >= 60:
        global_request_count['minute'] = 0
        global_request_count['minute_start'] = now

    if now - global_request_count['ten_min_start'] >= 600:
        global_request_count['ten_min'] = 0
        global_request_count['ten_min_start'] = now

    # Increment counters
    global_request_count['minute'] += 1
    global_request_count['ten_min'] += 1

    if global_request_count['minute'] >= 1000:
        reason = "Global limit: 1,000 requests/minute exceeded"
    elif global_request_count['ten_min'] >= 10000:
        reason = "Global limit: 10,000 requests/10 minutes exceeded"
    else:
        return None

    g.rate_limit_delayed = reason
    try:
        session_logger.logger.warning(f"GLOBAL_RATE_LIMIT_BLOCKED: {reason}")
    except NameError:
        pass
    return jsonify({
        'error': 'Global rate limit exceeded',
        'reason': reason,
        'retry_after': 60
    }), 429

# Request tracking middleware
@app.before_request
def before_request():
    """Track request start time, visitor, and security checks."""
    g.start_time = time.time()
    
    # Log incoming request
    incoming_log = {
        'timestamp': datetime.now().isoformat(),
        'event': 'request_received',
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'ip': get_remote_address(),
        'limiter_key': get_limiter_key(),
        'user_agent': request.headers.get('User-Agent', ''),
        'referer': request.headers.get('Referer', ''),
        'query_string': request.query_string.decode('utf-8')
    }
    
    # Add user info if authenticated
    if current_user.is_authenticated:
        try:
            incoming_log['user'] = {
                'user_id': current_user.user_id,
                'email': getattr(current_user, 'email', 'unknown')
            }
        except:
            pass
    
    session_logger.logger.info(f"INCOMING: {json.dumps(incoming_log)}")
    
    # Check global rate limits — a breach now actually blocks (429).
    _global_blocked = check_global_rate_limit()
    if _global_blocked is not None:
        return _global_blocked

    # CSRF defence (Stage 3, A-17 remainder): state-changing requests must
    # come from this app's own origin. SameSite=Lax on the session cookie
    # already stops cross-site POSTs carrying the cookie in modern browsers;
    # this rejects them outright when an Origin/Referer is present.
    # Exempt: Stripe posts the webhook itself, and Google/Facebook post the
    # OAuth callbacks — neither can carry our origin.
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.path not in (
        '/api/stripe/webhook', '/auth/callback', '/auth/facebook/callback',
    ):
        _origin = request.headers.get('Origin')
        if _origin and _origin not in LOCAL_ORIGINS:
            return jsonify({'error': 'Cross-origin request rejected'}), 403
        if not _origin:
            _referer = request.headers.get('Referer', '')
            if _referer and not any(
                _referer.startswith(o + '/') or _referer == o for o in LOCAL_ORIGINS
            ):
                return jsonify({'error': 'Cross-origin request rejected'}), 403
    
    # Get visitor IP. X-Forwarded-For is client-controlled and is only trusted
    # when a known proxy sits in front of the server (TRUST_PROXY=1); otherwise
    # anyone could spoof the IP used for the signup cap and security blocks.
    if os.environ.get('TRUST_PROXY', '').lower() in ('1', 'true', 'yes') and request.headers.getlist("X-Forwarded-For"):
        g.visitor_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        g.visitor_ip = request.remote_addr or "unknown"
    
    # Check for CRLF injection in headers
    for header_name, header_value in request.headers:
        if '\r' in header_value or '\n' in header_value:
            session_logger.logger.warning(f"CRLF injection attempt from {g.visitor_ip}")
            security_manager._log_attack(g.visitor_ip, 'crlf_injection', request.path, f"{header_name}:{header_value}")
            return jsonify({'error': 'Invalid request headers'}), 400
    
    # Validate Host header
    host_header = request.headers.get('Host', '')
    if host_header and not (host_header.startswith('localhost') or host_header.startswith('127.0.0.1') or ':5000' in host_header):
        # In production, validate against actual domain
        session_logger.logger.warning(f"Suspicious Host header from {g.visitor_ip}: {host_header}")
        security_manager._log_attack(g.visitor_ip, 'host_header_injection', request.path, host_header)
    
    # Security checks for all requests
    is_safe, reason = security_manager.check_request_security(
        ip_address=g.visitor_ip,
        endpoint=request.path,
        user_agent=request.headers.get('User-Agent')
    )
    
    if not is_safe:
        session_logger.logger.warning(f"Security block: {g.visitor_ip} - {reason}")
        
        # Check if this is a DDoS attack or connection limit issue
        if 'ddos' in reason.lower() or 'attack' in reason.lower() or 'concurrent' in reason.lower():
            return f'''
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Access Blocked - SlushAI 3D Modeller</title>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%);
                        color: #fff;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 700px;
                        text-align: center;
                        background: rgba(0, 0, 0, 0.3);
                        backdrop-filter: blur(10px);
                        border: 2px solid rgba(239, 68, 68, 0.5);
                        border-radius: 20px;
                        padding: 60px 40px;
                        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
                    }}
                    .icon {{
                        font-size: 100px;
                        margin-bottom: 24px;
                        animation: pulse 2s ease-in-out infinite;
                    }}
                    @keyframes pulse {{
                        0%, 100% {{ transform: scale(1); opacity: 1; }}
                        50% {{ transform: scale(1.1); opacity: 0.8; }}
                    }}
                    h1 {{
                        font-size: 42px;
                        font-weight: 700;
                        margin-bottom: 16px;
                        color: #fca5a5;
                    }}
                    .reason {{
                        font-size: 22px;
                        color: #fef3c7;
                        margin-bottom: 30px;
                        font-weight: 600;
                    }}
                    .explanation {{
                        font-size: 16px;
                        line-height: 1.8;
                        color: rgba(255, 255, 255, 0.9);
                        margin-bottom: 30px;
                    }}
                    .warning-box {{
                        background: rgba(239, 68, 68, 0.2);
                        border: 2px solid rgba(239, 68, 68, 0.4);
                        border-radius: 12px;
                        padding: 24px;
                        margin-bottom: 30px;
                    }}
                    .warning-box h3 {{
                        font-size: 16px;
                        color: #fca5a5;
                        margin-bottom: 12px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                    }}
                    .warning-box p {{
                        font-size: 15px;
                        color: rgba(255, 255, 255, 0.9);
                        line-height: 1.8;
                    }}
                    .ip-info {{
                        display: inline-block;
                        padding: 12px 24px;
                        background: rgba(0, 0, 0, 0.3);
                        border: 1px solid rgba(239, 68, 68, 0.3);
                        border-radius: 8px;
                        color: #fca5a5;
                        font-size: 14px;
                        font-weight: 600;
                        margin-bottom: 30px;
                        font-family: monospace;
                    }}
                    .details {{
                        margin-top: 30px;
                        padding-top: 30px;
                        border-top: 1px solid rgba(255, 255, 255, 0.2);
                        font-size: 13px;
                        color: rgba(255, 255, 255, 0.7);
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">🚫</div>
                    <h1>Access Blocked</h1>
                    <div class="reason">DDoS Attack Detected</div>
                    <div class="explanation">
                        Your IP address has been automatically blocked due to excessive request patterns 
                        consistent with a DDoS attack (over 1,000 requests in 10 seconds).
                    </div>
                    
                    <div class="warning-box">
                        <h3>🚨 Security Notice</h3>
                        <p>
                            This block is permanent and cannot be bypassed. Our system detected abnormal traffic 
                            patterns that violate our terms of service. If you believe this was triggered in error, 
                            please contact our security team with your IP address and timestamp.
                        </p>
                    </div>
                    
                    <div class="ip-info">
                        Blocked IP: {g.visitor_ip}
                    </div>
                    
                    <div class="details">
                        Block Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                        Reason: {reason}<br>
                        Duration: 24 hours (may be extended for repeat offenses)
                    </div>
                </div>
            </body>
            </html>
            ''', 403
        
        # For other security blocks, return JSON
        return jsonify({'error': 'Access denied', 'reason': reason}), 403
    
    # Validate input data for POST requests (JSON and form data)
    if request.method == 'POST':
        try:
            # Check JSON data
            if request.is_json:
                data = request.get_json(silent=True)
                if data:
                    for key, value in data.items():
                        if isinstance(value, str):
                            is_valid, reason = security_manager.validate_input(value)
                            if not is_valid:
                                attack_type = 'sql_injection' if 'sql' in reason.lower() else \
                                             'xss_attempt' if 'script' in value.lower() else \
                                             'command_injection' if 'cmd' in reason.lower() or 'eval' in value.lower() else \
                                             'path_traversal' if '..' in value else 'invalid_input'
                                security_manager._log_attack(g.visitor_ip, attack_type, request.path, f"{key}={value[:100]}")
                                security_manager._block_ip(g.visitor_ip, f"Malicious input detected: {attack_type}", attack_type=attack_type)
                                return jsonify({'error': 'Attack detected', 'reason': 'Malicious input blocked'}), 403
            
            # Check form data
            elif request.form:
                for key, value in request.form.items():
                    if isinstance(value, str):
                        is_valid, reason = security_manager.validate_input(value)
                        if not is_valid:
                            attack_type = 'sql_injection' if 'sql' in reason.lower() or 'union' in value.lower() or "'" in value else \
                                         'xss_attempt' if '<script' in value.lower() or 'javascript:' in value.lower() else \
                                         'command_injection' if '$(' in value or '`' in value or 'eval' in value.lower() else \
                                         'path_traversal' if '..' in value or '/etc/' in value.lower() else 'invalid_input'
                            security_manager._log_attack(g.visitor_ip, attack_type, request.path, f"{key}={value[:100]}")
                            security_manager._block_ip(g.visitor_ip, f"Malicious input detected: {attack_type}", attack_type=attack_type)
                            return jsonify({'error': 'Attack detected', 'reason': 'Malicious input blocked'}), 403
        except Exception as e:
            session_logger.logger.error(f"Error validating input: {e}")

@app.after_request
def after_request(response):
    """Track request completion, log visitor data, and add security headers."""
    if hasattr(g, 'start_time'):
        response_time_ms = (time.time() - g.start_time) * 1000
        
        # Track the request
        # (g.visitor_ip is set in before_request — but early returns there,
        # e.g. the CSRF 403 or the global 429, answer before it is assigned.
        # Fall back to the remote address instead of crashing after_request
        # with AttributeError and turning the real status into a 500.)
        _vip = getattr(g, 'visitor_ip', None) or request.remote_addr or 'unknown'
        visitor_id = visitor_tracker.track_request(
            ip_address=_vip,
            method=request.method,
            endpoint=request.endpoint or 'unknown',
            path=request.path,
            query_string=request.query_string.decode('utf-8'),
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            user_agent=request.headers.get('User-Agent', ''),
            referer=request.headers.get('Referer', '')
        )
        
        # Store visitor_id in g for route handlers
        g.visitor_id = visitor_id
        
        # Log comprehensive request details for debugging
        request_log = {
            'timestamp': datetime.now().isoformat(),
            'event': 'request_complete',
            'method': request.method,
            'path': request.path,
            'endpoint': request.endpoint or 'unknown',
            'status_code': response.status_code,
            'response_time_ms': round(response_time_ms, 2),
            'ip': _vip,
            'limiter_key': get_limiter_key(),
            'rate_limit_delayed': getattr(g, 'rate_limit_delayed', None),
            'visitor_id': visitor_id
        }
        
        # Add user info if authenticated
        if current_user.is_authenticated:
            try:
                request_log['user'] = {
                    'user_id': current_user.user_id,
                    'email': getattr(current_user, 'email', 'unknown')
                }
            except:
                pass
        
        # Log based on status code
        if response.status_code >= 400:
            session_logger.logger.warning(f"REQUEST: {json.dumps(request_log)}")
        else:
            session_logger.logger.info(f"REQUEST: {json.dumps(request_log)}")
    
    # Add security headers
    security_headers = create_security_headers()
    for header, value in security_headers.items():
        response.headers[header] = value
    
    # Add cache control headers to prevent stale data
    if request.endpoint in ['viewer', 'landing', 'get_user_profile']:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif request.endpoint and request.endpoint.startswith('api_'):
        response.headers['Cache-Control'] = 'no-store, max-age=0'
    
    # Remove server version header
    response.headers.pop('Server', None)
    
    return response

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def landing():
    """Landing page with Google sign-in (public access)."""
    if current_user.is_authenticated:
        return redirect(url_for('viewer'))
    session_logger.log_action('page_view', {'page': 'landing', 'ip': g.visitor_ip})
    analytics_tracker.log_visit(g.visitor_ip)  # Track visit
    return send_file('landing.html')

@app.route('/maintenance')
def maintenance():
    """Maintenance mode page when server is overloaded."""
    return send_file('maintenance.html')

@app.route('/pricing')
@login_required
def pricing():
    """Pricing page with subscription plans."""
    return send_file('pricing.html')

@app.route('/viewer')
@login_required
def viewer():
    """Main viewer page (requires authentication)."""
    # Check if server is overloaded (queue > 15 tasks)
    queue_status = task_queue.get_queue_status()
    if queue_status.get('queued_count', 0) > 15:
        analytics_tracker.log_maintenance_mode()  # Track maintenance mode activation
        return redirect(url_for('maintenance'))
    
    session_logger.log_action('page_view', {
        'page': 'viewer',
        'user_id': current_user.user_id,
        'ip': g.visitor_ip
    })
    return send_file('viewer.html')

@app.route('/auth/login')
def auth_login():
    """Initiate Google OAuth flow."""
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    """Handle Google OAuth callback."""
    try:
        # Get OAuth token
        token = google.authorize_access_token()
        
        # Get user info from Google
        user_info = token.get('userinfo')
        if not user_info:
            resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
            user_info = resp.json()
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        # NB: .get('name', email.split(...)) would evaluate the default eagerly
        # and crash with AttributeError when Google returns no email.
        name = user_info.get('name') or (email.split('@')[0] if email else 'User')
        picture = user_info.get('picture', '')
        
        # Get or create user in database. get_or_create_user — NOT the
        # get-by-google_id + create_user pair — is the only safe shape:
        # create_user does a bare INSERT, so a Google sign-in for an
        # email that already has a row (email signup, or a temp) raised
        # UNIQUE constraint failed: users.email and bounced the user to
        # the landing page (seen 2026-11-11). get_or_create_user links
        # the email_* row onto the Google identity instead, and refuses
        # to clobber a row owned by a different Google sub. The DB row
        # is authoritative for the session identity from here on.
        user_data = user_manager.get_or_create_user(
            google_id, email, name, picture)
        user_id = user_data['user_id']
        email = user_data.get('email', email)
        name = user_data.get('name', name)
        picture = user_data.get('picture', picture)
        
        # Create User object for Flask-Login
        user = User(
            user_id=user_id,
            google_id=google_id,
            email=email,
            name=name,
            picture=picture
        )
        
        # Log user in
        login_user(user, remember=True)
        session.permanent = True
        
        # Track active user
        active_users.add(user_id)
        
        session_logger.log_action('user_login', {
            'user_id': user_id,
            'email': email,
            'ip': g.visitor_ip
        })
        
        return redirect(url_for('viewer'))
        
    except Exception as e:
        session_logger.logger.error(f"OAuth callback error: {e}")
        return redirect(url_for('landing'))

@app.route('/auth/facebook')
def auth_facebook():
    """Initiate Facebook OAuth flow."""
    redirect_uri = url_for('auth_facebook_callback', _external=True)
    return facebook.authorize_redirect(redirect_uri)

@app.route('/auth/facebook/callback')
def auth_facebook_callback():
    """Handle Facebook OAuth callback."""
    try:
        # Get OAuth token
        token = facebook.authorize_access_token()
        
        # Get user info from Facebook
        resp = facebook.get('me?fields=id,name,email,picture')
        user_info = resp.json()
        
        facebook_id = user_info.get('id')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else f'User_{facebook_id}')
        picture = user_info.get('picture', {}).get('data', {}).get('url', '')
        
        # Get or create user in database (use facebook_id as google_id for now).
        # Same shape as the Google callback: get_or_create_user links an
        # existing email_* row instead of raising UNIQUE users.email.
        fb_google_id = f'fb_{facebook_id}'  # Prefix to distinguish from Google
        fb_email = email or f'{fb_google_id}@facebook.user'
        user_data = user_manager.get_or_create_user(
            fb_google_id, fb_email, name, picture)
        user_id = user_data['user_id']
        email = user_data.get('email', fb_email)
        name = user_data.get('name', name)
        picture = user_data.get('picture', picture)
        
        # Create User object for Flask-Login
        user = User(
            user_id=user_id,
            google_id=f'fb_{facebook_id}',
            email=email or f'fb_{facebook_id}@facebook.user',
            name=name,
            picture=picture
        )
        
        # Log user in
        login_user(user, remember=True)
        session.permanent = True
        
        # Track active user
        active_users.add(user_id)
        
        session_logger.log_action('user_login', {
            'user_id': user_id,
            'email': email,
            'provider': 'facebook',
            'ip': g.visitor_ip
        })
        
        return redirect(url_for('viewer'))
        
    except Exception as e:
        session_logger.logger.error(f"Facebook OAuth callback error: {e}")
        return redirect(url_for('landing'))

@app.route('/auth/logout')
@login_required
def auth_logout():
    """Log user out."""
    user_id = current_user.user_id
    
    session_logger.log_action('user_logout', {
        'user_id': user_id,
        'ip': g.visitor_ip
    })
    
    # Remove from active users
    active_users.discard(user_id)

    logout_user()
    session.pop('is_temp', None)
    return redirect(url_for('landing'))

@app.route('/api/check-username', methods=['POST'])
@limiter.limit("30 per minute", key_func=get_limiter_key)
def check_username_availability():
    """Check if username is available."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'error': 'Username required'}), 400
        
        valid, message = user_manager.validate_username(username)
        
        return jsonify({
            'available': valid,
            'message': message if not valid else 'Username available',
            'username': username
        }), 200
        
    except Exception as e:
        session_logger.logger.error(f"Username check error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/auth/email/signup', methods=['POST'])
@limiter.limit("5 per hour", key_func=get_limiter_key)
def auth_email_signup():
    """Create account with email/password."""
    try:
        # Check IP-based account limit (max 3 accounts per IP)
        user_ip = g.visitor_ip
        
        # Add signup_ip column if it doesn't exist (auto-migration)
        conn = sqlite3.connect(user_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'signup_ip' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN signup_ip TEXT')
            conn.commit()
        
        # Count existing accounts from this IP
        cursor.execute('SELECT COUNT(*) FROM users WHERE signup_ip = ?', (user_ip,))
        signup_count = cursor.fetchone()[0]
        conn.close()
        
        if signup_count >= 3:
            # Too many signups from this IP. JSON, not an HTML error page:
            # the landing page calls this as an API and does response.json(),
            # so an HTML body only ever surfaced as a generic 'Network error'.
            session_logger.logger.warning(f"Signup blocked: IP {user_ip} has {signup_count} accounts (max 3)")
            return jsonify({'error': f'This IP address has already created {signup_count} accounts. Maximum 3 accounts per IP address allowed to prevent abuse. If you need additional accounts, please contact support.'}), 403
        
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        username = data.get('username', '').strip()
        newsletter = data.get('newsletter', True)  # Default to True
        
        if not all([email, password, name, username]):
            return jsonify({'error': 'All fields are required'}), 400
        
        # Create user with signup_ip tracking
        success, message, user_id = user_manager.create_email_user(email, password, name, username, newsletter, signup_ip=user_ip)
        
        if not success:
            return jsonify({'error': message}), 400
        
        # Generate and send verification code
        try:
            code = user_manager.generate_verification_code(user_id)
            if not code:
                return jsonify({'error': 'Failed to generate verification code'}), 500
            
            # Update last_code_sent_at
            conn = sqlite3.connect(user_manager.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET last_code_sent_at = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
            
            # Send verification email
            email_success, email_message = user_manager.send_verification_email(email, code)
            
            session_logger.log_action('email_signup', {
                'user_id': user_id,
                'email': email,
                'email_sent': email_success,
                'ip': g.visitor_ip
            })
            
            if not email_success:
                session_logger.logger.warning(f"Failed to send verification email to {email}: {email_message}")
                return jsonify({
                    'success': True,
                    'message': 'Account created but verification email failed to send. Please try resending.',
                    'user_id': user_id,
                    'email_sent': False
                }), 201
            
            return jsonify({
                'success': True,
                'message': 'Account created! Check your email for the verification code.',
                'user_id': user_id,
                'email_sent': True
            }), 201
            
        except Exception as e:
            session_logger.logger.error(f"Failed to send verification code: {e}")
            return jsonify({
                'error': 'Failed to send verification code. Please try again.',
                'user_id': user_id
            }), 500
            
    except Exception as e:
        session_logger.logger.error(f"Email signup error: {e}")
        return jsonify({'error': 'Server error during signup'}), 500

@app.route('/auth/email/login', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_limiter_key)
def auth_email_login():
    """Login with email/password."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember_me = data.get('remember_me', True)  # Default to True for backwards compatibility
        
        session_logger.logger.info(f"Login attempt for email: {email}")
        
        if not all([email, password]):
            return jsonify({'error': 'Email and password required'}), 400
        
        # Verify credentials
        success, user_data = user_manager.verify_email_password(email, password)
        
        if not success or not user_data:
            session_logger.logger.warning(f"Failed login attempt for: {email}")
            # Don't reveal whether email exists or password is wrong
            return jsonify({'error': 'Invalid email or password'}), 401
        
        session_logger.logger.info(f"Password verified for: {email}, user_data keys: {list(user_data.keys())}")
        
        # Map 'id' to 'user_id' for consistency
        user_id = user_data.get('id') or user_data.get('user_id')
        
        # Discarded temps cannot sign in (temp system): the temp's login
        # is revoked on discard; the user continues via Google sign-in.
        if user_data.get('is_temp') and user_data.get('temp_discarded_at'):
            return jsonify({
                'error': 'This temp account has been discarded. Sign in with Google to continue as a full user.',
                'user_id': user_id,
                'email_verified': False
            }), 403

        # Check if email is verified
        if not user_data.get('email_verified', False):
            return jsonify({
                'error': 'Please verify your email before signing in',
                'user_id': user_id,
                'email_verified': False
            }), 403
        
        # Check if user is founder/admin/moderator - require PIN
        tier = user_data.get('subscription_tier', 'free')
        if tier in ['founder', 'admin', 'moderator']:
            # Generate PIN and send email (CSPRNG: random.randint is predictable)
            pin = ''.join(secrets.choice('0123456789') for _ in range(6))
            
            # Store PIN in database (expires in 10 minutes)
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(minutes=10)
            
            conn = sqlite3.connect(user_manager.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET verification_token = ?, verification_token_expires = ?
                WHERE id = ?
            ''', (pin, expires_at.isoformat(), user_id))
            conn.commit()
            conn.close()
            
            # Send PIN email
            pin_sent, pin_message = user_manager.send_verification_email(email, pin)
            
            # DEVELOPMENT: If email failed, print PIN to console for testing
            if not pin_sent:
                session_logger.logger.warning(f"⚠️ EMAIL NOT CONFIGURED - Development Mode PIN for {email}")
                session_logger.logger.warning(f"🔑 LOGIN PIN: {pin}")
                session_logger.logger.warning(f"⏱️ Expires in 10 minutes")
                pin_sent = True  # Allow login to proceed
            
            session_logger.logger.info(f"PIN required for {tier} account: {email}, PIN sent: {pin_sent}")
            
            return jsonify({
                'success': False,
                'requires_pin': True,
                'user_id': user_id,
                'tier': tier,
                'message': 'Security PIN sent to your email' if user_manager.smtp_user else 'Development mode: Check console for PIN',
                'pin_sent': pin_sent
            }), 200
        
        # Create User object for Flask-Login
        user = User(
            user_id=user_id,
            google_id=user_data.get('google_id'),
            email=user_data['email'],
            name=user_data['name'],
            picture=user_data.get('avatar_url', ''),
            email_verified=user_data.get('email_verified', False)
        )
        
        # Log user in with remember_me flag
        login_user(user, remember=remember_me)
        session.permanent = remember_me
        session.pop('is_temp', None)  # a normal login is not a temp session

        # Track active user
        active_users.add(user_id)

        session_logger.log_action('email_login', {
            'user_id': user_id,
            'email': email,
            'remember_me': remember_me,
            'ip': g.visitor_ip
        })
        
        session_logger.logger.info(f"Successful login for: {email}")
        
        return jsonify({
            'success': True,
            'message': 'Signed in successfully'
        }), 200
        
    except Exception as e:
        session_logger.logger.error(f"Email login error: {e}")
        import traceback
        session_logger.logger.error(traceback.format_exc())
        return jsonify({'error': 'Server error during login'}), 500

@app.route('/auth/email/verify-code', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_limiter_key)
def auth_email_verify_code():
    """Verify email with 6-digit code."""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        code = data.get('code', '').strip()
        
        if not user_id or not code:
            return jsonify({'error': 'User ID and code are required'}), 400
        
        success, message = user_manager.verify_email_code(user_id, code)
        
        if success:
            session_logger.log_action('email_verified', {
                'user_id': user_id,
                'ip': g.visitor_ip
            })
            
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        session_logger.logger.error(f"Email verification error: {e}")
        return jsonify({'error': 'Server error during verification'}), 500

@app.route('/auth/email/verify-pin', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_limiter_key)
def auth_email_verify_pin():
    """Verify login PIN for privileged accounts (founder/admin/moderator)."""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        pin = data.get('pin', '').strip()
        remember_me = data.get('remember_me', True)
        
        session_logger.logger.info(f"PIN verification attempt for user_id: {user_id}")
        
        if not user_id or not pin:
            return jsonify({'error': 'User ID and PIN are required'}), 400
        
        # Import datetime for this function
        from datetime import datetime
        
        # Check if user is currently banned from PIN attempts
        is_banned, ban_until = user_manager.check_pin_ban(user_id)
        if is_banned:
            ban_time = datetime.fromisoformat(ban_until)
            session_logger.logger.warning(f"PIN attempt blocked - user {user_id} is banned until {ban_until}")
            return jsonify({
                'success': False,
                'error': f"Too many failed attempts. Account locked until {ban_time.strftime('%I:%M %p')}",
                'banned': True,
                'ban_until': ban_until
            }), 403
        
        # Verify PIN
        success, message = user_manager.verify_email_code(user_id, pin)
        
        # Record the attempt and check for ban
        should_ban, ban_message = user_manager.record_pin_attempt(user_id, success, g.visitor_ip)
        
        if not success:
            session_logger.logger.warning(f"Invalid PIN for user_id: {user_id}")
            
            if should_ban:
                return jsonify({
                    'success': False,
                    'error': ban_message,
                    'banned': True
                }), 403
            
            return jsonify({
                'success': False,
                'error': message,
                'warning': ban_message if ban_message else None
            }), 400
        
        # Get user data
        user_data = user_manager.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        
        # Create User object for Flask-Login
        user = User(
            user_id=user_id,
            google_id=user_data.get('google_id'),
            email=user_data['email'],
            name=user_data['name'],
            picture=user_data.get('avatar_url', ''),
            email_verified=user_data.get('email_verified', False)
        )
        
        # Log user in with remember_me flag
        login_user(user, remember=remember_me)
        session.permanent = remember_me
        
        # Track active user
        active_users.add(user_id)
        
        # Mark session as PIN-authenticated for email management access
        session['pin_authenticated'] = True
        session['pin_auth_time'] = datetime.now().isoformat()
        session['user_tier'] = user_data.get('subscription_tier')
        
        session_logger.log_action('privileged_login', {
            'user_id': user_id,
            'email': user_data['email'],
            'tier': user_data.get('subscription_tier'),
            'remember_me': remember_me,
            'ip': g.visitor_ip
        })
        
        session_logger.logger.info(f"Successful privileged login for: {user_data['email']}")
        
        return jsonify({
            'success': True,
            'message': 'Signed in successfully'
        }), 200
        
    except Exception as e:
        session_logger.logger.error(f"PIN verification error: {e}")
        import traceback
        session_logger.logger.error(traceback.format_exc())
        return jsonify({'error': 'Server error during PIN verification'}), 500

@app.route('/auth/email/resend-code', methods=['POST'])
@limiter.limit("5 per hour", key_func=get_limiter_key)
def auth_email_resend_code():
    """Resend verification code with 60-second throttling."""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400
        
        success, message, code = user_manager.resend_verification_code(user_id)
        
        if success:
            session_logger.log_action('verification_code_resent', {
                'user_id': user_id,
                'ip': g.visitor_ip
            })
            
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        session_logger.logger.error(f"Resend code error: {e}")
        return jsonify({'error': 'Server error during resend'}), 500

# ----------------------------------------------------------------------
# Temp accounts (SlushAI temp system — HUB pattern)
#
# Pattern (Gary, 2026-11-11): the temp system follows TizWildin's auth
# — worker-issued session tokens, email-based, Google optional not
# required — so the system does NOT depend on Google. The per-temp API
# token (x-slushai-temp-token) is the grant, issued once at creation;
# the temp verifies by email (the 6-digit code flow); the daily scrape
# marks it verified and discards it; the user continues as a full user
# via Google sign-in. Q3 default: discard is non-destructive (data
# preserved). Q5 default: temp creation is admin-only (not the public
# signup route, so the 3-per-IP cap does not apply).
#
# Endpoints (all JSON in, JSON out):
#   POST /api/temp/create   (admin)  create a temp; token returned once
#   POST /api/temp/login             temp sign-in; temp bypass for the
#                                    email_verified gate; rotates the token
#   GET  /api/temp/status            own verification status (any temp)
#   GET  /api/temp/avatar            own avatar artifact (file + SHA-256)
#   POST /api/temp/discard  (admin)  discard a verified temp
#   POST /api/temp/scrape            daily scrape hook (staff session OR
#                                    x-slushai-scrape-token header)
#
# The avatar FILE itself is fetched from the existing /outputs/<file>
# route with the temp's Flask-Login session (serve_output enforces
# ownership); this endpoint returns the metadata + SHA-256, and the
# caller verifies the hash BEFORE use (the snapshot rule: the hash IS
# the identity; mismatch -> discard + re-fetch).
# ----------------------------------------------------------------------

def _temp_token_user():
    """The temp for a valid x-slushai-temp-token header, or None.
    The token is the auth; it is scoped to its own temp and revoked on
    discard (checked on every call by verify_temp_token)."""
    _tok = request.headers.get(user_manager.TEMP_TOKEN_HEADER, '')
    if not _tok:
        return None
    try:
        return user_manager.verify_temp_token(_tok)
    except Exception:
        return None


def _temp_caller():
    """The calling temp: by API token header, else by the logged-in
    session (the temp's own session). Returns the temp's user dict, or
    None. A discarded temp authenticates neither way."""
    _u = _temp_token_user()
    if _u:
        return _u
    if current_user.is_authenticated:
        try:
            _ud = user_manager.get_user_by_id(current_user.user_id)
        except Exception:
            _ud = None
        if _ud and _ud.get('is_temp') and not _ud.get('temp_discarded_at'):
            return _ud
    return None


def _temp_avatar_artifact(temp_id):
    """The temp's avatar artifact: its latest owned generated model
    (OBJ + texture — what TripoSR makes; no GLB yet). Returns the
    artifact dict, or None if the temp has generated nothing yet.
    Same scan as /api/models (owned .obj files, newest first; vertex /
    face counts read from the file); the SHA-256 is streamed so a large
    model never loads into RAM."""
    try:
        _owned = {str(Path(p).resolve()) for p in
                  favorites_manager.get_user_model_paths(temp_id)}
    except Exception:
        _owned = set()
    _best = None
    if not OUTPUTS_DIR.exists():
        return None
    for _obj in OUTPUTS_DIR.rglob('*.obj'):
        if str(_obj.resolve()) not in _owned:
            continue
        if '_refined' in _obj.stem:
            continue
        _mtime = _obj.stat().st_mtime
        if _best is None or _mtime > _best[0]:
            _best = (_mtime, _obj)
    if _best is None:
        return None
    _mtime, _obj = _best
    _vertices, _faces = count_obj_vertices_faces(_obj)
    _sha = hashlib.sha256()
    try:
        with open(_obj, 'rb') as _f:
            for _chunk in iter(lambda: _f.read(1024 * 1024), b''):
                _sha.update(_chunk)
    except Exception:
        return None
    _rel = _obj.relative_to(PROJECT_ROOT)
    _refined = _obj.parent / f"{_obj.stem.replace('_preview', '')}_refined.obj"
    return {
        'temp_id': temp_id,
        'file_url': f"/outputs/{_obj.relative_to(OUTPUTS_DIR)}",
        'path': str(_rel),
        'sha256': _sha.hexdigest(),
        'format': 'obj',
        'vertices': _vertices,
        'faces': _faces,
        'size': _obj.stat().st_size,
        'has_texture': _refined.exists(),
        'created_at': datetime.fromtimestamp(_mtime).isoformat(),
    }


@app.route('/api/temp/create', methods=['POST'])
@login_required
@limiter.limit("10 per minute", key_func=get_limiter_key)
def temp_create():
    """Create a temp account (admin-only). Returns the temp id + the API
    token ONCE — pass it to the temp user now; it cannot be retrieved
    again (only its hash is stored)."""
    if not _is_staff(current_user.user_id):
        return jsonify({'error': 'Admin only'}), 403
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()
    username = (data.get('username') or '').strip()
    if not all([email, password, name, username]):
        return jsonify({'error': 'All fields are required'}), 400
    success, message, user_id, token = user_manager.create_temp_user(
        email, password, name, username,
        created_by_admin_id=current_user.user_id)
    if not success:
        # create_temp_user can return a user_id even on token-issue
        # failure (the account exists); surface it so the admin can act.
        _body = {'error': message}
        if user_id:
            _body['user_id'] = user_id
            _body['temp_id'] = user_id
        return jsonify(_body), 400
    # Never log the token.
    session_logger.log_action('temp_created', {
        'user_id': user_id,
        'email': email,
        'created_by': current_user.user_id
    })
    return jsonify({
        'success': True,
        'temp_id': user_id,
        'user_id': user_id,
        'email': email,
        'is_temp': True,
        'state': 'temp',
        'api_token': token,
        'message': 'Temp account created. The API token is shown once — pass it to the temp user now; it cannot be retrieved again.'
    }), 201


@app.route('/api/temp/login', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_limiter_key)
def temp_login():
    """Temp sign-in (email/password). Bypasses the email_verified gate
    for temps only; rotates the temp API token and returns it once.
    The session is marked as a temp session."""
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''
        remember_me = data.get('remember_me', True)

        if not all([email, password]):
            return jsonify({'error': 'Email and password required'}), 400

        success, user_data = user_manager.verify_email_password(email, password)
        if not success or not user_data:
            session_logger.logger.warning(f"Failed temp login attempt for: {email}")
            return jsonify({'error': 'Invalid email or password'}), 401

        if not user_data.get('is_temp'):
            return jsonify({'error': 'Not a temp account. Use the normal sign-in.'}), 403

        user_id = user_data.get('id') or user_data.get('user_id')

        if user_data.get('temp_discarded_at'):
            return jsonify({
                'error': 'This temp account has been discarded. Sign in with Google to continue as a full user.',
                'user_id': user_id
            }), 403

        # Rotate the API token (old token revoked, new one returned once).
        token = user_manager._issue_temp_token(user_id)

        user = User(
            user_id=user_id,
            google_id=user_data.get('google_id'),
            email=user_data['email'],
            name=user_data.get('name'),
            picture=user_data.get('avatar_url', ''),
            email_verified=user_data.get('email_verified', False)
        )
        login_user(user, remember=remember_me)
        session.permanent = remember_me
        session['is_temp'] = True
        active_users.add(user_id)

        session_logger.log_action('temp_login', {
            'user_id': user_id,
            'email': email,
            'remember_me': remember_me,
            'ip': g.visitor_ip
        })

        return jsonify({
            'success': True,
            'message': 'Signed in as temp',
            'user_id': user_id,
            'temp_id': user_id,
            'is_temp': True,
            'state': user_manager.temp_state(user_data),
            'email_verified': bool(user_data.get('email_verified')),
            'api_token': token
        }), 200

    except Exception as e:
        session_logger.logger.error(f"Temp login error: {e}")
        import traceback
        session_logger.logger.error(traceback.format_exc())
        return jsonify({'error': 'Server error during temp login'}), 500


@app.route('/api/temp/status', methods=['GET'])
def temp_status():
    """Verification status lookup. Any temp can check its own status
    (the Lucid design rule: a status lookup, not a hidden gate)."""
    caller = _temp_caller()
    if not caller:
        return jsonify({'error': 'Temp authentication required'}), 401
    status = user_manager.get_temp_status(
        caller.get('id') or caller.get('user_id'))
    if not status:
        return jsonify({'error': 'Not a temp account'}), 403
    return jsonify(status), 200


@app.route('/api/temp/avatar', methods=['GET'])
def temp_avatar():
    """The temp's avatar artifact for Lucid: the temp's latest generated
    model (OBJ + texture; no GLB yet) as file + SHA-256. Lucid verifies
    the hash BEFORE use; mismatch -> discard + re-fetch. The file itself
    is fetched from /outputs/<file> with the temp's session.
    Staff (logged in) may fetch any temp's avatar with ?temp_id= (the
    data is preserved after discard, so a discarded temp's avatar is
    still reachable to staff)."""
    # Staff session + ?temp_id= : admin fetch of any temp (incl. discarded).
    if current_user.is_authenticated:
        try:
            if _is_staff(current_user.user_id):
                _tid = request.args.get('temp_id')
                if _tid:
                    _t = user_manager.get_user_by_id(int(_tid))
                    if _t and _t.get('is_temp'):
                        _art = _temp_avatar_artifact(int(_tid))
                        if not _art:
                            return jsonify({
                                'error': 'No avatar yet — generate a model first',
                                'temp_id': int(_tid)
                            }), 404
                        return jsonify(_art), 200
                    return jsonify({'error': 'Temp not found'}), 404
        except (TypeError, ValueError):
            return jsonify({'error': 'temp_id must be an integer'}), 400
        except Exception:
            pass
    caller = _temp_caller()
    if not caller:
        return jsonify({'error': 'Temp authentication required'}), 401
    temp_id = caller.get('id') or caller.get('user_id')
    artifact = _temp_avatar_artifact(temp_id)
    if not artifact:
        return jsonify({
            'error': 'No avatar yet — generate a model first',
            'temp_id': temp_id
        }), 404
    return jsonify(artifact), 200


@app.route('/api/temp/discard', methods=['POST'])
@login_required
@limiter.limit("10 per minute", key_func=get_limiter_key)
def temp_discard():
    """Discard a temp (admin). Non-destructive (Q3 default): marks the
    temp discarded, revokes the API token, records the audit; the
    temp's models/outputs are PRESERVED (nothing is deleted)."""
    if not _is_staff(current_user.user_id):
        return jsonify({'error': 'Admin only'}), 403
    data = request.get_json(silent=True) or {}
    temp_id = data.get('temp_id') or data.get('user_id')
    if not temp_id:
        return jsonify({'error': 'temp_id required'}), 400
    try:
        temp_id = int(temp_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'temp_id must be an integer'}), 400
    ok, message = user_manager.discard_temp(
        temp_id, reason=f'admin:{current_user.user_id}')
    if not ok:
        return jsonify({'error': message}), 400
    session_logger.log_action('temp_discarded', {
        'user_id': temp_id,
        'by': current_user.user_id
    })
    return jsonify({
        'success': True,
        'temp_id': temp_id,
        'state': 'discarded',
        'message': message
    }), 200


@app.route('/api/temp/scrape', methods=['POST'])
def temp_scrape():
    """Daily scrape hook (Q2: checks email confirmation via the 6-digit
    code flow). Runs run_temp_scrape(): marks temps verified where the
    email is confirmed, then discards verified temps. Auth: a staff
    session, OR the x-slushai-scrape-token header matching
    TEMP_SCRAPE_TOKEN from the environment. Fails closed when the token
    is not configured (the header path is then disabled)."""
    _authorized = False
    _tok = request.headers.get(user_manager.TEMP_SCRAPE_HEADER, '')
    _expected = os.environ.get('TEMP_SCRAPE_TOKEN', '')
    if _tok and _expected and secrets.compare_digest(_tok, _expected):
        _authorized = True
    elif current_user.is_authenticated:
        try:
            _authorized = _is_staff(current_user.user_id)
        except Exception:
            _authorized = False
    if not _authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    summary = user_manager.run_temp_scrape()
    session_logger.log_action('temp_scrape', summary)
    return jsonify({'success': True, **summary}), 200


@app.route('/auth/password-reset/request', methods=['POST'])
@limiter.limit("3 per hour", key_func=get_limiter_key)
def password_reset_request():
    """Request password reset - generates token and sends email."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Generate reset token
        success, message, token = user_manager.generate_password_reset_token(email)
        
        if not success:
            return jsonify({'error': message}), 400
        
        # Get user data for email
        user_data = user_manager.get_user_by_email(email)
        
        if token and user_data:  # Only send if user exists
            # Send reset email
            email_success, email_message = user_manager.send_password_reset_email(
                email, token, user_data.get('name')
            )
            
            # DEVELOPMENT: If email not configured, print reset link
            if not email_success:
                session_logger.logger.warning(f"⚠️ EMAIL NOT CONFIGURED - Development Mode")
                session_logger.logger.warning(f"🔑 Password reset link for {email}:")
                session_logger.logger.warning(f"http://localhost:5000/password-reset?token={token}")
            
            session_logger.log_action('password_reset_requested', {
                'email': email,
                'email_sent': email_success,
                'ip': g.visitor_ip
            })
        
        # Always return success to not reveal if email exists
        return jsonify({
            'success': True,
            'message': message
        }), 200
        
    except Exception as e:
        session_logger.logger.error(f"Password reset request error: {e}")
        return jsonify({'error': 'Server error during password reset request'}), 500

@app.route('/auth/password-reset/complete', methods=['POST'])
@limiter.limit("5 per hour", key_func=get_limiter_key)
def password_reset_complete():
    """Complete password reset with token and new password."""
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        new_password = data.get('password', '')
        
        if not token or not new_password:
            return jsonify({'error': 'Token and password are required'}), 400
        
        # Reset password
        success, message = user_manager.reset_password(token, new_password)
        
        if success:
            session_logger.log_action('password_reset_completed', {
                'ip': g.visitor_ip
            })
            
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        session_logger.logger.error(f"Password reset complete error: {e}")
        return jsonify({'error': 'Server error during password reset'}), 500

@app.route('/password-reset')
def password_reset_page():
    """Password reset page."""
    return send_file('password_reset.html')

@app.route('/api/support/submit', methods=['POST'])
@limiter.limit(
    "5 per hour",
    key_func=lambda: f"user:{current_user.user_id}" if current_user.is_authenticated else f"ip:{get_remote_address()}"
)
def support_submit():
    """Submit a support request (public or member)."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message = data.get('message', '').strip()
        is_member = data.get('is_member', False)
        
        if not all([name, email, message]):
            return jsonify({'error': 'All fields are required'}), 400
        
        # Store support request in email_manager as an inbound email
        try:
            email_manager.log_inbound_email(
                sender_email=email,
                subject=f'Support Request from {name}',
                body_text=f"From: {name} ({email})\nMember: {'Yes' if is_member else 'No'}\n\n{message}",
                sender_name=name,
                metadata={'is_member': is_member, 'user_id': current_user.user_id if current_user.is_authenticated else None}
            )
        except Exception as e:
            session_logger.logger.error(f"Failed to log support request: {e}")
            return jsonify({'error': 'Failed to submit support request'}), 500
        
        session_logger.log_action('support_request', {
            'name': name,
            'email': email,
            'is_member': is_member,
            'user_id': current_user.user_id if current_user.is_authenticated else None,
            'ip': g.visitor_ip
        })
        
        return jsonify({
            'success': True,
            'message': 'Support request submitted successfully'
        }), 200
        
    except Exception as e:
        session_logger.logger.error(f"Support submission error: {e}")
        return jsonify({'error': 'Server error during support submission'}), 500

@app.route('/docs')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def docs():
    """Documentation page with links to Terms and Privacy Policy (rate limited)."""
    return send_file('docs.html')

@app.route('/donate')
def donate_page():
    """Donations are not set up yet — say so plainly instead of linking
    nowhere. The pricing page holds the real payment options."""
    return (
        '<!DOCTYPE html><html><head><title>Donate — SlushAI</title></head>'
        '<body style="font-family:sans-serif;max-width:640px;margin:80px auto;padding:0 20px;">'
        '<h1>Donate</h1>'
        '<p>Donations are not set up yet. There is no donation address or form '
        'right now, so please do not send anything.</p>'
        '<p>Paid plans are on the <a href="/pricing">pricing page</a>.</p>'
        '</body></html>', 200)

@app.route('/users')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def users_list_page():
    """Public user directory page."""
    return send_file('users.html')

@app.route('/docs/terms')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def terms_of_service():
    """Serve Terms of Service HTML page."""
    return send_file('terms.html')

@app.route('/docs/privacy')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def privacy_policy():
    """Serve Privacy Policy HTML page."""
    return send_file('privacy.html')

@app.route('/docs/api')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def api_documentation():
    """Serve API Reference HTML page with syntax-highlighted code examples."""
    return send_file('api_reference.html')

@app.route('/docs/rate-limits')
@limiter.limit("100 per minute; 256000 per day", key_func=get_limiter_key)
def rate_limits_documentation():
    """Serve Rate Limits Documentation."""
    return send_file('../docs/RATE_LIMITS.md', mimetype='text/markdown')

# ============================================================================
# API ROUTES (Protected)
# ============================================================================

@app.route('/classic')
@login_required
def classic():
    return send_file('index.html')

@app.route('/api/health')
def health():
    """Health check endpoint - verify server is running."""
    return jsonify({
        '_meta': {
            'endpoint': '/api/health',
            'description': 'Server health check and status verification',
            'method': 'GET',
            'rate_limit': 'No rate limit (public endpoint)',
            'authentication': 'Not required',
            'fields': {
                'ok': 'Boolean indicating server is operational',
                'time': 'Current Unix timestamp (seconds since epoch)',
                'outputs_dir': 'Absolute path to model outputs directory'
            }
        },
        'ok': True,
        'time': time.time(),
        'outputs_dir': str(OUTPUTS_DIR)
    })

@app.route('/api/capacity')
def get_capacity():
    """Get current user capacity by tier (public endpoint)."""
    try:
        counts = user_manager.get_user_counts_by_tier()
        
        # Get worker status from task queue
        queue_status = task_queue.get_queue_status()
        
        # Get active users by role
        active_by_role = get_active_users_by_role()
        
        return jsonify({
            'success': True,
            '_meta': {
                'endpoint': '/api/capacity',
                'description': 'Real-time platform capacity and usage statistics across all subscription tiers',
                'rate_limit': 'No rate limit (public endpoint)',
                'fields': {
                    'capacity': 'Object containing tier-specific and worker capacity data',
                    'capacity.{tier}.current': 'Number of registered users in this tier',
                    'capacity.{tier}.max': 'Maximum allowed users for this tier',
                    'capacity.{tier}.available': 'Remaining slots available for new users',
                    'capacity.{tier}.percent_full': 'Percentage of tier capacity currently used',
                    'capacity.{tier}.active': 'Number of currently logged-in users (staff tiers only)',
                    'capacity.workers.active': 'Current number of active worker processes',
                    'capacity.workers.max': 'Maximum worker limit (scales 5-20)',
                    'capacity.workers.processing': 'Number of models currently being generated',
                    'capacity.workers.queue_length': 'Number of pending generation tasks',
                    'capacity.workers.total_processed': 'Total models generated since server start'
                }
            },
            'capacity': {
                'founder': {
                    'count': counts['founder_count'],
                    'email': counts['founder_email'],
                    'active': active_by_role['founder']
                },
                'free': {
                    'current': counts['free_count'],
                    'max': counts['free_max'],
                    'available': counts['free_available'],
                    'percent_full': round((counts['free_count'] / counts['free_max']) * 100, 1)
                },
                'standard': {
                    'current': counts['standard_count'],
                    'max': counts['standard_max'],
                    'available': counts['standard_available'],
                    'percent_full': round((counts['standard_count'] / counts['standard_max']) * 100, 1) if counts['standard_max'] > 0 else 0
                },
                'pro': {
                    'current': counts['pro_count'],
                    'max': counts['pro_max'],
                    'available': counts['pro_available'],
                    'percent_full': round((counts['pro_count'] / counts['pro_max']) * 100, 1) if counts['pro_max'] > 0 else 0
                },
                'moderator': {
                    'current': counts['moderator_count'],
                    'max': counts['moderator_max'],
                    'available': counts['moderator_available'],
                    'percent_full': round((counts['moderator_count'] / counts['moderator_max']) * 100, 1) if counts['moderator_max'] > 0 else 0,
                    'active': active_by_role['moderators']
                },
                'admin': {
                    'current': counts['admin_count'],
                    'max': counts['admin_max'],
                    'available': counts['admin_available'],
                    'percent_full': round((counts['admin_count'] / counts['admin_max']) * 100, 1) if counts['admin_max'] > 0 else 0,
                    'active': active_by_role['admins']
                },
                'total': {
                    'current': counts['total_count'],
                    'max': counts['total_max'],
                    'percent_full': round((counts['total_count'] / counts['total_max']) * 100, 1)
                },
                'workers': {
                    'active': queue_status['active_workers'],
                    'max': queue_status['max_workers'],
                    'base': queue_status['base_workers'],
                    'target': queue_status['target_workers'],
                    'processing': queue_status['processing'],
                    'queue_length': queue_status['queue_length'],
                    'total_processed': queue_status.get('total_completed', 0)
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/profile')
@login_required
def get_user_profile():
    """Get current user's profile and stats."""
    user_data = user_manager.get_user_by_id(current_user.user_id)
    
    if not user_data:
        return jsonify({'error': 'User not found'}), 404
    
    # Get quota info
    can_generate, quota_info = user_manager.check_quota(current_user.user_id)
    
    # Get referral stats if Benefactor
    referral_stats = None
    if user_data.get('benefactor_badge_unlocked'):
        referral_stats = user_manager.get_referral_stats(current_user.user_id)
    
    return jsonify({
        'user_id': user_data['user_id'],
        'email': user_data['email'],
        'name': user_data['name'],
        'username': user_data.get('username', ''),
        'picture': user_data['picture'],
        'subscription_tier': user_data.get('subscription_tier', 'free'),
        'badge_level': user_data['badge_level'],
        'badge_name': user_manager.BADGE_NAMES[user_data['badge_level']],
        'badge_color': user_manager.BADGE_COLORS[user_data['badge_level']],
        'total_models': user_data['total_models_generated'],
        'joined_date': user_data['created_at'],
        'quota': quota_info,
        'benefactor_badge': user_data.get('benefactor_badge_unlocked', False),
        'referral_stats': referral_stats
    })

@app.route('/api/admin/users/list')
@login_required
@limiter.limit("60 per minute", key_func=get_limiter_key)
def admin_users_list():
    """Get list of all users (staff only)."""
    # Check if user is staff
    user = user_manager.get_user_by_id(current_user.user_id)
    if not user or user.get('subscription_tier') not in ['founder', 'admin', 'moderator']:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get filter parameters
        tier = request.args.get('tier')
        search = request.args.get('search', '').strip()
        
        import sqlite3
        conn = sqlite3.connect(user_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = '''SELECT id, username, name, email, subscription_tier, badge_level, 
                   lifetime_completions, created_at, last_login FROM users'''
        params = []
        
        conditions = []
        if tier:
            conditions.append('subscription_tier = ?')
            params.append(tier)
        
        if search:
            conditions.append('(username LIKE ? OR email LIKE ? OR name LIKE ?)')
            search_pattern = f'%{search}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY created_at DESC'
        
        cursor.execute(query, params)
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Check active status
        for usr in users:
            usr['active'] = usr['id'] in active_users
            # Mask email for privacy (show first 3 chars + domain)
            email = usr.get('email', '')
            if '@' in email:
                local, domain = email.split('@', 1)
                usr['email_masked'] = f"{local[:3]}***@{domain}"
            else:
                usr['email_masked'] = email
        
        return jsonify({
            'success': True,
            'users': users,
            'total': len(users)
        })
        
    except Exception as e:
        session_logger.logger.error(f"Admin users list error: {e}")
        return jsonify({'error': 'Server error'}), 500

# ---- Ownership helpers (Stage 3, #9) ----
# Models are registered per user in favorites_manager.generated_models when a
# queued generation completes. Staff (founder/admin/moderator) may see all.
STAFF_TIERS = ('founder', 'admin', 'moderator')

def _is_staff(user_id):
    try:
        _u = user_manager.get_user_by_id(user_id)
        return bool(_u) and _u.get('subscription_tier') in STAFF_TIERS
    except Exception:
        return False

def _user_can_access_output(user_id, resolved_path):
    """True if the resolved output file belongs to this user (or a sibling
    .png/.mtl of one of their models), or the user is staff."""
    if _is_staff(user_id):
        return True
    try:
        owned = favorites_manager.get_user_model_paths(user_id)
    except Exception:
        owned = []
    owned_set = {str(Path(p).resolve()) for p in owned}
    target = str(Path(resolved_path).resolve())
    if target in owned_set:
        return True
    # Sibling files of an owned model (texture .png, material .mtl): allow
    # any file whose base stem matches an owned model's base stem.
    owned_stems = {Path(p).stem for p in owned_set}
    owned_stems |= {s.replace('_preview', '').replace('_refined', '') for s in owned_stems}
    base = Path(target).stem.replace('_preview', '').replace('_refined', '')
    return base in owned_stems

@app.route('/api/models')
@login_required
def list_models():
    """List all available 3D models."""
    session_logger.log_action('api_call', {
        'endpoint': '/api/models',
        'method': 'GET',
        'user_id': current_user.user_id
    })
    models = []

    if not OUTPUTS_DIR.exists():
        return jsonify([])

    # Ownership scope (Stage 3, #9): a user only sees models registered to
    # them in favorites_manager.generated_models; staff see everything.
    # Legacy unregistered outputs (e.g. the temp_example evidence meshes)
    # are staff-only.
    _owned_paths = None
    if not _is_staff(current_user.user_id):
        try:
            _owned_paths = {str(Path(p).resolve()) for p in
                            favorites_manager.get_user_model_paths(current_user.user_id)}
        except Exception:
            _owned_paths = set()

    # Find all .obj files
    for obj_file in OUTPUTS_DIR.rglob('*.obj'):
        if _owned_paths is not None and str(obj_file.resolve()) not in _owned_paths:
            continue
        # Skip refined versions (we'll show them as part of preview)
        if '_refined' in obj_file.stem:
            continue
            
        relative_path = obj_file.relative_to(PROJECT_ROOT)
        
        # Vertex/face count from file (same helper as the task result).
        vertices, faces = count_obj_vertices_faces(obj_file)
        
        # Check if there's a refined version
        refined_path = obj_file.parent / f"{obj_file.stem.replace('_preview', '')}_refined.obj"
        has_texture = refined_path.exists()
        
        models.append({
            'name': obj_file.stem,
            'path': str(relative_path),
            'refined_path': str(refined_path.relative_to(PROJECT_ROOT)) if has_texture else None,
            'vertices': vertices,
            'faces': faces,
            'size': obj_file.stat().st_size,
            'modified': obj_file.stat().st_mtime
        })
    
    # Sort by modification time (newest first)
    models.sort(key=lambda x: x['modified'], reverse=True)
    
    return jsonify(models)

@app.route('/outputs/<path:filename>')
@login_required
def serve_output(filename):
    """Serve output files — only the requesting user's own outputs (or
    staff). Rejects traversal, hidden files and non-model extensions."""
    session_logger.log_action('file_access', {
        'type': 'output',
        'file': filename,
        'user_id': current_user.user_id
    })
    if '..' in Path(filename).parts or filename.startswith(('/', '\\')):
        return jsonify({'error': 'Invalid file path'}), 400
    _resolved = (OUTPUTS_DIR / filename).resolve()
    try:
        _resolved.relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Invalid file path'}), 400
    if _resolved.name.startswith('.') or _resolved.suffix.lower() not in (
            '.obj', '.mtl', '.png', '.jpg', '.jpeg'):
        return jsonify({'error': 'File type not served'}), 403
    if not _resolved.exists():
        return jsonify({'error': 'File not found'}), 404
    if not _user_can_access_output(current_user.user_id, _resolved):
        return jsonify({'error': 'Access denied'}), 403
    return send_from_directory(OUTPUTS_DIR, filename)

@app.route('/assets/<path:filename>')
def serve_asset(filename):
    """Serve asset files."""
    return send_from_directory(PROJECT_ROOT / 'assets', filename)

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS, etc.) from the viewer directory only.
    Stage 3 fix: the old route served ANY file under viewer/ unauthenticated,
    including app.py itself. Now only safe public extensions are served, and
    dotfiles, .py/.db/.md and path traversal are refused."""
    _allowed = {'.html', '.css', '.js', '.mjs', '.map', '.png', '.jpg', '.jpeg',
                '.gif', '.svg', '.ico', '.json', '.woff', '.woff2', '.ttf', '.txt'}
    _p = Path(filename)
    if ('..' in _p.parts or filename.startswith(('/', '\\'))
            or _p.name.startswith('.') or _p.suffix.lower() not in _allowed):
        return "File not found", 404
    file_path = (Path(__file__).parent / filename).resolve()
    try:
        file_path.relative_to(Path(__file__).parent.resolve())
    except ValueError:
        return "File not found", 404
    if file_path.exists() and file_path.is_file():
        return send_from_directory(Path(__file__).parent, filename)
    return "File not found", 404

def _ensure_png(src_path: Path) -> Path:
    """Convert arbitrary image formats to PNG for the pipeline."""
    try:
        from PIL import Image
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass
        img = Image.open(src_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if img.mode.endswith('A') else "RGB")
        out_path = src_path.with_suffix('.png') if src_path.suffix.lower() != '.png' else src_path
        if out_path != src_path:
            img.save(out_path)
            return out_path
        return src_path
    except Exception:
        # Fallback to macOS sips
        try:
            out_path = src_path.with_suffix('.png')
            import subprocess
            subprocess.run(['sips', '-s', 'format', 'png', str(src_path), '--out', str(out_path)], check=True, capture_output=True)
            return out_path
        except Exception:
            return src_path


GENERATION_BACKENDS = ('triposr', 'native')
GENERATION_TEXTURES = ('native', 'none')
# Local remesh (Meshy Remesh equivalent): target face budget and
# output topology. The budget is triangle-equivalent faces, Meshy's
# target_polycount range 100-300,000. Both params are optional --
# a generation without them behaves exactly as before.
REMESH_TOPOLOGIES = ('triangle', 'quad')
REMESH_MIN_TARGET_FACES = 100
REMESH_MAX_TARGET_FACES = 300000

def _run_pipeline(temp_path, backend, filename, texture='native'):
    import subprocess
    if backend not in GENERATION_BACKENDS:
        raise ValueError(f"Unsupported backend: {backend!r} (allowed: {', '.join(GENERATION_BACKENDS)})")
    if texture not in GENERATION_TEXTURES:
        raise ValueError(f"Unsupported texture mode: {texture!r} (allowed: {', '.join(GENERATION_TEXTURES)})")
    session_logger.logger.info(f"Running pipeline for: {temp_path}")
    cmd = [
        sys.executable, '-m', 'src.ai3d.cli', 'pipeline',
        '--image', str(temp_path),
        '--backend', backend,
        '--texture', texture,
        '--outdir', str(OUTPUTS_DIR)
    ]
    session_logger.logger.info(f"CMD: {' '.join(cmd)}")
    # Timeout 1800s, matching the TripoSR runner's own wait(timeout=1800).
    # The old 900s wrapper killed real CPU generations mid-inference:
    # measured 2026-11-10, a TripoSR generation on this Mac CPU ran past
    # 900s (task 53b2d735, execution 900.2s, killed with no mesh). The
    # runner already allows 1800s; the wrapper was the inconsistent cap.
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800
    )

@app.route('/api/generate', methods=['POST'])
@login_required
@limiter.limit("1 per 2 seconds", key_func=get_limiter_key)
def generate_model():
    """Queue a 3D model generation from uploaded image."""
    import uuid
    from werkzeug.utils import secure_filename
    
    # Check quota first
    can_generate, quota_info = user_manager.check_quota(current_user.user_id)
    
    if not can_generate:
        session_logger.log_action('generate_quota_exceeded', {
            'user_id': current_user.user_id,
            'quota': quota_info
        })
        return jsonify({
            'error': 'Weekly quota exceeded',
            'quota': quota_info
        }), 429
    
    session_logger.logger.info(f"=== GENERATE API CALLED ===")
    session_logger.logger.info(f"User: {current_user.email} ({current_user.user_id})")
    session_logger.logger.info(f"Quota remaining: {quota_info['remaining']}")
    session_logger.logger.info(f"Request files: {list(request.files.keys())}")
    session_logger.logger.info(f"Request form: {dict(request.form)}")
    
    if 'image' not in request.files:
        session_logger.logger.error('No image provided in request')
        session_logger.log_action('generate_error', {'error': 'No image provided'})
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    backend = request.form.get('backend', 'triposr')
    texture = request.form.get('texture', 'native')
    if backend not in GENERATION_BACKENDS:
        return jsonify({'error': f"Unsupported backend: {backend!r} (allowed: triposr, native)"}), 400
    if texture not in GENERATION_TEXTURES:
        return jsonify({'error': f"Unsupported texture mode: {texture!r} (allowed: native, none)"}), 400

    # Optional local remesh to a target face budget (Meshy Remesh,
    # local + free). Absent means no remesh -- the generation path
    # is exactly as before. Present but invalid is a 400, so a
    # typo'd budget fails fast instead of silently generating
    # un-remeshed.
    remesh_target_faces = None
    remesh_topology = 'triangle'
    _raw_target = request.form.get('remesh_target_faces')
    if _raw_target:
        try:
            remesh_target_faces = int(_raw_target)
        except (TypeError, ValueError):
            return jsonify({'error': 'remesh_target_faces must be an integer'}), 400
        if remesh_target_faces < REMESH_MIN_TARGET_FACES or remesh_target_faces > REMESH_MAX_TARGET_FACES:
            return jsonify({'error': f'remesh_target_faces must be between {REMESH_MIN_TARGET_FACES} and {REMESH_MAX_TARGET_FACES}'}), 400
        remesh_topology = request.form.get('remesh_topology', 'triangle')
        if remesh_topology not in REMESH_TOPOLOGIES:
            return jsonify({'error': f"Unsupported remesh topology: {remesh_topology!r} (allowed: triangle, quad)"}), 400

    # Optional local GLB export (Meshy export, local + free). Absent
    # means no GLB -- the generation path is exactly as before.
    # Present but invalid is a 400, so a typo'd flag fails fast
    # instead of silently generating without a GLB.
    try:
        export_glb_flag = parse_export_flag(request.form.get('export_glb'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Optional local PBR textures (Meshy PBR texture, local +
    # free). Absent means no textures -- the generation path is
    # exactly as before. Present but invalid is a 400, so a typo'd
    # flag fails fast instead of silently generating untextured.
    try:
        pbr_textures_flag = parse_pbr_flag(request.form.get('pbr_textures'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    session_logger.logger.info(f"Image received: {file.filename}, size: {getattr(file, 'content_length', None)} bytes")
    session_logger.logger.info(f"Backend: {backend}")
    session_logger.logger.info(f"Texture: {texture}")

    # The upload is saved after the task id is created (below), under a
    # name carrying the task id, so two users uploading the same filename
    # never collide or read each other's upload.
    filename = secure_filename(file.filename)
    temp_path = None
    # Create unique task ID
    task_id = str(uuid.uuid4())
    # Unique upload name: task id + filename.
    temp_path = OUTPUTS_DIR / f"temp_{task_id[:8]}_{filename}"
    session_logger.logger.info(f"Saving uploaded file to: {temp_path}")
    file.save(temp_path)
    session_logger.logger.info(f"File saved successfully: {temp_path.stat().st_size} bytes")
    # Normalize to PNG for backend compatibility
    temp_path = _ensure_png(temp_path)
    
    # Add task to queue
    def task_callback(task):
        """Callback when task completes."""
        try:
            if task.status == 'completed':
                socketio.emit('generation_complete', {
                    'task_id': task.task_id,
                    'preview_path': task.result.get('preview_path')
                })
                socketio.emit('models_changed', {})
            elif task.status == 'failed':
                socketio.emit('generation_error', {
                    'task_id': task.task_id,
                    'error': task.error
                })
        except Exception as e:
            session_logger.logger.error(f"Callback error: {e}")
    
    task = task_queue.add_task(
        task_id=task_id,
        task_type='model',
        params={
            'temp_path': str(temp_path),
            'backend': backend,
            'texture': texture,
            'filename': filename,
            'remesh_target_faces': remesh_target_faces,
            'remesh_topology': remesh_topology,
            'export_glb': export_glb_flag,
            'pbr_textures': pbr_textures_flag,
        },
        callback=task_callback
    )
    
    session_logger.log_action('task_queued', {
        'task_id': task_id,
        'filename': filename,
        'backend': backend,
        'user_id': current_user.user_id
    })
    
    # Store user_id and start time in task params for quota and analytics tracking
    task.params['user_id'] = current_user.user_id
    task.params['start_time'] = time.time()
    
    # Log task start for quota tracking
    user_manager.log_task_start(
        user_id=current_user.user_id,
        task_id=task_id,
        task_type='model'
    )
    
    analytics_tracker.log_api_call()  # Track API call
    
    # Emit queued event
    try:
        socketio.emit('generation_queued', {
            'task_id': task_id,
            'filename': filename,
            'backend': backend
        })
    except Exception:
        pass
    
    # Return task status immediately
    status = task_queue.get_task_status(task_id)
    return jsonify({
        'success': True,
        'task_id': task_id,
        'status': status
    })

@app.route('/api/queue/status')
@login_required
def queue_status():
    """Get overall queue status."""
    status = task_queue.get_queue_status()
    return jsonify(status)

@app.route('/api/task/<task_id>/status')
@login_required
def task_status(task_id):
    """Get status for a specific task — only its owner (or staff)."""
    _task = task_queue.tasks.get(task_id) if hasattr(task_queue, 'tasks') else None
    if _task is not None:
        _owner = (_task.params or {}).get('user_id')
        if _owner is not None and int(_owner) != int(current_user.user_id) and not _is_staff(current_user.user_id):
            return jsonify({'error': 'Access denied'}), 403
    status = task_queue.get_task_status(task_id)
    if not status:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(status)

@app.route('/api/task/<task_id>/cancel', methods=['POST'])
@login_required
@limiter.limit("1 per 2 seconds", key_func=lambda: f'user:{current_user.user_id}')
def cancel_task(task_id):
    """Cancel a queued task."""
    success = task_queue.cancel_task(task_id)
    if success:
        return jsonify({'success': True, 'message': 'Task cancelled'})
    return jsonify({'error': 'Cannot cancel task (not queued or not found)'}), 400

@app.route('/api/thumbnail')
@login_required
def get_thumbnail():
    """Thumbnail for a model: the real generated texture.png next to the
    model file when it exists (Stage 3, #12), else the grey placeholder.
    Requires login and ownership of the model."""
    from flask import Response
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <rect fill="#1a1a1a" width="100" height="100"/>
        <text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="#666" font-size="14">3D</text>
    </svg>'''
    model_path = request.args.get('path', '')
    if model_path:
        try:
            _mp = (PROJECT_ROOT / model_path).resolve() if not Path(model_path).is_absolute() else Path(model_path).resolve()
            _mp.relative_to(PROJECT_ROOT.resolve())
            if _mp.suffix.lower() == '.obj' and _mp.exists():
                if not _user_can_access_output(current_user.user_id, _mp):
                    return jsonify({'error': 'Access denied'}), 403
                for _cand in (_mp.with_suffix('.png'),
                              _mp.parent / (_mp.stem + '_albedo.png'),
                              _mp.parent / (_mp.stem.replace('_preview', '') + '_refined_albedo.png'),
                              _mp.parent / (_mp.stem.replace('_preview', '') + '_refined.png'),
                              _mp.parent / (_mp.stem.replace('_preview', '') + '.png')):
                    if _cand.exists() and _cand.stat().st_size > 0:
                        return send_file(str(_cand), mimetype='image/png')
        except Exception:
            pass
    return Response(svg, mimetype='image/svg+xml')

@app.route('/api/screenshot/cooldown')
@login_required
def get_screenshot_cooldown():
    """Get remaining cooldown time for screenshot."""
    try:
        # Check rate limit status without incrementing counter
        identifier = f'user:{current_user.user_id}'
        endpoint = 'api_screenshot'
        
        conn = sqlite3.connect(security_manager.db_path)
        cursor = conn.cursor()
        
        now = time.time()
        window_start = now - 60  # 1 minute window
        
        # Check if currently blocked
        cursor.execute('''
        SELECT blocked_until FROM rate_limits
        WHERE identifier = ? AND endpoint = ? AND blocked_until > ?
        ''', (identifier, endpoint, now))
        
        blocked = cursor.fetchone()
        if blocked:
            remaining = int(blocked[0] - now)
            conn.close()
            return jsonify({
                'on_cooldown': True,
                'remaining_seconds': remaining
            })
        
        # Check recent requests
        cursor.execute('''
        SELECT window_start, request_count FROM rate_limits
        WHERE identifier = ? AND endpoint = ? AND window_start > ?
        ''', (identifier, endpoint, window_start))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[1] >= 1:
            # Calculate remaining time
            last_request_time = result[0]
            elapsed = now - last_request_time
            remaining = max(0, int(60 - elapsed))
            
            return jsonify({
                'on_cooldown': remaining > 0,
                'remaining_seconds': remaining
            })
        
        return jsonify({
            'on_cooldown': False,
            'remaining_seconds': 0
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/screenshot', methods=['POST'])
@login_required
@limiter.limit("1 per minute", key_func=get_limiter_key)
def save_screenshot():
    """Save a screenshot from the viewer to user gallery."""
    try:
        data = request.get_json()
        
        if 'image' not in data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Extract base64 image data
        import base64
        image_data = data['image']
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{timestamp}.png'
        filepath = SCREENSHOTS_DIR / filename
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(image_data))
        
        session_logger.log_action('screenshot', {
            'filename': filename,
            'size': filepath.stat().st_size,
            'user_id': current_user.user_id
        })
        
        analytics_tracker.log_screenshot()  # Track screenshot
        
        # Save to user gallery
        user_manager.add_to_gallery(
            user_id=current_user.user_id,
            image_type='screenshot',
            file_path=str(filepath.relative_to(PROJECT_ROOT))
        )
        
        # Track screenshot in analytics
        if hasattr(g, 'visitor_id'):
            visitor_tracker.log_action(g.visitor_id, 'screenshot', {
                'filename': filename,
                'user_id': current_user.user_id
            })
        
        return jsonify({
            'success': True,
            'filename': filename,
            'path': str(filepath.relative_to(PROJECT_ROOT)),
            'cooldown': 60  # 60 seconds cooldown
        })
        
    except Exception as e:
        session_logger.log_action('screenshot_error', {'error': str(e)})
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/gallery')
@login_required
def get_user_gallery():
    """Get user's gallery images."""
    try:
        gallery = user_manager.get_user_gallery(current_user.user_id)
        return jsonify(gallery)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/log', methods=['POST'])
@login_required
def log_action():
    """Log a user action from the frontend."""
    try:
        data = request.get_json()
        action_type = data.get('type', 'unknown')
        details = data.get('details', {})
        details['user_id'] = current_user.user_id
        
        log_entry = session_logger.log_action(action_type, details)
        
        return jsonify({
            'success': True,
            'log_entry': log_entry
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs')
@login_required
def get_logs():
    """Get recent log entries — staff only (Stage 3, #9)."""
    if not _is_staff(current_user.user_id):
        return jsonify({'error': 'Access denied'}), 403
    try:
        limit = int(request.args.get('limit', 100))
        
        logs = []
        log_file = LOGS_DIR / 'viewer.log'
        
        if log_file.exists():
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Get last N lines
                for line in lines[-limit:]:
                    # Try to parse JSON log entries
                    try:
                        if '{' in line and '}' in line:
                            json_str = line[line.index('{'):line.rindex('}')+1]
                            logs.append(json.loads(json_str))
                    except:
                        pass
        
        return jsonify(logs)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics')
@login_required
def get_analytics():
    """Get visitor analytics and statistics."""
    try:
        days = int(request.args.get('days', 7))
        stats = visitor_tracker.get_stats(days=days)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/visitor/history')
@login_required
def get_visitor_history():
    """Get current visitor's request history."""
    try:
        if hasattr(g, 'visitor_ip'):
            history = visitor_tracker.get_visitor_history(g.visitor_ip)
            if history:
                return jsonify(history)
            else:
                return jsonify({'message': 'No history found'})
        return jsonify({'error': 'Unable to determine visitor'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/monthly')
@login_required
def get_monthly_analytics():
    """Get current month analytics summary."""
    try:
        stats = analytics_tracker.get_current_month_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== ISSUE TRACKING ENDPOINTS ==========

@app.route('/issues')
@login_required
def issues_page():
    """Community issues board page."""
    return send_file('issues.html')

@app.route('/api/issues', methods=['GET'])
@login_required
def get_issues():
    """Get all issues with optional status filter."""
    try:
        status_filter = request.args.get('status')  # None, 'open', 'fixed', 'ignored'
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        if status_filter and status_filter not in ['open', 'fixed', 'ignored']:
            return jsonify({'error': 'Invalid status filter'}), 400
        
        issues = issue_manager.get_all_issues(
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        # Add is_admin flag for current user
        is_admin = issue_manager.is_admin(current_user.user_id)
        
        return jsonify({
            'success': True,
            'issues': issues,
            'is_admin': is_admin,
            'count': len(issues)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues/recent', methods=['GET'])
@login_required
def get_recent_issues():
    """Get issues from the last 7 days."""
    try:
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))
        
        issues = issue_manager.get_recent_issues(days=days, limit=limit)
        is_admin = issue_manager.is_admin(current_user.user_id)
        
        return jsonify({
            'success': True,
            'issues': issues,
            'is_admin': is_admin,
            'count': len(issues)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues/stats', methods=['GET'])
@login_required
def get_issue_stats():
    """Get issue statistics."""
    try:
        stats = issue_manager.get_issue_stats()
        is_admin = issue_manager.is_admin(current_user.user_id)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'is_admin': is_admin
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues/<int:issue_id>', methods=['GET'])
@login_required
def get_issue(issue_id):
    """Get a single issue with comments."""
    try:
        issue = issue_manager.get_issue_by_id(issue_id)
        
        if not issue:
            return jsonify({'error': 'Issue not found'}), 404
        
        is_admin = issue_manager.is_admin(current_user.user_id)
        
        return jsonify({
            'success': True,
            'issue': issue,
            'is_admin': is_admin
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues', methods=['POST'])
@login_required
def create_issue():
    """Create a new issue."""
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        
        if not title or not description:
            return jsonify({'error': 'Title and description are required'}), 400
        
        if len(title) < 5:
            return jsonify({'error': 'Title must be at least 5 characters'}), 400
        
        if len(description) < 10:
            return jsonify({'error': 'Description must be at least 10 characters'}), 400
        
        issue_id = issue_manager.create_issue(
            user_id=current_user.user_id,
            user_name=current_user.name,
            user_email=current_user.email,
            title=title,
            description=description
        )
        
        session_logger.log_action('issue_created', {
            'issue_id': issue_id,
            'user_id': current_user.user_id,
            'title': title
        })
        
        return jsonify({
            'success': True,
            'issue_id': issue_id,
            'message': 'Issue created successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues/<int:issue_id>/comments', methods=['POST'])
@login_required
def add_issue_comment(issue_id):
    """Add a comment to an issue."""
    try:
        data = request.get_json()
        comment = data.get('comment', '').strip()
        
        if not comment:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        if len(comment) < 3:
            return jsonify({'error': 'Comment must be at least 3 characters'}), 400
        
        comment_id = issue_manager.add_comment(
            issue_id=issue_id,
            user_id=current_user.user_id,
            user_name=current_user.name,
            comment=comment
        )
        
        return jsonify({
            'success': True,
            'comment_id': comment_id,
            'message': 'Comment added'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issues/<int:issue_id>/status', methods=['PUT'])
@login_required
def update_issue_status(issue_id):
    """Update issue status (admin only)."""
    try:
        # Check if user is admin
        if not issue_manager.is_admin(current_user.user_id):
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        status = data.get('status')
        resolution_note = data.get('resolution_note', '').strip()
        
        if status not in ['open', 'fixed', 'ignored']:
            return jsonify({'error': 'Invalid status'}), 400
        
        # Require resolution note for fixed/ignored status
        if status in ['fixed', 'ignored'] and not resolution_note:
            return jsonify({'error': 'Resolution note required when marking as fixed/ignored'}), 400
        
        if status in ['fixed', 'ignored'] and len(resolution_note) < 5:
            return jsonify({'error': 'Resolution note must be at least 5 characters'}), 400
        
        success = issue_manager.update_issue_status(
            issue_id=issue_id,
            status=status,
            admin_user_id=current_user.user_id,
            resolution_note=resolution_note if status in ['fixed', 'ignored'] else None
        )
        
        if not success:
            return jsonify({'error': 'Failed to update issue'}), 500
        
        session_logger.log_action('issue_status_updated', {
            'issue_id': issue_id,
            'admin_user_id': current_user.user_id,
            'status': status
        })
        
        return jsonify({
            'success': True,
            'message': f'Issue marked as {status}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== CRYPTO PAYMENT ENDPOINTS ==========

@app.route('/crypto-payment')
@login_required
def crypto_payment_page():
    """Crypto payment page."""
    return send_file('crypto_payment.html')

@app.route('/api/crypto/prices')
def get_crypto_prices():
    """Get current BTC and ETH prices."""
    try:
        prices = crypto_manager.get_prices()
        return jsonify({
            'success': True,
            'prices': prices,
            'last_update': crypto_manager.last_price_update.isoformat() if crypto_manager.last_price_update else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto/create-payment', methods=['POST'])
@login_required
def create_crypto_payment():
    """Create a new crypto payment session."""
    try:
        data = request.get_json()
        payment_type = data.get('payment_type')  # 'refill', 'standard_yearly', etc.
        crypto_type = data.get('crypto_type', 'btc')  # 'btc' or 'eth'
        
        if not payment_type:
            return jsonify({'success': False, 'error': 'payment_type required'}), 400
        
        if crypto_type not in ['btc', 'eth']:
            return jsonify({'success': False, 'error': 'Invalid crypto_type'}), 400
        
        session_data = crypto_manager.create_payment_session(
            user_id=current_user.user_id,
            payment_type=payment_type,
            crypto_type=crypto_type
        )
        
        session_data['success'] = True
        return jsonify(session_data)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto/verify-payment', methods=['POST'])
@login_required
def verify_crypto_payment():
    """Verify a blockchain transaction."""
    try:
        data = request.get_json()
        payment_id = data.get('payment_id')
        txid = data.get('txid')
        sender_address = data.get('sender_address')
        
        if not all([payment_id, txid, sender_address]):
            return jsonify({
                'success': False,
                'error': 'payment_id, txid, and sender_address required'
            }), 400
        
        result = crypto_manager.verify_transaction(
            payment_id=int(payment_id),
            txid=txid,
            sender_address=sender_address
        )
        
        # If payment complete, activate subscription/refill
        if result.get('success') and result.get('payment_complete'):
            payment_status = crypto_manager.get_payment_status(int(payment_id))
            conn = user_manager._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT user_id, payment_type FROM crypto_payments WHERE payment_id = ?',
                (payment_id,)
            )
            user_id, payment_type = cursor.fetchone()
            conn.close()
            
            # Activate based on payment type
            if payment_type == 'refill':
                user_manager.purchase_refill(user_id)
            elif 'standard' in payment_type:
                user_manager.update_subscription(user_id, 'standard', 'yearly' in payment_type)
            elif 'pro' in payment_type:
                user_manager.update_subscription(user_id, 'pro', 'yearly' in payment_type)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto/payment-status/<int:payment_id>')
@login_required
def get_payment_status(payment_id):
    """Get status of a payment."""
    try:
        status = crypto_manager.get_payment_status(payment_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crypto/payment-history')
@login_required
def get_crypto_payment_history():
    """Get user's crypto payment history."""
    try:
        history = crypto_manager.get_user_payment_history(current_user.user_id)
        return jsonify({
            'success': True,
            'payments': history
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== STRIPE CHECKOUT & WEBHOOK ====================
# Card payments via Stripe Checkout (test mode until Gary connects Stripe
# and creates the products). The crypto flow (BTC/ETH) is untouched and
# stays available alongside Stripe — see /crypto-payment.

@app.route('/api/stripe/config', methods=['GET'])
def stripe_config():
    """Return whether Stripe is configured + the publishable key.

    The publishable key is public by design (Stripe's own docs embed it
    in the frontend). No login required — the pricing page calls this
    before showing the Stripe buttons.
    """
    return jsonify({
        'configured': stripe_manager.is_configured(),
        'publishable_key': stripe_manager.publishable_key or None
    })


@app.route('/api/stripe/create-checkout-session', methods=['POST'])
@login_required
def stripe_create_checkout_session():
    """Create a Stripe Checkout session for a plan or a refill.

    Body: {"plan": "standard_weekly" | "standard_yearly" | "pro_weekly"
                 | "pro_yearly" | "refill"}.
    Returns {"success": true, "url": <checkout url>, "session_id": ...};
    the frontend redirects the user to the URL (no Stripe.js needed).
    503 when Stripe is not configured or the plan has no Price ID yet.
    """
    try:
        data = request.get_json(silent=True) or {}
        plan = (data.get('plan') or '').strip()
        if plan not in STRIPE_PLANS:
            return jsonify({'success': False, 'error': f'Unknown plan: {plan}'}), 400
        if not stripe_manager.is_configured():
            return jsonify({
                'success': False,
                'error': 'Stripe is not configured yet. Card payments open once Stripe is connected — meanwhile you can pay with BTC or ETH.'
            }), 503
        price_id = stripe_manager.get_price_id(plan)
        if not price_id:
            return jsonify({
                'success': False,
                'error': f'This plan has no Stripe Price ID yet ({STRIPE_PLANS[plan]["price_env"]}). It will be available once the product is created in Stripe.'
            }), 503
        base = request.url_root.rstrip('/')
        success_url = base + '/pricing?checkout=success&session_id={CHECKOUT_SESSION_ID}'
        cancel_url = base + '/pricing?checkout=cancelled'
        session = stripe_manager.create_checkout_session(
            current_user.user_id, plan, success_url, cancel_url
        )
        return jsonify({'success': True, 'url': session['url'], 'session_id': session['session_id']})
    except Exception as e:
        session_logger.logger.error(f'Stripe checkout session error: {str(e)}')
        return jsonify({'success': False, 'error': f'Could not start checkout: {str(e)}'}), 502


@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe webhook endpoint (called by Stripe, not by the user).

    Verifies the signature with STRIPE_WEBHOOK_SECRET and fails CLOSED
    (503) when Stripe is not configured — an unverified webhook is never
    processed. Verified events are applied idempotently (see
    handle_webhook_event); a verified event always returns 200 so Stripe
    stops retrying, and a handler failure returns 500 so it retries.
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    if not stripe_manager.is_configured() or not stripe_manager.webhook_secret:
        return jsonify({'error': 'Stripe is not configured'}), 503
    try:
        event = stripe_manager.construct_webhook_event(payload, sig_header)
    except StripeWebhookError as e:
        session_logger.logger.warning(f'Stripe webhook rejected: {str(e)}')
        return jsonify({'error': f'Webhook verification failed: {str(e)}'}), 400
    except Exception as e:
        session_logger.logger.warning(f'Stripe webhook error: {str(e)}')
        return jsonify({'error': f'Webhook verification failed: {str(e)}'}), 400
    try:
        status = handle_webhook_event(event, user_manager, stripe_manager,
                                      log=session_logger.logger)
    except Exception as e:
        session_logger.logger.error(f'Stripe webhook handler error: {str(e)}')
        return jsonify({'error': 'Webhook handler failed'}), 500
    return jsonify({'received': True, 'status': status}), 200

# ========== FAVORITES ENDPOINTS ==========

@app.route('/api/favorites/add', methods=['POST'])
@login_required
@limiter.limit("30 per minute", key_func=get_limiter_key)
def add_favorite():
    """Add model to favorites."""
    try:
        data = request.get_json()
        model_path = data.get('model_path', '').strip()
        
        if not model_path:
            return jsonify({'success': False, 'message': 'Model path required'}), 400
        
        # Validate path
        is_valid, reason = security_manager.validate_input(model_path, 'path')
        if not is_valid:
            return jsonify({'success': False, 'message': 'Invalid model path'}), 400
        
        result = favorites_manager.add_favorite(current_user.user_id, model_path)
        return jsonify(result)
        
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

@app.route('/api/favorites/remove', methods=['POST'])
@login_required
@limiter.limit("30 per minute", key_func=get_limiter_key)
def remove_favorite():
    """Remove model from favorites (restarts deletion timer)."""
    try:
        data = request.get_json()
        model_path = data.get('model_path', '').strip()
        
        if not model_path:
            return jsonify({'success': False, 'message': 'Model path required'}), 400
        
        result = favorites_manager.remove_favorite(current_user.user_id, model_path)
        return jsonify(result)
        
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

@app.route('/api/favorites/list')
@login_required
def get_favorites():
    """Get user's favorites list."""
    try:
        favorites = favorites_manager.get_favorites(current_user.user_id)
        return jsonify({
            'success': True,
            'favorites': favorites,
            'count': len(favorites),
            'max_favorites': favorites_manager.MAX_FAVORITES
        })
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

@app.route('/api/models/recent')
@login_required
def get_recent_models():
    """Get recent models with favorite status and time remaining."""
    try:
        limit = int(request.args.get('limit', 20))
        models = favorites_manager.get_recent_models(current_user.user_id, limit=limit)
        return jsonify({
            'success': True,
            'models': models,
            'count': len(models),
            'cleanup_hours': favorites_manager.CLEANUP_HOURS
        })
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

@app.route('/api/favorites/stats')
@login_required
def get_favorites_stats():
    """Get user's storage statistics."""
    try:
        stats = favorites_manager.get_user_storage_stats(current_user.user_id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

# ========== ERROR HANDLERS ==========

def get_attempted_action(path, endpoint, method):
    """Determine what the user was trying to do based on the request path and endpoint."""
    # Map paths to user-friendly action descriptions
    action_map = {
        '/': 'Access the home page (sign-up/login)',
        '/viewer': 'Open the 3D modeller viewer',
        '/pricing': 'View pricing and subscription plans',
        '/docs': 'View documentation',
        '/docs/api': 'View API reference',
        '/docs/terms': 'View Terms of Service',
        '/docs/privacy': 'View Privacy Policy',
        '/donate': 'Access the donation page',
        '/maintenance': 'View maintenance status',
        '/auth/login': 'Sign in with Google',
        '/auth/callback': 'Complete Google authentication',
        '/auth/logout': 'Sign out of your account',
        '/api/user/profile': 'Load your user profile',
        '/api/user/gallery': 'Load your screenshot gallery',
        '/api/user/activity': 'Load your activity history',
        '/api/user/activity/stats': 'Load activity statistics',
        '/api/user/activity/recent': 'Load recent activity events',
        '/api/generate': 'Generate a 3D model from an image',
        '/api/screenshot': 'Save a screenshot',
        '/api/models': 'List generated 3D models',
        '/api/models/recent': 'Load recent models',
        '/api/queue/status': 'Check the generation queue status',
        '/api/health': 'Check API health status',
        '/api/capacity': 'Check server capacity',
        '/api/check-username': 'Check username availability',
        '/api/favorites/add': 'Add a model to favorites',
        '/api/favorites/remove': 'Remove a model from favorites',
        '/api/favorites/list': 'View your favorites list',
        '/api/favorites/stats': 'View storage statistics',
        '/api/issues/submit': 'Submit a bug report or feature request',
        '/api/issues/list': 'View reported issues',
        '/api/crypto/addresses': 'View cryptocurrency payment addresses',
        '/api/crypto/payment/verify': 'Verify cryptocurrency payment',
    }
    
    # Check exact path match first
    if path in action_map:
        return action_map[path]
    
    # Check for dynamic paths
    if path.startswith('/api/task/'):
        if 'status' in path:
            return 'Check the status of a model generation task'
        elif 'cancel' in path:
            return 'Cancel a model generation task'
    
    if path.startswith('/outputs/'):
        return 'Download a generated 3D model file'
    
    if path.startswith('/api/model/'):
        return 'Access a specific 3D model'
    
    # Fallback based on method and path pattern
    if path.startswith('/api/'):
        if method == 'POST':
            return f'Submit data to the API ({path})'
        elif method == 'GET':
            return f'Retrieve data from the API ({path})'
        elif method == 'DELETE':
            return f'Delete data via the API ({path})'
        elif method == 'PUT' or method == 'PATCH':
            return f'Update data via the API ({path})'
    
    # Generic fallback
    if endpoint:
        return f'Access the {endpoint.replace("_", " ")} page'
    
    return f'Access {path}'

def render_error_page(title, message, code, icon="❌", suspected_reason=None, attempted_action=None):
    """Render a nice HTML error page."""
    
    # Add attempted action section if provided
    attempted_action_html = ''
    if attempted_action:
        attempted_action_html = f'''
            <div style="margin: 20px 0; padding: 16px; background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); border-radius: 12px;">
                <div style="font-size: 14px; color: #fb923c; font-weight: 600; margin-bottom: 8px;">🎯 What You Were Trying To Do</div>
                <div style="font-size: 14px; color: rgba(255, 255, 255, 0.85); line-height: 1.6;">{attempted_action}</div>
            </div>
        '''
    
    suspected_reason_html = ''
    if suspected_reason:
        suspected_reason_html = f'''
            <div style="margin: 20px 0; padding: 16px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px;">
                <div style="font-size: 14px; color: #60a5fa; font-weight: 600; margin-bottom: 8px;">💡 Suspected Reason</div>
                <div style="font-size: 14px; color: rgba(255, 255, 255, 0.85); line-height: 1.6;">{suspected_reason}</div>
            </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - SlushAI 3D Modeller</title>
        <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
                color: #fff;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                max-width: 650px;
                text-align: center;
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                padding: 60px 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }}
            .icon {{
                font-size: 80px;
                margin-bottom: 24px;
                animation: pulse 2s ease-in-out infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.1); }}
            }}
            h1 {{
                font-size: 36px;
                font-weight: 700;
                margin-bottom: 16px;
                background: linear-gradient(135deg, #f43f5e, #f97316);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .error-code {{
                font-size: 20px;
                color: #fbbf24;
                margin-bottom: 20px;
                font-weight: 600;
            }}
            .message {{
                font-size: 16px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.8);
                margin-bottom: 20px;
            }}
            .actions {{
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
            }}
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 14px 24px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                font-size: 14px;
                transition: all 0.2s;
                cursor: pointer;
                border: none;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #f43f5e, #f97316);
                color: white;
            }}
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(249, 115, 22, 0.4);
            }}
            .btn-secondary {{
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{icon}</div>
            <h1>{title}</h1>
            <div class="error-code">Error {code}</div>
            <div class="message">{message}</div>
            {attempted_action_html}
            {suspected_reason_html}
            <div class="actions">
                <button class="btn btn-primary" onclick="window.history.back()">← Go Back</button>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
                <a href="/docs" class="btn btn-secondary">📚 Docs</a>
            </div>
        </div>
    </body>
    </html>
    ''', code

@app.errorhandler(Exception)
def handle_exception(e):
    """Global error handler with sanitized messages."""
    # Stage 3 fix: HTTPExceptions (404/405/...) carry their own status and
    # must keep it. The old code caught them here too and returned 500 for
    # everything — a POST to a removed route answered 500 instead of 405,
    # which hid the real status and looked like a server error.
    if isinstance(e, HTTPException):
        return e
    # Log the real error with comprehensive context
    error_log = {
        'timestamp': datetime.now().isoformat(),
        'event': 'unhandled_exception',
        'error': str(e),
        'type': type(e).__name__,
        'path': request.path,
        'method': request.method,
        'endpoint': request.endpoint,
        'ip': get_remote_address()
    }
    # Safely check for authenticated user without triggering load_user errors
    try:
        if current_user.is_authenticated:
            try:
                error_log['user_id'] = current_user.user_id
            except:
                pass
    except:
        # Avoid recursive errors if current_user access fails
        pass
    
    session_logger.logger.error(f"EXCEPTION: {json.dumps(error_log)}")
    
    # Sanitize error for user
    sanitized_error = security_manager.sanitize_error_message(str(e))
    
    # Determine what the user was trying to do based on the path and endpoint
    attempted_action = get_attempted_action(request.path, request.endpoint, request.method)
    
    # Check if this is an API request or browser request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'error': 'An error occurred',
            'message': sanitized_error,
            'attempted_action': attempted_action
        }), 500
    
    # Determine suspected reason
    suspected_reason = None
    error_str = str(e).lower()
    if 'database' in error_str or 'sqlite' in error_str:
        suspected_reason = "Database connection issue. The server may be experiencing high load."
    elif 'timeout' in error_str:
        suspected_reason = "Request timeout. The operation took too long to complete."
    elif 'memory' in error_str:
        suspected_reason = "Server memory issue. Try again in a few moments."
    elif 'permission' in error_str or 'access' in error_str:
        suspected_reason = "File permission issue. This has been logged for the admin to review."
    else:
        suspected_reason = "An unexpected server error occurred. This has been logged and will be investigated."
    
    return render_error_page(
        title="Something Went Wrong",
        message=f"We encountered an unexpected error: {sanitized_error}",
        code=500,
        icon="🚫",
        suspected_reason=suspected_reason,
        attempted_action=attempted_action
    )

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    # Check if this is an API request or browser request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({'error': 'Not found'}), 404
    
    return render_error_page(
        title="Page Not Found",
        message="The page you're looking for doesn't exist. It might have been moved or deleted.",
        code=404,
        icon="🔍"
    )

@app.errorhandler(403)
def forbidden(e):
    """Handle 403 errors."""
    # Check if this is an API request or browser request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({'error': 'Access denied'}), 403
    
    return render_error_page(
        title="Access Denied",
        message="You don't have permission to access this resource. Please log in or contact support if you believe this is an error.",
        code=403,
        icon="🚫"
    )

@app.errorhandler(429)
def rate_limit_exceeded_error(e):
    """Handle rate limit errors - delegates to comprehensive handler."""
    return rate_limit_exceeded_handler(e)

# ========== USER ACTIVITY LOG ENDPOINTS ==========

@app.route('/api/user/activity')
@login_required
@limiter.limit("30 per minute")  # 1-second delay between requests
def get_user_activity():
    """Get recent activity for current user."""
    try:
        # Add 1-second delay for rate limiting compliance
        time.sleep(1)
        
        limit = min(int(request.args.get('limit', 100)), 500)  # Max 500 events
        event_type = request.args.get('type', None)  # Optional filter
        
        # Get activity from logger
        activity = activity_logger.get_user_activity(
            user_id=current_user.user_id,
            limit=limit,
            event_type=event_type
        )
        
        # Get summary stats
        stats = activity_logger.get_activity_stats(
            user_id=current_user.user_id,
            days=30
        )
        
        return jsonify({
            'success': True,
            'activity': activity,
            'stats': stats,
            'count': len(activity)
        })
        
    except Exception as e:
        session_logger.logger.error(f"Failed to fetch user activity: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve activity log'
        }), 500

@app.route('/api/user/activity/stats')
@login_required
@limiter.limit("30 per minute")  # 1-second delay between requests
def get_activity_stats():
    """Get activity statistics summary for current user."""
    try:
        # Add 1-second delay for rate limiting compliance
        time.sleep(1)
        
        days = min(int(request.args.get('days', 30)), 365)  # Max 1 year
        
        stats = activity_logger.get_activity_stats(
            user_id=current_user.user_id,
            days=days
        )
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        session_logger.logger.error(f"Failed to fetch activity stats: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve statistics'
        }), 500

@app.route('/api/user/activity/recent')
@login_required
@limiter.limit("30 per minute")  # 1-second delay between requests
def get_recent_activity():
    """Get recent events of specific types for current user."""
    try:
        # Add 1-second delay for rate limiting compliance
        time.sleep(1)
        
        # Get event types from query params (comma-separated)
        event_types_str = request.args.get('types', 'generation_completed,model_saved,model_favorited')
        event_types = [t.strip() for t in event_types_str.split(',')]
        limit = min(int(request.args.get('limit', 20)), 100)
        
        events = activity_logger.get_recent_events(
            user_id=current_user.user_id,
            event_types=event_types,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'events': events,
            'count': len(events)
        })
        
    except Exception as e:
        session_logger.logger.error(f"Failed to fetch recent events: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve events'
        }), 500

# ========== SECURITY MONITORING ENDPOINTS ==========

@app.route('/api/security/stats')
@login_required
@limiter.limit("30 per minute")  # 1-second delay between requests
def get_security_stats():
    """Get attack statistics (admin or user's own stats)."""
    try:
        # Add 1-second delay for rate limiting compliance
        time.sleep(1)
        days = int(request.args.get('days', 30))
        stats = security_manager.get_attack_stats(days=days)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

@app.route('/api/security/recent-attacks')
@login_required
@limiter.limit("30 per minute")  # 1-second delay between requests
def get_recent_attacks():
    """Get recent attack attempts (admin only)."""
    try:
        # Add 1-second delay for rate limiting compliance
        time.sleep(1)
        # Check if user is admin (using issue_manager as proxy for admin check)
        if not issue_manager.is_admin(current_user.user_id):
            return jsonify({'error': 'Admin access required'}), 403
        
        limit = int(request.args.get('limit', 100))
        
        conn = sqlite3.connect(security_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT ip_address, attack_type, endpoint, timestamp
        FROM attack_log
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (limit,))
        
        attacks = [
            {
                'ip': row[0],
                'type': row[1],
                'endpoint': row[2],
                'timestamp': row[3]
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'attacks': attacks,
            'count': len(attacks)
        })
        
    except Exception as e:
        sanitized_error = security_manager.sanitize_error_message(str(e))
        return jsonify({'success': False, 'message': sanitized_error}), 500

# NOTE (Stage 3, #8): the /admin/api/* dev endpoints were removed here.
# They were live, key-gated only, and create-account accepted an
# unvalidated tier (anyone with the key could create a founder).
# Staff user listing lives at /api/admin/users/list (login + staff tier).

def cleanup_old_servers():
    """Kill older instances of the server, keeping only the newest one."""
    import subprocess
    import signal
    
    try:
        # Get all python processes running app.py
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        
        # Find all app.py processes
        app_processes = []
        for line in result.stdout.split('\n'):
            if 'python' in line and 'app.py' in line and 'grep' not in line:
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pid = int(parts[1])
                        # Get process start time (column 8 in ps aux)
                        start_time = parts[8] if len(parts) > 8 else ''
                        app_processes.append((pid, start_time, line))
                    except (ValueError, IndexError):
                        continue
        
        # Get current process PID
        current_pid = os.getpid()
        
        # Filter out current process and sort by start time (oldest first)
        other_processes = [(pid, time, line) for pid, time, line in app_processes if pid != current_pid]
        
        if other_processes:
            print(f"\n⚠️  Found {len(other_processes)} other server instance(s) running")
            print(f"🔄 Killing older instances (keeping PID {current_pid})...\n")
            
            for pid, start_time, line in other_processes:
                try:
                    print(f"   Terminating PID {pid} (started at {start_time})")
                    os.kill(pid, signal.SIGKILL)  # Force kill to ensure cleanup
                    time.sleep(0.3)  # Brief wait to ensure termination
                except ProcessLookupError:
                    print(f"   PID {pid} already terminated")
                except PermissionError:
                    print(f"   ⚠️  Permission denied for PID {pid} (may need sudo)")
                except Exception as e:
                    print(f"   ⚠️  Failed to kill PID {pid}: {e}")
            
            print(f"\n✅ Cleanup complete - this is now the only running server (PID {current_pid})\n")
        else:
            print(f"\n✅ No other server instances detected (PID {current_pid})\n")
            
    except Exception as e:
        print(f"\n⚠️  Error during server cleanup: {e}")
        print("Continuing with server startup...\n")

if __name__ == '__main__':
    # Kill any older server instances before starting
    cleanup_old_servers()
    
    print("="*60)
    print("🎨 AI3DModeller Web Viewer")
    print("="*60)
    print(f"Server: http://localhost:{PORT}")
    print(f"Models: {OUTPUTS_DIR}")
    print(f"Mode: Production (low resource usage)")
    print("="*60 + "\n")
    
    # Production mode: no debug, no reloader, single-threaded, minimal overhead
    # use_reloader=False prevents the watchdog process
    # Run Socket.IO server (threading mode)
    # Localhost only: never expose the server on the LAN or beyond.
    socketio.run(
        app,
        debug=False,
        host='127.0.0.1',
        port=PORT,
        allow_unsafe_werkzeug=True
    )
