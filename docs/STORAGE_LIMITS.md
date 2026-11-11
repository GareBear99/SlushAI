# Storage Limits & Retention Policies

## Overview

SlushAI 3D Modeller offers generous storage limits that scale with your subscription tier. All plans include automatic cleanup of unfavorited models to keep your account organized.

## Storage Limits by Plan

### 🎁 Free Plan ($0 USD/week)

**Favorites:** 10 models max
**Total Storage:** 32 models
**Retention:** 36 hours for unfavorited models

Free users get:
- 10 favorite slots to protect important models
- 32 total model capacity
- Unfavorited models automatically deleted after 36 hours
- Favorited models kept indefinitely
- **Note:** Tight limits prevent data accumulation (10 models/week × 36 hours = ~5 models max at once)

### ⭐ Standard Plan ($3.47 USD/week or $72 USD/year)

**Favorites:** 50 models
**Total Storage:** 150 models
**Retention:** 14 days for unfavorited models

Standard users get:
- 5x more favorite slots than Free (50 vs 10)
- 4.6x more total storage than Free (150 vs 32)
- 9.3x longer retention than Free (14 days vs 36 hours)
- Favorited models kept indefinitely
- **Estimated storage:** ~750MB - 1.5GB (at 5-10MB per model)

### 👑 Pro Plan ($7.89 USD/week or $164 USD/year)

**Favorites:** 150 models
**Total Storage:** 500 models
**Retention:** 30 days for unfavorited models

Pro users get:
- **15x more favorites** than Free (150 vs 10)
- **15.6x more storage** than Free (500 vs 32)
- **20x longer retention** than Free (30 days vs 36 hours)
- Premium tier for professionals
- **Estimated storage:** ~2.5GB - 5GB (at 5-10MB per model)

## How Favorites Work

### Favoriting Models

- Click the ⭐ icon on any model to favorite it
- Favorited models are protected from automatic deletion
- You can unfavorite models at any time to free up slots

### Storage Management

- Your total model count includes both favorited and unfavorited models
- When you reach your storage limit, you must delete models before generating new ones
- Delete unfavorited models first to free up space
- Use the favorites feature strategically for your best work

## Automatic Cleanup Policy

### Free Plan (36-hour cleanup)

- Unfavorited models are automatically deleted after 36 hours
- You receive a notification before deletion
- Countdown timer shows hours remaining on each model
- Favorite models before the timer expires to save them
- **Security feature:** Prevents free tier data accumulation

### Standard Plan (14-day cleanup)

- Unfavorited models are automatically deleted after 14 days
- Two weeks to review and favorite your best models
- Countdown timer shows days remaining
- Balanced between storage and retention

### Pro Plan (30-day cleanup)

- Unfavorited models are automatically deleted after 30 days
- Full month to review and organize your library
- Maximum retention for paid users
- Best for professional workflows

## Storage Comparison

| Feature | Free | Standard | Pro |
|---------|------|----------|-----|
| **Max Favorites** | 10 | 50 | 150 |
| **Total Storage** | 32 | 150 | 500 |
| **Retention** | 36 hours | 14 days | 30 days |
| **Est. Storage** | ~160-320MB | ~750MB-1.5GB | ~2.5-5GB |
| **Price/week** | $0 | $3.47 | $7.89 |
| **Price/year** | $0 | $72 (save 60%) | $164 (save 60%) |

## Use Cases by Plan

### Free Plan - Best For:

- Casual users testing the platform
- Occasional 3D model generation
- Learning and experimentation
- Small projects with limited scope

**Strategy:** Favorite your best 10 models, let others auto-delete after 36 hours. Upgrade to keep more!

### Standard Plan - Best For:

- Regular users generating models weekly
- Small business owners
- Freelancers with multiple clients
- Hobbyists with growing portfolios

**Strategy:** Organize favorites by project, use 14-day window to review quality

### Pro Plan - Best For:

- Professional 3D artists
- Large-scale production teams
- Agencies managing multiple clients
- Users building extensive model libraries

**Strategy:** Build serious portfolio with 150 favorites, 30-day retention for all models

## Notifications & Warnings

### Storage Limit Warnings

**75% Full:**
- Yellow warning badge appears
- Notification: "Storage 75% full - consider upgrading or deleting models"

**90% Full:**
- Orange warning badge appears
- Notification: "Storage 90% full - delete models or upgrade to avoid blocking"

**100% Full:**
- Red error badge appears
- Cannot generate new models until space is freed
- Notification: "Storage full - delete models or upgrade to continue"

### Deletion Countdown

**3 Days Remaining:**
- Yellow countdown timer on model card
- Email reminder sent

**1 Day Remaining:**
- Orange countdown timer on model card
- Urgent email reminder sent

**Day of Deletion:**
- Red countdown timer showing hours remaining
- Final email notification sent
- Model deleted at midnight UTC

## Best Practices

### For Free Users

1. **Be selective** - You only have 10 favorite slots
2. **Act fast** - Models delete after 36 hours
3. **Download immediately** - Keep local backups of important models
4. **Upgrade when ready** - Standard gives 20x more capacity and 30-day retention

### For Standard Users

1. **Organize by project** - Use naming conventions
2. **Review bi-weekly** - Check models before 14-day deletion
3. **Use favorites wisely** - 50 slots for your best work
4. **Consider Pro upgrade** - If you consistently hit 50 favorites or need longer retention

### For Pro Users

1. **Build your library** - 150 favorites, 500 total models
2. **Organize systematically** - Use naming and categorization
3. **30-day retention** - Plenty of time to curate your collection
4. **Export regularly** - Download archives for backup

## Upgrading Storage

### Instant Benefits

When you upgrade your plan:
- New storage limits apply immediately
- Countdown timers extended automatically
- Previous models retain their status
- No data loss during upgrade

### Downgrading

When you downgrade your plan:
- Grace period of 7 days to adjust storage
- Models exceeding new limit are marked for deletion
- You choose which models to keep
- Favorited models prioritized for retention

## Technical Details

### Storage Calculation

- Each 3D model (GLB file) typically: 2-10 MB
- Each screenshot (PNG file) typically: 100-500 KB
- Total size displayed in account dashboard
- Quota based on model count, not file size

### Cleanup Process

- Runs daily at 00:00 UTC
- Checks creation timestamp vs retention policy
- Emails sent 3 days, 1 day, and 12 hours before deletion
- Favorited models always skipped
- Irreversible - deleted models cannot be recovered

### Data Retention

- User accounts: Retained indefinitely
- Generation history: Retained for 1 year
- Payment records: Retained for 7 years (tax compliance)
- Deleted models: Permanently removed, no backups

## FAQ

**Q: What happens if I don't favorite anything?**
A: On Free plan, all models are deleted after 36 hours. On Standard, after 14 days. On Pro, after 30 days.

**Q: Can I recover a deleted model?**
A: No, automatic deletion is permanent. Download important models before they're deleted.

**Q: Do favorited models count toward my storage limit?**
A: Yes, favorited models count toward both your favorites limit and total storage limit.

**Q: Can I exceed my storage limit temporarily?**
A: No, you must free up space before generating new models.

**Q: What if I upgrade mid-month?**
A: New limits apply immediately. Your retention timers are automatically extended to the new plan's duration.

**Q: Does Pro plan storage have any limits?**
A: Yes, Pro has a limit of 150 favorites and 500 total models. This is designed to fit within our 1000GB infrastructure while providing professional-level storage.

## Support

For storage-related questions or issues:
- Email: support@slushai.com
- Documentation: https://slushai.com/docs
- Account Dashboard: View real-time storage usage
