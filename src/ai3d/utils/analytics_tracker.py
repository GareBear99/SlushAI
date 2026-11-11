"""Monthly analytics tracking for SlushAI 3D Modeller.

Tracks site traffic, processing times, worker usage, and generates monthly reports.
Automatically truncates old months to keep file size manageable.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class AnalyticsTracker:
    """Tracks and aggregates monthly analytics data."""
    
    def __init__(self, db_path: str, log_path: str):
        self.db_path = Path(db_path)
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize analytics database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Daily aggregated stats
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                visits INTEGER DEFAULT 0,
                unique_visitors INTEGER DEFAULT 0,
                models_generated INTEGER DEFAULT 0,
                models_failed INTEGER DEFAULT 0,
                avg_processing_time REAL DEFAULT 0,
                total_processing_time REAL DEFAULT 0,
                min_processing_time REAL DEFAULT 0,
                max_processing_time REAL DEFAULT 0,
                screenshots_taken INTEGER DEFAULT 0,
                third_worker_activations INTEGER DEFAULT 0,
                third_worker_total_seconds REAL DEFAULT 0,
                api_calls INTEGER DEFAULT 0,
                rate_limit_hits INTEGER DEFAULT 0,
                maintenance_mode_activations INTEGER DEFAULT 0
            )
        ''')
        
        # Monthly summary stats
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monthly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                total_visits INTEGER DEFAULT 0,
                unique_visitors INTEGER DEFAULT 0,
                total_models_generated INTEGER DEFAULT 0,
                total_models_failed INTEGER DEFAULT 0,
                avg_processing_time REAL DEFAULT 0,
                fastest_processing_time REAL DEFAULT 0,
                slowest_processing_time REAL DEFAULT 0,
                total_screenshots INTEGER DEFAULT 0,
                third_worker_activations INTEGER DEFAULT 0,
                third_worker_total_hours REAL DEFAULT 0,
                avg_third_worker_duration REAL DEFAULT 0,
                total_api_calls INTEGER DEFAULT 0,
                total_rate_limit_hits INTEGER DEFAULT 0,
                total_maintenance_activations INTEGER DEFAULT 0,
                peak_concurrent_users INTEGER DEFAULT 0,
                busiest_day TEXT,
                busiest_hour INTEGER DEFAULT 0,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(year, month)
            )
        ''')
        
        # Real-time tracking (for current day aggregation)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS realtime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_visit(self, visitor_ip: str):
        """Log a site visit."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, visits, unique_visitors)
            VALUES (?, 1, 1)
            ON CONFLICT(date) DO UPDATE SET
                visits = visits + 1
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def log_model_generation(self, processing_time: float, success: bool):
        """Log a model generation attempt."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get current stats for this day
        cursor.execute('SELECT models_generated, avg_processing_time, min_processing_time, max_processing_time FROM daily_stats WHERE date = ?', (today,))
        row = cursor.fetchone()
        
        if row:
            count, avg, min_time, max_time = row
            # Update averages
            new_avg = ((avg * count) + processing_time) / (count + 1) if count > 0 else processing_time
            new_min = min(min_time, processing_time) if min_time > 0 else processing_time
            new_max = max(max_time, processing_time)
        else:
            new_avg = processing_time
            new_min = processing_time
            new_max = processing_time
        
        if success:
            cursor.execute('''
                INSERT INTO daily_stats (date, models_generated, avg_processing_time, total_processing_time, min_processing_time, max_processing_time)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    models_generated = models_generated + 1,
                    avg_processing_time = ?,
                    total_processing_time = total_processing_time + ?,
                    min_processing_time = ?,
                    max_processing_time = ?
            ''', (today, new_avg, processing_time, new_min, new_max, new_avg, processing_time, new_min, new_max))
        else:
            cursor.execute('''
                INSERT INTO daily_stats (date, models_failed)
                VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    models_failed = models_failed + 1
            ''', (today,))
        
        conn.commit()
        conn.close()
    
    def log_third_worker_activation(self, duration_seconds: float):
        """Log when 3rd worker activates and how long it ran."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, third_worker_activations, third_worker_total_seconds)
            VALUES (?, 1, ?)
            ON CONFLICT(date) DO UPDATE SET
                third_worker_activations = third_worker_activations + 1,
                third_worker_total_seconds = third_worker_total_seconds + ?
        ''', (today, duration_seconds, duration_seconds))
        
        conn.commit()
        conn.close()
    
    def log_screenshot(self):
        """Log a screenshot taken."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, screenshots_taken)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET
                screenshots_taken = screenshots_taken + 1
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def log_api_call(self):
        """Log an API call."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, api_calls)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET
                api_calls = api_calls + 1
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def log_rate_limit_hit(self):
        """Log when rate limit is exceeded."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, rate_limit_hits)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET
                rate_limit_hits = rate_limit_hits + 1
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def log_maintenance_mode(self):
        """Log maintenance mode activation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT INTO daily_stats (date, maintenance_mode_activations)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET
                maintenance_mode_activations = maintenance_mode_activations + 1
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def generate_monthly_report(self, year: int = None, month: int = None):
        """Generate monthly summary report."""
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get date range for the month
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"
        
        # Aggregate daily stats for the month
        cursor.execute('''
            SELECT 
                SUM(visits) as total_visits,
                SUM(unique_visitors) as unique_visitors,
                SUM(models_generated) as total_models,
                SUM(models_failed) as failed_models,
                AVG(avg_processing_time) as avg_time,
                MIN(min_processing_time) as fastest_time,
                MAX(max_processing_time) as slowest_time,
                SUM(screenshots_taken) as total_screenshots,
                SUM(third_worker_activations) as worker3_activations,
                SUM(third_worker_total_seconds) as worker3_total_seconds,
                SUM(api_calls) as total_api,
                SUM(rate_limit_hits) as total_rate_limits,
                SUM(maintenance_mode_activations) as total_maintenance
            FROM daily_stats
            WHERE date >= ? AND date < ?
        ''', (start_date, end_date))
        
        row = cursor.fetchone()
        
        if not row or not row[0]:
            conn.close()
            return None
        
        (total_visits, unique_visitors, total_models, failed_models, avg_time,
         fastest_time, slowest_time, total_screenshots, worker3_activations,
         worker3_total_seconds, total_api, total_rate_limits, total_maintenance) = row
        
        # Find busiest day
        cursor.execute('''
            SELECT date, visits FROM daily_stats
            WHERE date >= ? AND date < ?
            ORDER BY visits DESC
            LIMIT 1
        ''', (start_date, end_date))
        
        busiest_row = cursor.fetchone()
        busiest_day = busiest_row[0] if busiest_row else None
        
        # Calculate averages
        worker3_total_hours = (worker3_total_seconds or 0) / 3600
        avg_worker3_duration = (worker3_total_seconds / worker3_activations) if worker3_activations else 0
        
        # Insert or update monthly summary
        cursor.execute('''
            INSERT INTO monthly_summaries (
                year, month, total_visits, unique_visitors, total_models_generated,
                total_models_failed, avg_processing_time, fastest_processing_time,
                slowest_processing_time, total_screenshots, third_worker_activations,
                third_worker_total_hours, avg_third_worker_duration, total_api_calls,
                total_rate_limit_hits, total_maintenance_activations, busiest_day
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(year, month) DO UPDATE SET
                total_visits = excluded.total_visits,
                unique_visitors = excluded.unique_visitors,
                total_models_generated = excluded.total_models_generated,
                total_models_failed = excluded.total_models_failed,
                avg_processing_time = excluded.avg_processing_time,
                fastest_processing_time = excluded.fastest_processing_time,
                slowest_processing_time = excluded.slowest_processing_time,
                total_screenshots = excluded.total_screenshots,
                third_worker_activations = excluded.third_worker_activations,
                third_worker_total_hours = excluded.third_worker_total_hours,
                avg_third_worker_duration = excluded.avg_third_worker_duration,
                total_api_calls = excluded.total_api_calls,
                total_rate_limit_hits = excluded.total_rate_limit_hits,
                total_maintenance_activations = excluded.total_maintenance_activations,
                busiest_day = excluded.busiest_day,
                generated_at = CURRENT_TIMESTAMP
        ''', (year, month, total_visits, unique_visitors, total_models, failed_models,
              avg_time, fastest_time, slowest_time, total_screenshots, worker3_activations,
              worker3_total_hours, avg_worker3_duration, total_api, total_rate_limits,
              total_maintenance, busiest_day))
        
        conn.commit()
        
        # Get the summary we just created
        cursor.execute('SELECT * FROM monthly_summaries WHERE year = ? AND month = ?', (year, month))
        summary = cursor.fetchone()
        
        conn.close()
        
        # Write to log file
        self._write_monthly_log(year, month, summary)
        
        return summary
    
    def _write_monthly_log(self, year: int, month: int, summary):
        """Write monthly summary to log file."""
        month_name = datetime(year, month, 1).strftime('%B')
        
        log_entry = f"""
{'='*80}
MONTHLY ANALYTICS REPORT - {month_name} {year}
{'='*80}

📊 TRAFFIC STATISTICS
- Total Visits: {summary[3]:,}
- Unique Visitors: {summary[4]:,}
- Busiest Day: {summary[18]} ({summary[3] // 30:,} avg visits/day)
- Total API Calls: {summary[14]:,}

🎨 MODEL GENERATION
- Total Models Generated: {summary[5]:,}
- Failed Generations: {summary[6]:,}
- Success Rate: {(summary[5] / (summary[5] + summary[6]) * 100) if (summary[5] + summary[6]) > 0 else 0:.1f}%
- Average Processing Time: {summary[7]:.1f} seconds
- Fastest Generation: {summary[8]:.1f} seconds
- Slowest Generation: {summary[9]:.1f} seconds

⚡ WORKER PERFORMANCE
- 3rd Worker Activations: {summary[11]:,} times
- Total Time on 3rd Worker: {summary[12]:.2f} hours
- Average 3rd Worker Duration: {summary[13]:.1f} seconds per activation
- 3rd Worker Uptime: {(summary[12] / (24 * 30) * 100):.2f}% of month

📸 USER ENGAGEMENT
- Screenshots Taken: {summary[10]:,}
- Screenshots per User: {(summary[10] / summary[4]):.1f} avg

🔒 SECURITY & LIMITS
- Rate Limit Hits: {summary[15]:,}
- Maintenance Mode Activations: {summary[16]:,}

📈 DAILY AVERAGES
- Visits per Day: {summary[3] // 30:,}
- Models per Day: {summary[5] // 30:,}
- API Calls per Day: {summary[14] // 30:,}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*80}

"""
        
        # Append to log file
        with open(self.log_path, 'a') as f:
            f.write(log_entry)
        
        # Truncate old months (keep last 12 months)
        self._truncate_old_logs()
    
    def _truncate_old_logs(self):
        """Keep only last 12 months of logs."""
        try:
            if not self.log_path.exists():
                return
            
            with open(self.log_path, 'r') as f:
                content = f.read()
            
            # Split by report headers
            reports = content.split('='*80)
            
            # Keep last 25 reports (12 months + buffer for in-progress months)
            if len(reports) > 25:
                kept_reports = reports[-25:]
                new_content = ('='*80).join(kept_reports)
                
                with open(self.log_path, 'w') as f:
                    f.write(new_content)
        except Exception as e:
            print(f"Failed to truncate logs: {e}")
    
    def get_current_month_stats(self) -> Dict:
        """Get stats for current month (for live dashboard)."""
        now = datetime.now()
        summary = self.generate_monthly_report(now.year, now.month)
        
        if not summary:
            return {}
        
        return {
            'year': summary[1],
            'month': summary[2],
            'total_visits': summary[3],
            'unique_visitors': summary[4],
            'total_models': summary[5],
            'failed_models': summary[6],
            'avg_processing_time': round(summary[7], 2),
            'third_worker_activations': summary[11],
            'third_worker_hours': round(summary[12], 2),
            'total_screenshots': summary[10],
            'rate_limit_hits': summary[15]
        }
    
    def cleanup_old_daily_stats(self, days_to_keep: int = 60):
        """Clean up daily stats older than specified days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        
        cursor.execute('DELETE FROM daily_stats WHERE date < ?', (cutoff_date,))
        
        conn.commit()
        conn.close()
