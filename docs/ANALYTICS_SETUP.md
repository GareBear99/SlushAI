# Analytics Setup Guide

Complete guide for SlushAI 3D Modeller analytics tracking and reporting.

## Overview

The analytics system tracks:
- **Site Traffic**: visits, unique visitors, daily patterns
- **Model Generation**: success rate, processing times, performance
- **Worker Usage**: 3rd worker activations, duration, uptime percentage
- **User Engagement**: screenshots, API calls
- **Security**: rate limit breaches, maintenance mode activations

## Database Schema

Analytics are stored in `logs/analytics.db` with three tables:

### `daily_stats`
Aggregated daily metrics (auto-purged after 60 days)
- `date`: YYYY-MM-DD
- `total_visits`, `unique_visitors`
- `models_generated`, `models_failed`
- `avg_processing_time`, `min_processing_time`, `max_processing_time`
- `total_screenshots`, `total_api_calls`
- `third_worker_activations`, `third_worker_duration`
- `rate_limit_hits`, `maintenance_mode_activations`

### `monthly_summaries`
Monthly aggregate reports (permanent storage)
- `year`, `month`
- All daily_stats columns aggregated
- `busiest_day`: date with most traffic

### `realtime_events`
Short-term event stream (auto-purged after 7 days)
- `timestamp`, `event_type`
- `user_id`, `ip_address`, `metadata`

## Tracked Events

### Automatic Tracking
The analytics system automatically tracks:

1. **Page Visits**
   - Every `/viewer` and `/` access
   - Unique visitors identified by IP hash (GDPR compliant)

2. **Model Generation**
   - Start time, end time, processing duration
   - Success/failure status
   - User ID

3. **3rd Worker Activation**
   - Start/stop timestamp
   - Duration of activation
   - Queue size that triggered it

4. **Screenshots**
   - Timestamp of capture
   - User ID

5. **API Calls**
   - Endpoint accessed
   - Response time

6. **Rate Limit Breaches**
   - User or IP that exceeded limits
   - Endpoint attempted

7. **Maintenance Mode**
   - Start/stop timestamp
   - Queue size that triggered it

## Monthly Reports

Reports are automatically generated and saved to `logs/monthly_analytics.log`.

### Manual Generation

Generate report for current month:
```bash
python scripts/generate_monthly_report.py
```

Generate report for specific month:
```bash
python scripts/generate_monthly_report.py 2025 11
```

### Automated Generation (Cron)

Add to your crontab to run at 2 AM on the 1st of each month:

```bash
# Open crontab editor
crontab -e

# Add this line (adjust path to your installation)
0 2 1 * * cd /path/to/AI3DModeller && python3 scripts/generate_monthly_report.py >> logs/cron.log 2>&1
```

**macOS users**: You may need to grant Terminal/cron "Full Disk Access" in System Preferences > Security & Privacy.

### Report Format

Each monthly report includes:

```
================================================================================
MONTHLY ANALYTICS REPORT - November 2025
================================================================================

📊 TRAFFIC STATISTICS
- Total Visits: 15,432
- Unique Visitors: 2,847
- Busiest Day: 2025-11-15 (514 avg visits/day)
- Total API Calls: 8,921

🎨 MODEL GENERATION
- Total Models Generated: 3,245
- Failed Generations: 124
- Success Rate: 96.3%
- Average Processing Time: 8.3 seconds
- Fastest Generation: 4.2 seconds
- Slowest Generation: 45.6 seconds

⚡ WORKER PERFORMANCE
- 3rd Worker Activations: 47 times
- Total Time on 3rd Worker: 12.4 hours
- Average 3rd Worker Duration: 950.5 seconds per activation
- 3rd Worker Uptime: 1.72% of month

📸 USER ENGAGEMENT
- Screenshots Taken: 1,823
- Screenshots per User: 0.6 avg

🔒 SECURITY & LIMITS
- Rate Limit Hits: 89
- Maintenance Mode Activations: 3

📈 DAILY AVERAGES
- Visits per Day: 514
- Models per Day: 108
- API Calls per Day: 297

Generated: 2025-12-01 02:00:15
================================================================================
```

### Log Retention

