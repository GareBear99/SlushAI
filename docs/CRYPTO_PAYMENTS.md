# Cryptocurrency Payment System

Complete guide for accepting Bitcoin and Ethereum payments with automatic verification and incremental payment support.

## Overview

SlushAI 3D Modeller now supports cryptocurrency payments with:
- ✅ **Bitcoin (BTC)** and **Ethereum (ETH)** support
- ✅ **Blockchain verification** via Blockstream & Etherscan APIs
- ✅ **Incremental payments** - send partial amounts, pay the rest later
- ✅ **Auto-pricing** - rates update every 10 minutes from CoinGecko
- ✅ **Auto-authorization** - if price drops, partial payments may auto-complete
- ✅ **5% discount** on yearly plans paid with crypto
- ✅ **$5 crypto refills** (instead of $1 for credit card)
- ✅ **QR code payments** for mobile wallets
- ✅ **Sender verification** - only payments from declared wallet are accepted

## Features

### Pricing

| Item | Credit Card | Crypto (BTC/ETH) | Savings |
|------|------------|------------------|---------|
| Refill (10 models) | N/A | $5.00 | - |
| Standard Weekly | $3.47 | $3.47 | - |
| Standard Yearly | $72.00 | **$68.40** | 5% OFF |
| Pro Weekly | $7.89 | $7.89 | - |
| Pro Yearly | $164.00 | **$155.80** | 5% OFF |

### Payment Flow

1. User selects plan and crypto type (BTC or ETH)
2. System creates payment session with:
   - Unique payment ID
   - Exact crypto amount required (calculated at current rates)
   - Receiver wallet address
   - QR code for mobile wallets
   - 24-hour expiration timer
3. User sends crypto from their wallet
4. User enters transaction ID (txid) and their sending wallet address
5. System verifies transaction on blockchain:
   - Validates receiver address matches
   - Validates sender address matches user's input
   - Confirms amount sent
   - Checks blockchain confirmation status
6. Payment tracked incrementally - can send multiple transactions
7. Subscription/refill activates when full payment received

## Setup

### 1. Get Wallet Addresses

You need receiving addresses for both BTC and ETH:

**Bitcoin:**
- Use a reputable wallet (Coinbase, Binance, Ledger, etc.)
- Get your receiving address (starts with `bc1...` or `1...` or `3...`)

**Ethereum:**
- Use MetaMask, Coinbase, or similar
- Get your receiving address (starts with `0x...`)

### 2. Get Etherscan API Key

ETH transaction verification requires an Etherscan API key:
1. Visit https://etherscan.io/apis
2. Sign up for free account
3. Create API key
4. Copy key to `.env` file

**Note:** BTC uses Blockstream API (no key required)

### 3. Configure Environment Variables

Edit `.env` file:

```bash
# Cryptocurrency Payment Configuration
BTC_RECEIVER_ADDRESS=bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq
ETH_RECEIVER_ADDRESS=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
ETHERSCAN_API_KEY=YourEtherscanApiKey123456
```

⚠️ **IMPORTANT:** Use your OWN wallet addresses! Payments go directly to these addresses.

### 4. Start the Server

```bash
python viewer/app.py
```

The crypto payment system will initialize automatically:
- Price updater starts (fetches prices every 10 minutes)
- Database tables created (`logs/crypto_payments.db`)
- Ready to accept payments!

## Usage

### For Users

1. Go to `/pricing` page
2. Click "Pay with Crypto" button on desired plan
3. Choose Bitcoin or Ethereum
4. Scan QR code or copy wallet address
5. Send exact amount shown (or more)
6. Enter your transaction ID and wallet address
7. Click "Verify Payment"
8. Wait for confirmation (usually 1-10 minutes)
9. Subscription activates automatically!

### API Endpoints

#### Get Current Crypto Prices
```http
GET /api/crypto/prices
```

Response:
```json
{
  "success": true,
  "prices": {
    "btc": 95123.45,
    "eth": 3521.67
  },
  "last_update": "2025-11-26T14:23:15"
}
```

#### Create Payment Session
```http
POST /api/crypto/create-payment
Content-Type: application/json

{
  "payment_type": "standard_yearly",
  "crypto_type": "btc"
}
```

Response:
```json
{
  "success": true,
  "payment_id": 42,
  "amount_usd": 68.40,
  "amount_crypto": 0.00071923,
  "crypto_type": "BTC",
  "receiver_address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
  "expires_at": "2025-11-27T14:23:15"
}
```

#### Verify Transaction
```http
POST /api/crypto/verify-payment
Content-Type: application/json

{
  "payment_id": 42,
  "txid": "a1b2c3d4e5f6...",
  "sender_address": "bc1qexample..."
}
```

