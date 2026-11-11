# Privacy Policy

**Last Updated: November 28, 2025**
**Platform: SlushAI 3D Modeller**
**Founder: Gary Richard Doman (@GareBearProductionz)**

> **DRAFT — not reviewed (Stage 3, 2026-11-10):** this is unreviewed draft
> text written for the project. It is not legal advice and has not been
> checked by a lawyer. Do not treat it as a final privacy policy until it
> has been reviewed.

## 1. Introduction

This Privacy Policy describes how SlushAI 3D Modeller ("we", "us", "our", or "SlushAI") collects, uses, and protects your information when you use our Service. We are committed to protecting your privacy and handling your data transparently.

**By using SlushAI 3D Modeller, you consent to the data practices described in this policy.**

### Key Privacy Principles
- **We do NOT sell your data** to third parties
- **Email addresses are private** - only visible to staff in moderation tools
- **User directory shows limited public info** - username, tier, badge level, model count only
- **IP addresses are hashed (SHA256) for lookup, but the original IP is also retained** in the visitor log (`visitor_tracker.py` stores both `ip_hash` and `ip_address`). They are not anonymized.
- **Error logs kept for 3 months** for security audits and troubleshooting
- **Regular logs truncate** at 2,560 entries (no long-term storage)
- **You retain ownership** of all images and 3D models

## 2. Information We Collect

### 2.1 Information You Provide Directly

**Account Information:**
- Username or email address (if authentication is required)
- Password (stored in hashed format)
- Profile information (if applicable)

**User-Generated Content:**
- Images you upload for 3D model generation
- Generated 3D models
- Favorites and preferences
- Issue reports and feedback

**Communications:**
- Messages sent through the issue reporting system
- Support requests
- Feature requests

### 2.2 Information Collected Automatically

**Usage Data:**
- IP address
- Browser type and version
- Operating system
- Device information
- Pages visited and features used
- Time and date of access
- Referral URLs
- Session duration

**Technical Data:**
- API request logs
- Model generation parameters
- Error logs and crash reports
- Performance metrics

**Security Data:**
- Rate limiting violations
- Attack attempts and security incidents
- Blocked IP addresses
- User agent strings
- Request patterns

### 2.3 Cookies and Tracking Technologies

We use the following technologies:

**Session Cookies:**
- Authentication tokens
- Session management
- User preferences

**Local Storage:**
- UI settings
- Temporary cache data
- WebSocket connection state

We do NOT use third-party tracking cookies or advertising networks.

## 3. How We Use Your Information

### 3.1 Service Provision
- Process your images and generate 3D models
- Authenticate and maintain your user account
- Store your favorites and preferences
- Enable model downloads and screenshots
- Manage the generation queue

### 3.2 Service Improvement
- Analyze usage patterns to improve features
- Debug and fix technical issues
- Optimize performance and resource usage
- Develop new features
- Train and improve AI models (using anonymized data)

### 3.3 Security and Protection
- Detect and prevent security threats
- Block malicious users and attacks
- Monitor for abuse and violations
- Enforce our Terms of Service
- Investigate suspicious activity

### 3.4 Communication
- Respond to support requests
- Send service announcements (critical updates only)
- Process issue reports
- Notify about account-related matters

### 3.5 Legal Compliance
- Comply with legal obligations
- Respond to lawful requests from authorities
- Protect our rights and property
- Enforce our agreements

## 4. Data Storage and Retention

### 4.1 Storage Location
- Generated models are stored locally on our servers
- User data is stored in SQLite databases
- Logs are stored in local file systems

### 4.2 Retention Periods

**Generated Models:**
- Non-favorited models: Automatically deleted after 36 hours
- Favorited models: Retained until you remove them or delete your account
- Maximum of 32 models per user (includes favorites)

**User Accounts:**
- Active accounts: Retained while your account is active
- Inactive accounts: May be deleted after prolonged inactivity

**Logs and Security Data:**
- Attack logs: Retained for 90 days
- Error logs: Retained for 30 days
- Access logs: Retained for 7 days
- Monthly security reports: Retained indefinitely in aggregated form