- **Monthly reports**: Last 12 months kept automatically
- **Daily stats**: Last 60 days (configurable in script)
- **Realtime events**: Last 7 days (auto-purged by tracker)

## API Endpoints

### View Current Month Stats
```
GET /api/analytics/monthly
```

**Response:**
```json
{
  "year": 2025,
  "month": 11,
  "total_visits": 15432,
  "unique_visitors": 2847,
  "total_models": 3245,
  "failed_models": 124,
  "avg_processing_time": 8.3,
  "third_worker_activations": 47,
  "third_worker_hours": 12.4,
  "total_screenshots": 1823,
  "rate_limit_hits": 89
}
```

**Authentication**: Requires admin login (future feature)

## Monitoring Best Practices

### Key Metrics to Watch

1. **Success Rate** (should be > 95%)
   - If falling, check model processing errors
   - Review failed generation logs

2. **Processing Time** (should be < 15s avg)
   - Spikes indicate GPU/CPU bottleneck
   - May need to reduce concurrent workers

3. **3rd Worker Uptime** (should be < 5%)
   - High percentage = sustained overload
   - Consider upgrading hardware or quota limits

4. **Rate Limit Hits** (should be minimal)
   - High numbers = potential abuse
   - Review and adjust rate limits if needed

5. **Maintenance Mode** (should be < 5 activations/month)
   - Frequent activations = need more capacity
   - Review queue management settings

### Alert Thresholds

Consider setting up alerts for:
- Success rate drops below 90%
- Avg processing time exceeds 20s
- 3rd worker uptime exceeds 10%
- Maintenance mode activations > 10/month

## Database Maintenance

The system automatically cleans up old data, but you can manually optimize:

```bash
# Vacuum database (reclaim space)
sqlite3 logs/analytics.db "VACUUM;"

# Check database size
du -h logs/analytics.db

# Manually clean old daily stats (keeps last 60 days)
python scripts/generate_monthly_report.py
```

## Privacy & GDPR Compliance

The analytics system is designed with privacy in mind:

1. **IP Hashing**: All IP addresses are SHA256 hashed before storage
2. **No PII**: User IDs are anonymous (Google OAuth sub)
3. **Data Retention**: Automatic purging of old data
4. **Aggregation**: Monthly reports use aggregated data only

## Troubleshooting

### Report not generating
```bash
# Check database exists
ls -l logs/analytics.db

# Check permissions
chmod 644 logs/analytics.db

# Test manually
python scripts/generate_monthly_report.py
```

### No data in reports
- Ensure Flask app is using `AnalyticsTracker`
- Check that tracker is initialized in `app.py`
- Verify database has data: `sqlite3 logs/analytics.db "SELECT COUNT(*) FROM daily_stats;"`

### Cron job not running
```bash
# Check cron is running
sudo systemctl status cron  # Linux
sudo launchctl list | grep cron  # macOS

# Check cron logs
grep CRON /var/log/syslog  # Linux
grep cron /var/log/system.log  # macOS

# Test cron script manually
/path/to/scripts/generate_monthly_report.py
```

## Future Enhancements

Planned analytics features:
- [ ] Real-time dashboard with live charts
- [ ] Email reports to admin
- [ ] Slack/Discord webhook notifications
- [ ] Anomaly detection (unusual traffic patterns)
- [ ] User cohort analysis
- [ ] A/B testing framework
- [ ] Export to CSV/JSON
- [ ] Integration with monitoring tools (Prometheus, Datadog)

## Example Analysis

### Capacity Planning
Current capacity with 3 workers:
- 2 workers: 960 models/day
- 3 workers (peak): 1,440 models/day

If average daily models exceeds 800:
- Consider upgrading to permanent 3-worker setup
- Or reduce quota limits per tier

### Cost Optimization
If 3rd worker uptime consistently > 5%:
- Hardware upgrade may be more cost-effective than spot instances
- Or increase pricing to reduce demand

### User Engagement
Screenshots per user ratio:
- High ratio (> 1.0) = engaged users exploring models
- Low ratio (< 0.3) = users leaving quickly (check UX)

## Support

For issues or questions about analytics:
1. Check `logs/analytics_errors.log`
2. Review Flask app logs
3. Open GitHub issue with report output

---

**Last Updated**: 2025-11-26
