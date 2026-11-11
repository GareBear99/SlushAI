# Terms of Service

**Last Updated: November 28, 2025**
**Platform: SlushAI 3D Modeller**
**Founder: Gary Richard Doman (@GareBearProductionz)**

> **DRAFT — not reviewed (Stage 3, 2026-11-10):** this is unreviewed draft
> text written for the project. It is not legal advice and has not been
> checked by a lawyer. Do not treat it as final legal terms until it has
> been reviewed.

## 1. Acceptance of Terms

By accessing or using SlushAI 3D Modeller ("the Service", "SlushAI", or "the Platform"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the Service.

**Important**: These Terms apply to all users, including free tier users, paid subscribers (Standard/Pro), staff members (Moderators/Admins), and the Founder.

## 2. Description of Service

SlushAI 3D Modeller is an AI-powered web platform that transforms 2D images into high-quality 3D models. The Service includes:

### Core Features
- **AI-Powered Generation**: Image-to-3D model conversion using TripoSR technology
- **Interactive 3D Viewer**: Real-time model preview with orbit controls
- **Model Downloads**: OBJ + MTL + PNG downloads for generated models (GLB export is not produced by this build)
- **Screenshot Gallery**: Capture and save model screenshots (1-minute cooldown)
- **Smart Storage System**: Save/favorite functionality with automatic cleanup
- **Activity Tracking**: Complete logs of generations, saves, and deletions (30-day retention)

### Account Features
- **Multi-Authentication**: Google OAuth, Facebook OAuth, or Email/Password
- **Username System**: Unique usernames (3-20 characters, alphanumeric + underscore)
- **Email Verification**: Required for email/password accounts (6-digit codes, 10-minute expiry)
- **Badge Progression**: 5 levels from Newcomer to Legend based on completed models
- **Benefactor Badge**: Mystery badge unlocked by donations ($1+ monthly renewal)

### Subscription System
- **Free Tier**: 10 models/week, 10 favorites, 32 total models, 36-hour deletion
- **Standard Tier**: 40 models/week, 50 favorites, 150 models, 14-day deletion
- **Pro Tier**: 120 models/week, 150 favorites, 500 models, 30-day deletion
- **Quick Refills**: $1 for +10 models (max 100/week)

### Referral System (Benefactor Members Only)
- Earn $1/week per paying referral
- Earnings first pay subscription, then become redeemable profit
- Minimum $5 cashout via PayPal or Crypto (BTC/ETH)
- Requires monthly badge renewal

## 3. User Accounts

### 3.1 Account Creation
**Registration Methods:**
- **Google OAuth**: Sign in with existing Google account (instant email verification)
- **Facebook OAuth**: Sign in with existing Facebook account (instant email verification)
- **Email/Password**: Create account with email verification (6-digit code, 10-minute expiry)

**Account Requirements:**
- You must provide accurate and complete information
- Usernames must be unique, 3-20 characters, start with letter, alphanumeric + underscore only
- Valid email address required for all accounts
- You must be 13 years or older to use the Service
- **IP Limit**: Maximum 3 accounts per IP address (prevents spam/abuse)
- **Signup Rate Limit**: 5 signups per hour per IP address

### 3.2 Account Security
**Your Responsibilities:**
- Maintain confidentiality of your password (for email/password accounts)
- Notify us immediately of any unauthorized use: support via homepage
- Do not share your account credentials with anyone
- Log out from shared computers

**Our Protection:**
- Passwords hashed with bcrypt (12+ rounds)
- Multi-tier security system with progressive blocking
- Attack detection (SQL injection, XSS, path traversal, command injection, DDoS)
- Rate limiting on all endpoints
- Error logs kept for 3 months for security audits

### 3.3 Account Termination
**By You:**
- Close your account at any time through the Account tab
- All favorited models will be permanently deleted
- Redeemable referral balance will be paid out (if ≥$5)

**By Us:**
- We reserve the right to suspend or terminate accounts that violate these Terms
- Accounts may be suspended for security violations (see Section 4.2)
- Upon termination, your right to use the Service ceases immediately
- Unused subscription time is non-refundable

## 4. Acceptable Use Policy

### 4.1 Prohibited Activities
You agree NOT to:

- Upload, generate, or distribute illegal, harmful, threatening, abusive, harassing, defamatory, vulgar, obscene, or otherwise objectionable content
- Violate any intellectual property rights, including copyrights, trademarks, or patents
- Attempt to gain unauthorized access to the Service or related systems
- Use automated means (bots, scrapers, etc.) to access the Service without permission
- Interfere with or disrupt the Service or servers
- Impersonate any person or entity
- Upload malware, viruses, or any malicious code
- Use the Service for any commercial purpose without authorization
- Generate models from images you do not have rights to use
- Attempt to reverse engineer or decompile the Service
- Bypass any security features or rate limiting mechanisms
- Engage in any activity that could damage, disable, or impair the Service

### 4.2 Rate Limits and Security System
**Weekly Generation Quotas:**
- Free Tier: 10 models/week (resets Monday 00:00 UTC)
- Standard Tier: 40 models/week
- Pro Tier: 120 models/week
- Staff: 500 models/week
- Only successful completions count toward quota
- Failed or cancelled generations do not consume quota

**Storage Limits by Tier:**
- **Free**: 10 favorites max, 32 total models, 36-hour auto-deletion for unsaved
- **Standard**: 50 favorites max, 150 total models, 14-day auto-deletion
- **Pro**: 150 favorites max, 500 total models, 30-day auto-deletion
- **Favorited models are permanent** and protected from deletion (cannot be unfavorited)

**API Rate Limits:**
- Public endpoints (/api/health, /api/capacity): No limit
- Public pages (/docs, /users): 100 req/min, 256,000 req/day per IP
- Username validation: 30 req/min per IP
- Signup: 5 req/hour per IP, 3 accounts max per IP
- Protected endpoints: 30-60 req/min per user
- Support: 5 req/hour per user/IP

**4-Level Progressive Blocking System:**
- **Level 1**: Rate limit warning (429 error, retry after cooldown)
- **Level 2**: Temporary block (1 hour for sustained >100 req/min)
- **Level 3**: Extended block (24 hours for attack patterns)
- **Level 4**: Permanent ban (DDoS attacks >1000 req/10s, repeated malicious activity)

**Attack Detection & Response:**
- SQL injection attempts: Immediate 24-hour block
- XSS attempts: Immediate 24-hour block
- Path traversal: Immediate 24-hour block
- Command injection: Immediate 24-hour block
- DDoS attacks: Immediate permanent ban
- Brute force attempts: Progressive blocking
- All attacks logged for 3 months

### 4.3 Content Guidelines
- You retain ownership of images you upload
- You grant us a license to process your images for model generation
- You are solely responsible for the legality of images you upload
- We reserve the right to remove any content that violates these Terms

## 5. Intellectual Property

### 5.1 Service Ownership
- The Service, including all software, designs, and trademarks, is owned by us and our licensors
- These Terms do not grant you any rights to our intellectual property

### 5.2 User Content
- You retain ownership of images you upload
- Generated 3D models are provided to you under a limited license for personal use
- You may not resell or redistribute generated models without authorization

### 5.3 License Grant
By using the Service, you grant us a non-exclusive, worldwide, royalty-free license to:
- Process, store, and display your uploaded images
- Generate 3D models from your images
- Use anonymized data to improve the Service

## 6. Security and Data Protection

### 6.1 Security Measures
We implement multiple security layers including:
- Multi-tier progressive IP blocking system
- DDoS protection and rate limiting
- Attack detection and prevention
- Encrypted data transmission
- Regular security audits

### 6.2 User Responsibilities
- Use strong passwords
- Do not share account credentials
- Report security vulnerabilities responsibly
- Comply with all security policies

## 7. Service Availability

### 7.1 No Guarantee of Uptime
- The Service is provided "as is" and "as available"
- We do not guarantee uninterrupted or error-free operation
- We may suspend the Service for maintenance or updates

### 7.2 Modifications
- We reserve the right to modify or discontinue the Service at any time
- We may change these Terms at any time by posting updated Terms
- Continued use after changes constitutes acceptance of new Terms

## 8. Disclaimers and Limitations

### 8.1 Disclaimer of Warranties
THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO:
- Merchantability
- Fitness for a particular purpose
- Non-infringement
- Accuracy or reliability of results

### 8.2 Limitation of Liability
TO THE MAXIMUM EXTENT PERMITTED BY LAW:
- We are not liable for any indirect, incidental, special, consequential, or punitive damages
- Our total liability shall not exceed the amount you paid for the Service (if any) in the past 12 months
- We are not liable for data loss, service interruptions, or third-party actions

### 8.3 Quality of Generated Models
- Generated 3D models may vary in quality
- We do not guarantee that models will be suitable for any particular purpose
- Model generation is dependent on input image quality and AI model capabilities

## 9. Privacy and Data Collection

Your use of the Service is also governed by our Privacy Policy. By using the Service, you consent to our data practices as described in the Privacy Policy.

## 10. Third-Party Services

### 10.1 External Links
- The Service may contain links to third-party websites or services
- We are not responsible for the content or practices of third-party services
- Use of third-party services is at your own risk

### 10.2 Third-Party Software
- The Service uses open-source and third-party software components
- Such components are subject to their own licenses and terms

## 11. Issue Reporting and Support

### 11.1 Issue Reporting System
- Users may report technical issues, bugs, or feature requests
- We reserve the right to prioritize or decline issue resolution
- Issue reports may be reviewed by administrators

### 11.2 No Guaranteed Support
- We are not obligated to provide technical support
- Support, if provided, is on a best-effort basis

## 12. Badge System & Progression

### 12.1 Badge Levels
Users earn badges based on lifetime completed models:
- **Newcomer** (0-9 models): Gray badge, starting level
- **Creator** (10-49 models): Blue badge, one-time quota reset reward
- **Artist** (50-199 models): Purple badge, one-time quota reset reward
- **Master** (200-499 models): Orange badge, one-time quota reset reward
- **Legend** (500+ models): Red badge, one-time quota reset reward
- **Benefactor** (Mystery Badge): Purple badge, unlocked by donation, monthly renewal required

### 12.2 Badge Rewards
- Each badge level (Creator through Legend) grants a **one-time** weekly quota reset
- Rewards are granted once per badge level (cannot be farmed)
- Only successful model completions count toward badge progression
- Failed or cancelled generations do not count
- Badge levels are permanent and track lifetime progress

### 12.3 Benefactor Badge (Mystery Badge)
**Unlock Requirements:**
- Donate $1 or more to SlushAI via /donate page
- Unlocks referral system access
- Badge displayed with purple color and special icon

**Monthly Renewal:**
- Badge expires on the 1st of each month at 00:00 UTC
- Must donate $1+ each month to renew
- Losing badge locks referral system
- Redeemable balance preserved but frozen until renewal
- Email notification sent when badge expires

## 13. Referral System (Benefactor Members Only)

### 13.1 Eligibility
- Active Benefactor badge required
- Must donate $1+ monthly to maintain access
- System locks if badge expires

### 13.2 How It Works
**Earning Structure:**
- Earn $1 USD per week for each paying member you refer
- Only Standard and Pro subscribers count as paying members
- Free tier referrals do not generate earnings
- Unlimited referrals - no cap on potential earnings

**Earnings Distribution:**
1. **Pay Your Bill First**: Earnings automatically pay your subscription cost
2. **Accumulate Profit**: Excess earnings become redeemable balance
3. **Cash Out**: Redeem when balance reaches minimum $5 threshold

**Example:**
- You have Standard plan ($3.50/week)
- You refer 10 paying members
- Weekly earnings: $10.00
- Minus subscription: -$3.50
- Redeemable profit: $6.50/week
- Your subscription is free + you earn passive income!

### 13.3 Payouts
**Redemption Requirements:**
- Minimum cashout: $5.00 USD
- Earnings must first cover subscription cost
- Payout options: PayPal or Crypto (BTC/ETH)
- Payouts processed weekly

**Badge Expiration Impact:**
- Losing Benefactor badge freezes referral system
- Redeemable balance preserved but cannot cash out
- Referred members remain tracked
- Earnings resume when badge renewed

### 13.4 Prohibited Referral Practices
You agree NOT to:
- Create fake accounts to generate referral earnings
- Use bots or automated systems to create referrals
- Spam or harass people with referral links
- Misrepresent the Service to potential referrals
- Pay users to sign up through your referral link
- Violate any platform's terms when sharing referral links

**Consequences:**
- Referral abuse results in immediate account termination
- All earnings forfeited
- Permanent ban from referral system
- No refunds for lost earnings

## 14. Subscription Plans & Payments

### 14.1 Subscription Tiers
**Free Tier ($0/week):**
- 10 models/week
- 10 favorites max, 32 total models
- 36-hour auto-deletion for unsaved models
- Standard queue priority

**Standard Tier:**
- Weekly: $3.47 USD/week
- Yearly: $72 USD/year (save 60%)
- 40 models/week
- 50 favorites max, 150 total models
- 14-day auto-deletion for unsaved
- Priority queue, higher resolution (512px), email support

**Pro Tier:**
- Weekly: $7.89 USD/week
- Yearly: $164 USD/year (save 60%)
- 120 models/week
- 150 favorites max, 500 total models
- 30-day auto-deletion for unsaved
- Highest priority queue, max resolution (1024px), API access, premium support

**Quick Refill:**
- $1.00 USD per refill
- Adds +10 models to current week quota
- Maximum 100 refills per week
- No subscription required

### 14.2 Payment Processing
**Credit Card Payments:**
- Processed securely through Stripe
- Auto-renewal for subscriptions
- Cancel anytime

**Cryptocurrency Payments:**
- Bitcoin (BTC) and Ethereum (ETH) accepted
- Yearly plans receive additional 5% crypto discount
- Real-time price conversion via CoinGecko
- 24-hour payment window
- Incremental payments supported
- Blockchain verification required

### 14.3 Refunds & Cancellations
- Subscriptions can be cancelled anytime through Account tab
- No refunds for partial subscription periods
- Unused quota does not roll over
- Quick refills are non-refundable
- Crypto payments are final and non-refundable (blockchain transactions)

### 14.4 Platform Capacity Limits
**User Registration Limits (1000GB Infrastructure):**
- Free Tier: 200 users maximum
- Standard Tier: 50 users maximum
- Pro Tier: 20 users maximum
- When tier reaches capacity, signups for that tier are paused
- Users can upgrade to higher tier with available capacity
- Capacity expanded regularly based on demand

## 15. Cryptocurrency Integration

### 12.1 Cryptocurrency Payments
- If cryptocurrency payments are offered, they are provided through third-party services
- You are responsible for understanding cryptocurrency risks
- Cryptocurrency transactions may be irreversible

### 12.2 No Financial Advice
- We do not provide financial, investment, or tax advice
- Consult appropriate professionals before making financial decisions

## 13. Indemnification

You agree to indemnify and hold us harmless from any claims, damages, losses, liabilities, and expenses (including legal fees) arising from:
- Your use of the Service
- Your violation of these Terms
- Your violation of any rights of another party
- Your uploaded content

## 14. Dispute Resolution

### 14.1 Governing Law
These Terms are governed by the laws of [Your Jurisdiction], without regard to conflict of law provisions.

### 14.2 Arbitration
Any disputes shall be resolved through binding arbitration, except where prohibited by law.

### 14.3 Class Action Waiver
You agree to resolve disputes individually, not as part of a class action.

## 15. Miscellaneous

### 15.1 Entire Agreement
These Terms constitute the entire agreement between you and us regarding the Service.

### 15.2 Severability
If any provision is found unenforceable, the remaining provisions remain in effect.

### 15.3 No Waiver
Our failure to enforce any right or provision does not constitute a waiver.

### 15.4 Assignment
You may not assign these Terms without our consent. We may assign these Terms without restriction.

### 15.5 Force Majeure
We are not liable for failures due to circumstances beyond our reasonable control.

## 16. Contact Information

For questions about these Terms, contact us through:
- The issue reporting system within the Service
- [Your contact method]

## 17. Special Provisions

### 17.1 Beta Services
- Certain features may be designated as beta or experimental
- Beta features are provided without warranties and may be discontinued

### 17.2 Academic and Research Use
- If using the Service for academic or research purposes, you must provide appropriate attribution
- Commercial use of research results may require separate authorization

### 17.3 Export Controls
- You agree to comply with all applicable export laws and regulations
- You may not use the Service in countries subject to trade restrictions

---

**By using AI3DModeller, you acknowledge that you have read, understood, and agree to be bound by these Terms of Service.**