**Uploaded Images:**
- Processed images may be temporarily cached during generation
- Original uploads are deleted after model generation completes
- Images are not retained for training purposes without explicit consent

### 4.3 Data Deletion
You can request deletion of your data by:
- Deleting individual models through the interface
- Closing your account (if applicable)
- Contacting us through the issue reporting system

## 5. Data Sharing and Disclosure

### 5.1 We DO NOT Sell Your Data
We do not sell, rent, or trade your personal information to third parties.

### 5.2 Third-Party Services

**Open-Source Dependencies:**
The Service uses open-source libraries including:
- TripoSR (3D model generation)
- Three.js (3D rendering)
- Flask (web framework)
- Socket.IO (real-time communication)

These libraries may have their own privacy practices. We do not share your data with these projects.

**Cryptocurrency Services (If Applicable):**
If cryptocurrency payments are enabled, transaction data may be shared with blockchain networks (which are public by nature).

### 5.3 Legal Requirements
We may disclose information if required to:
- Comply with legal obligations
- Respond to valid legal requests (subpoenas, court orders)
- Protect our rights, property, or safety
- Prevent fraud or security threats
- Enforce our Terms of Service

### 5.4 Business Transfers
If we are involved in a merger, acquisition, or asset sale, your information may be transferred. We will notify you of any such change.

## 6. Data Security

### 6.1 Security Measures

We implement comprehensive security controls:

**Multi-Tier Progressive Blocking System:**
- Automatic IP blocking based on violation severity
- Escalating block durations (5 minutes to 30 days)
- Permanent blocks for persistent offenders

**Attack Detection:**
- SQL injection detection and blocking
- XSS (Cross-Site Scripting) prevention
- Path traversal protection
- Command injection prevention
- SSRF (Server-Side Request Forgery) detection
- Header injection protection

**Rate Limiting:**
- Per-endpoint rate limits
- Global request limits
- Connection limits per IP
- Request size limits

**Encryption:**
- HTTPS/TLS for data in transit
- Password hashing (not stored in plaintext)
- Secure session management

**Access Controls:**
- Authentication required for user-specific features
- Admin-only access for sensitive operations
- Role-based permissions

### 6.2 Security Limitations

**No System is 100% Secure:**
Despite our security measures, no system is completely secure. You acknowledge the inherent risks of internet transmission.

**User Responsibility:**
- Use strong, unique passwords
- Do not share account credentials
- Report security vulnerabilities responsibly
- Keep your device and software updated

## 7. Your Rights and Choices

### 7.1 Access and Control
You have the right to:
- Access your personal information
- Update or correct your information
- Delete your data (subject to legal requirements)
- Export your data (generated models)
- Opt-out of non-essential communications

### 7.2 Managing Your Data

**Through the Interface:**
- View and manage your favorites
- Delete individual models
- Update your preferences
- Close your account (if applicable)

**Contact Us:**
For data requests, use the issue reporting system.

### 7.3 Do Not Track
Our Service does not currently respond to "Do Not Track" signals as there is no industry standard for compliance.

## 8. Children's Privacy

**The Service is not intended for children under 13.**

We do not knowingly collect personal information from children under 13. If you believe we have inadvertently collected such information, contact us immediately to have it removed.

## 9. International Users

### 9.1 Data Location
Our servers may be located in various jurisdictions. By using the Service, you consent to the transfer of your information to these locations.

### 9.2 Compliance with Local Laws
If you are accessing the Service from outside [Primary Jurisdiction], you are responsible for compliance with local laws regarding data collection and use.

### 9.3 GDPR Compliance (EU Users)

If you are in the European Union, you have additional rights:
- Right to data portability
- Right to restriction of processing
- Right to object to processing
- Right to lodge a complaint with supervisory authorities

**Legal Basis for Processing:**
- Contract performance (providing the Service)
- Legitimate interests (security, improvement)
- Legal compliance
- Consent (where applicable)

## 10. California Privacy Rights (CCPA)

