#!/usr/bin/env python3
"""Generate monthly analytics report.

Run this script manually or via cron to generate monthly analytics reports.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai3d.utils.analytics_tracker import AnalyticsTracker
from datetime import datetime

def main():
    """Generate monthly report for current or specified month."""
    project_root = Path(__file__).parent.parent
    analytics_db = project_root / 'logs' / 'analytics.db'
    analytics_log = project_root / 'logs' / 'monthly_analytics.log'
    
    tracker = AnalyticsTracker(str(analytics_db), str(analytics_log))
    
    # Get year and month from command line args or use current
    if len(sys.argv) >= 3:
        year = int(sys.argv[1])
        month = int(sys.argv[2])
    else:
        now = datetime.now()
        year = now.year
        month = now.month
    
    print(f"Generating monthly report for {year}-{month:02d}...")
    
    summary = tracker.generate_monthly_report(year, month)
    
    if summary:
        print(f"✅ Report generated successfully!")
        print(f"📄 Log file: {analytics_log}")
        print(f"\n📊 Quick Stats:")
        print(f"  - Total Visits: {summary[3]:,}")
        print(f"  - Models Generated: {summary[5]:,}")
        print(f"  - 3rd Worker Activations: {summary[11]:,}")
        print(f"  - Avg Processing Time: {summary[7]:.1f}s")
    else:
        print("⚠️  No data found for this month.")
    
    # Clean up old daily stats (keep last 60 days)
    tracker.cleanup_old_daily_stats(60)
    print("\n🧹 Cleaned up daily stats older than 60 days")

if __name__ == '__main__':
    main()