Response:
```json
{
  "success": true,
  "confirmed": true,
  "amount_sent": 0.00071923,
  "amount_usd": 68.40,
  "payment_complete": true,
  "amount_owed": 0.00
}
```

#### Check Payment Status
```http
GET /api/crypto/payment-status/42
```

Response:
```json
{
  "payment_id": 42,
  "status": "complete",
  "complete": true,
  "required_usd": 68.40,
  "required_crypto": 0.00071923,
  "paid_usd": 68.40,
  "paid_crypto": 0.00071923,
  "amount_owed": 0.00,
  "crypto_owed": 0,
  "crypto_type": "BTC"
}
```

#### Get Payment History
```http
GET /api/crypto/payment-history
```

Response:
```json
{
  "success": true,
  "payments": [
    {
      "payment_id": 42,
      "payment_type": "standard_yearly",
      "crypto_type": "BTC",
      "amount_usd": 68.40,
      "status": "complete",
      "created_at": "2025-11-26T14:23:15",
      "completed_at": "2025-11-26T14:35:42"
    }
  ]
}
```

## Incremental Payments

Users can send partial payments from the **same wallet**:

### Example Flow:

1. **Required:** $68.40 = 0.00071923 BTC
2. **First payment:** User sends 0.0005 BTC
   - Status: Paid $47.56, Owed $20.84
3. **Second payment:** User sends 0.0003 BTC
   - Status: Paid $76.04, **Complete!** (overpayment is fine)

### Rules:
- All payments must come from the **same wallet address**
- Payments must be **confirmed on blockchain**
- Total USD value must reach required amount
- Each transaction needs unique txid

## Auto-Authorization

If crypto prices drop after partial payment, the system may auto-authorize:

### Example:

1. **Required:** $68.40 at BTC=$95,000
2. **User sends:** 0.00071 BTC (slightly less)
3. **Value:** $67.45 (short by $0.95)
4. **Price drops:** BTC=$93,000
5. **New value:** $66.03 → Still short
6. **Price drops again:** BTC=$91,000
7. **New value:** $64.61 → **Wait...**
8. **Price bounces back:** BTC=$95,500
9. **New value:** $67.81 → **Auto-authorized!** ✅

The system checks every 10 minutes (when prices update) and auto-completes payments within 5% tolerance.

## Blockchain Verification

### Bitcoin (BTC)
- **API:** Blockstream.info (no key required)
- **Endpoint:** `https://blockstream.info/api/tx/{txid}`
- **Verification:**
  - Checks transaction exists
  - Validates receiver address in outputs
  - Extracts sender from inputs
  - Confirms blockchain confirmation status
  - Calculates amount in satoshis → BTC

### Ethereum (ETH)
- **API:** Etherscan.io (requires free API key)
- **Endpoint:** `https://api.etherscan.io/api`
- **Verification:**
  - Gets transaction by hash
  - Gets transaction receipt for confirmation
  - Validates sender (`from`) address
  - Validates receiver (`to`) address
  - Converts wei → ETH

## Security Features

1. **Sender Validation**
   - User must declare their sending wallet
   - Only transactions from that wallet are accepted
   - Prevents address confusion attacks

2. **Receiver Validation**
   - Transaction must be sent to exact receiver address
   - Prevents wrong-destination errors

3. **Amount Tracking**
   - All payments converted to USD at time of verification
   - Protects against price manipulation

4. **Unique Transaction IDs**
   - Each txid can only be used once
   - Database UNIQUE constraint prevents double-spending

5. **24-Hour Expiration**
   - Payment sessions expire after 24 hours
   - Prevents stale sessions from completing

6. **Blockchain Confirmation**
   - Only confirmed transactions counted
   - Prevents mempool manipulation

## Database Schema

### `crypto_payments`
Main payment sessions:
```sql
CREATE TABLE crypto_payments (
    payment_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    payment_type TEXT NOT NULL,
    crypto_type TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    amount_crypto REAL NOT NULL,
    receiver_address TEXT NOT NULL,
    sender_address TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT
);
```

### `payment_increments`
Individual transactions:
```sql
CREATE TABLE payment_increments (
    increment_id INTEGER PRIMARY KEY,
    payment_id INTEGER NOT NULL,
    txid TEXT NOT NULL UNIQUE,
    amount_crypto REAL NOT NULL,
    amount_usd REAL NOT NULL,
    sender_address TEXT NOT NULL,
    confirmed BOOLEAN NOT NULL,
    verified_at TEXT
);
```