If you are a California resident, you have the right to:
- Know what personal information is collected
- Know if personal information is sold or disclosed
- Opt-out of the sale of personal information (we don't sell data)
- Request deletion of personal information
- Non-discrimination for exercising your rights

**To exercise these rights, contact us through the issue reporting system.**

## 11. Data Breach Notification

In the event of a data breach that affects your personal information:
- We will investigate promptly
- We will notify affected users within 72 hours (if legally required)
- We will take remedial action to prevent future breaches
- We will cooperate with authorities as required

## 12. Third-Party Links

The Service may contain links to external websites. We are not responsible for the privacy practices of third-party sites. Review their privacy policies before providing any information.

## 13. Changes to This Policy

### 13.1 Updates
We may update this Privacy Policy from time to time. Changes will be posted on this page with an updated "Last Updated" date.

### 13.2 Material Changes
For significant changes, we may provide additional notice:
- Email notification (if we have your email)
- In-app notification
- Prominent notice on the website

### 13.3 Continued Use
Your continued use of the Service after changes constitutes acceptance of the updated policy.

## 14. Data Processing Details

### 14.1 Image Processing
- Images are processed locally on our servers
- AI model inference is performed using TripoSR
- Images are not sent to external APIs (unless explicitly configured)
- Processing is automated and not manually reviewed

### 14.2 Model Generation
- Generated models are derived works based on your uploaded images
- Models are stored in GLB and OBJ formats
- Thumbnail previews are automatically generated
- Generation metadata (parameters, timing) is logged

### 14.3 Anonymization
When using data for service improvement:
- Personal identifiers are removed
- IP addresses are anonymized or aggregated
- User IDs are pseudonymized
- Only aggregate statistics are retained long-term

## 15. Cookies Policy Details

### 15.1 Essential Cookies
- `session`: User authentication (expires on logout)
- Required for core functionality

### 15.2 Preference Cookies
- UI settings and preferences
- Stored in browser local storage
- Can be cleared via browser settings

### 15.3 Managing Cookies
You can control cookies through your browser settings. Note that disabling essential cookies will prevent the Service from functioning properly.

## 16. Security Logging and Monitoring

### 16.1 What We Log

**Security Events:**
- Failed login attempts
- Rate limit violations
- Attack attempts (SQL injection, XSS, etc.)
- Suspicious user agents
- IP blocking events

**Operational Events:**
- Model generation requests
- API endpoint access
- Error occurrences
- Performance metrics

### 16.2 Log Retention
- Security logs: 90 days
- Operational logs: 30 days
- Monthly aggregated reports: Indefinite

### 16.3 Log Access
- Logs are only accessible to authorized administrators
- Logs may be reviewed for security investigations
- Logs are not sold or shared with third parties

## 17. Contact Information

### 17.1 Privacy Questions
For questions about this Privacy Policy or our data practices:
- Use the issue reporting system within the Service
- Mark your issue as "Privacy-related"
- We will respond within 30 days

### 17.2 Data Protection Officer
If applicable in your jurisdiction, you may contact our Data Protection Officer at [DPO contact information].

### 17.3 Supervisory Authority
EU residents may contact their local data protection authority for complaints.

## 18. Consent and Acknowledgment

**By using AI3DModeller, you acknowledge that:**
- You have read and understood this Privacy Policy
- You consent to the collection and use of information as described
- You understand your rights and how to exercise them
- You agree to the Terms of Service

**If you do not agree with this Privacy Policy, please do not use the Service.**

---

## Summary of Key Points

✅ **We collect:** Account info, uploaded images, usage data, security logs  
✅ **We use it for:** Service provision, security, improvement  
✅ **We store it:** Locally on our servers  
✅ **We keep it:** 36 hours (models), 90 days (security logs)  
✅ **We protect it:** Multi-tier blocking, encryption, attack detection  
✅ **We DON'T:** Sell your data, share with advertisers, or track you across sites  
✅ **You can:** Access, update, delete your data anytime  

**Questions? Use the issue reporting system.**