### `price_history`
Price tracking for auto-auth:
```sql
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY,
    crypto_type TEXT NOT NULL,
    price_usd REAL NOT NULL,
    timestamp TEXT NOT NULL
);
```

## Troubleshooting

### Transaction Not Found

**Problem:** "Transaction not found" error when verifying

**Solutions:**
1. Wait 1-2 minutes for blockchain propagation
2. Check txid is correct (copy-paste from wallet)
3. Verify transaction on blockchain explorer:
   - BTC: https://blockstream.info
   - ETH: https://etherscan.io
4. Ensure transaction has at least 1 confirmation

### Sender Address Mismatch

**Problem:** "Sender address does not match" error

**Solutions:**
1. Use the EXACT address you sent from
2. Check your wallet for the sending address
3. Copy address from blockchain explorer transaction details
4. Be careful with case sensitivity (ETH addresses)

### Wrong Receiver Address

**Problem:** "Transaction sent to wrong address" error

**Solutions:**
1. Transaction was sent to wrong wallet (cannot be recovered)
2. Contact support with txid
3. Double-check receiver address in payment UI

### Price Changed, Now Short

**Problem:** Sent exact amount but price increased

**Solutions:**
1. Send additional crypto to cover difference
2. Wait for price to drop (auto-auth may trigger)
3. Amount owed shown in payment status

### ETH Verification Failing

**Problem:** ETH transactions fail to verify

**Solutions:**
1. Check ETHERSCAN_API_KEY in `.env` is correct
2. Verify API key is active on Etherscan
3. Check API rate limits (5 calls/sec on free tier)
4. Try again after a few minutes

## Testing

### Test with Testnet (Recommended)

Use testnet coins for testing:

**BTC Testnet:**
- Get testnet BTC: https://coinfaucet.eu/en/btc-testnet/
- Testnet explorer: https://blockstream.info/testnet/
- Modify API endpoints to testnet

**ETH Sepolia Testnet:**
- Get testnet ETH: https://sepoliafaucet.com/
- Testnet explorer: https://sepolia.etherscan.io/
- Use Sepolia Etherscan API

### Test Flow:

1. Create payment session
2. Send testnet crypto
3. Wait for confirmation
4. Verify transaction
5. Check status updates
6. Confirm subscription activation

## Best Practices

### For Operators

1. **Use Hardware Wallets**
   - Store private keys securely
   - Use Ledger/Trezor for receiving addresses

2. **Monitor Payments**
   - Check `/api/crypto/payment-history` regularly
   - Set up alerts for large payments

3. **Backup Database**
   - Regularly backup `crypto_payments.db`
   - Contains payment records and txids

4. **Update Prices**
   - Price updater runs automatically
   - Check logs for update failures

5. **Rate Limits**
   - Blockstream: No limits
   - Etherscan: 5 calls/sec (free tier)
   - CoinGecko: 10-50 calls/min (free tier)

### For Users

1. **Double-Check Addresses**
   - Always verify receiver address
   - Use QR codes when possible

2. **Save Transaction ID**
   - Copy txid immediately after sending
   - You'll need it for verification

3. **Use Same Wallet**
   - All payments must be from same address
   - Don't use exchange wallets (they rotate addresses)

4. **Send Exact Amount**
   - Or slightly more to account for price changes
   - Underpayments require additional transactions

5. **Wait for Confirmation**
   - BTC: Usually 10-30 minutes
   - ETH: Usually 1-5 minutes
   - Don't verify immediately after sending

## Future Enhancements

Planned features:
- [ ] Additional cryptocurrencies (LTC, USDT, USDC)
- [ ] Lightning Network support (instant BTC)
- [ ] Automatic refunds for overpayments
- [ ] Email notifications on payment events
- [ ] Webhook integration for accounting
- [ ] Multi-currency display (EUR, GBP, JPY)
- [ ] Payment links (shareable URLs)
- [ ] Recurring crypto subscriptions
- [ ] Gift codes via crypto

## Support

For issues with crypto payments:
1. Check payment status API
2. Verify transaction on blockchain explorer
3. Review server logs in `logs/viewer.log`
4. Check price update logs
5. Open GitHub issue with:
   - Payment ID
   - Transaction ID (txid)
   - Error message
   - Blockchain explorer link

## Legal Disclaimer

Cryptocurrency payments are processed directly on-chain. The platform:
- Does NOT custody user funds
- Does NOT convert crypto to fiat
- Does NOT provide financial advice
- Cannot reverse blockchain transactions

Users are responsible for:
- Sending to correct addresses
- Managing their private keys
- Complying with local regulations
- Paying applicable taxes

---

**Last Updated**: 2025-11-26
**Version**: 1.0.0
