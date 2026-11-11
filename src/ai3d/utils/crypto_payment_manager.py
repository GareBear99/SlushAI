"""Cryptocurrency Payment Manager for BTC and ETH.

Handles:
- Wallet address generation and validation
- Transaction tracking and blockchain verification
- Incremental payment handling
- Price updates (10-minute intervals)
- Auto-authorization when price drops back in range
"""
import sqlite3
import time
import requests
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from threading import Thread, Lock
from pathlib import Path


class CryptoPaymentManager:
    """Manages cryptocurrency payments for subscriptions and refills."""
    
    # Pricing in USD
    PRICING = {
        'refill': 5.00,  # $5 for 10 models (crypto only)
        'standard_weekly': 3.47,
        'standard_yearly': 72.00,
        'pro_weekly': 7.89,
        'pro_yearly': 164.00
    }
    
    # 5% discount for yearly crypto payments
    YEARLY_DISCOUNT = 0.05
    
    # Price update interval (10 minutes)
    PRICE_UPDATE_INTERVAL = 600  # seconds
    
    # Tolerance for price fluctuation auto-auth (5%)
    PRICE_TOLERANCE = 0.05
    
    def __init__(self, db_path: str, receiver_wallets: Dict[str, str]):
        """Initialize crypto payment manager.
        
        Args:
            db_path: Path to SQLite database
            receiver_wallets: Dict with 'btc' and 'eth' receiver addresses
        """
        self.db_path = Path(db_path)
        self.receiver_wallets = receiver_wallets
        
        # Current crypto prices (USD)
        self.prices = {'btc': 0.0, 'eth': 0.0}
        self.price_lock = Lock()
        self.last_price_update = None
        
        # Initialize database
        self._init_db()
        
        # Start price updater thread
        self.price_updater_running = True
        self.price_thread = Thread(target=self._price_updater_loop, daemon=True)
        self.price_thread.start()
    
    def _init_db(self):
        """Initialize database tables for crypto payments."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Crypto payment sessions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS crypto_payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # Individual transaction increments
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_increments (
            increment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id INTEGER NOT NULL,
            txid TEXT NOT NULL UNIQUE,
            amount_crypto REAL NOT NULL,
            amount_usd REAL NOT NULL,
            sender_address TEXT NOT NULL,
            confirmed BOOLEAN NOT NULL DEFAULT 0,
            verified_at TEXT,
            FOREIGN KEY (payment_id) REFERENCES crypto_payments(payment_id)
        )
        ''')
        
        # Price history for auto-authorization
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crypto_type TEXT NOT NULL,
            price_usd REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def _price_updater_loop(self):
        """Background thread to update crypto prices every 10 minutes."""
        while self.price_updater_running:
            try:
                self._update_prices()
                self._check_pending_payments_for_auto_auth()
            except Exception as e:
                print(f"Price update error: {e}")
            
            time.sleep(self.PRICE_UPDATE_INTERVAL)
    
    def _update_prices(self):
        """Fetch current BTC and ETH prices from CoinGecko."""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'bitcoin,ethereum',
                'vs_currencies': 'usd'
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            with self.price_lock:
                self.prices['btc'] = data['bitcoin']['usd']
                self.prices['eth'] = data['ethereum']['usd']
                self.last_price_update = datetime.now()
            
            # Log to price history
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            cursor.execute(
                'INSERT INTO price_history (crypto_type, price_usd, timestamp) VALUES (?, ?, ?)',
                ('btc', self.prices['btc'], timestamp)
            )
            cursor.execute(
                'INSERT INTO price_history (crypto_type, price_usd, timestamp) VALUES (?, ?, ?)',
                ('eth', self.prices['eth'], timestamp)
            )
            
            conn.commit()
            conn.close()
            
            print(f"Prices updated: BTC=${self.prices['btc']:,.2f}, ETH=${self.prices['eth']:,.2f}")
            
        except Exception as e:
            print(f"Failed to update prices: {e}")
    
    def get_prices(self) -> Dict[str, float]:
        """Get current crypto prices (thread-safe)."""
        with self.price_lock:
            return self.prices.copy()
    
    def calculate_crypto_amount(self, usd_amount: float, crypto_type: str) -> float:
        """Convert USD to crypto amount.
        
        Args:
            usd_amount: Amount in USD
            crypto_type: 'btc' or 'eth'
        
        Returns:
            Amount in crypto (BTC or ETH)
        """
        prices = self.get_prices()
        
        if prices[crypto_type] == 0:
            raise ValueError(f"Price for {crypto_type} not available yet")
        
        return usd_amount / prices[crypto_type]
    
    def create_payment_session(self, user_id: int, payment_type: str, 
                               crypto_type: str) -> Dict:
        """Create a new crypto payment session.
        
        Args:
            user_id: User ID
            payment_type: 'refill', 'standard_weekly', 'standard_yearly', etc.
            crypto_type: 'btc' or 'eth'
        
        Returns:
            Payment session details
        """
        # Calculate USD amount with discount
        usd_amount = self.PRICING[payment_type]
        if 'yearly' in payment_type:
            usd_amount *= (1 - self.YEARLY_DISCOUNT)
        
        # Calculate crypto amount
        crypto_amount = self.calculate_crypto_amount(usd_amount, crypto_type)
        
        # Get receiver address
        receiver_address = self.receiver_wallets[crypto_type]
        
        # Create payment session (expires in 24 hours)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        created_at = datetime.now().isoformat()
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
        
        cursor.execute('''
        INSERT INTO crypto_payments 
        (user_id, payment_type, crypto_type, amount_usd, amount_crypto, 
         receiver_address, status, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, payment_type, crypto_type, usd_amount, crypto_amount,
              receiver_address, 'pending', created_at, expires_at))
        
        payment_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return {
            'payment_id': payment_id,
            'amount_usd': round(usd_amount, 2),
            'amount_crypto': crypto_amount,
            'crypto_type': crypto_type.upper(),
            'receiver_address': receiver_address,
            'expires_at': expires_at
        }
    
    def verify_transaction(self, payment_id: int, txid: str, 
                          sender_address: str) -> Dict:
        """Verify a blockchain transaction.
        
        Args:
            payment_id: Payment session ID
            txid: Transaction hash
            sender_address: Sender's wallet address
        
        Returns:
            Verification result with status and amounts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get payment details
        cursor.execute(
            'SELECT crypto_type, amount_crypto, receiver_address FROM crypto_payments WHERE payment_id = ?',
            (payment_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return {'success': False, 'error': 'Payment session not found'}
        
        crypto_type, expected_amount, receiver_address = result
        
        # Verify transaction on blockchain
        tx_data = self._verify_on_blockchain(txid, crypto_type)
        
        if not tx_data['success']:
            conn.close()
            return tx_data
        
        # Validate receiver address matches
        if tx_data['receiver'] != receiver_address:
            conn.close()
            return {
                'success': False,
                'error': 'Transaction sent to wrong address'
            }
        
        # Validate sender address matches
        if tx_data['sender'] != sender_address:
            conn.close()
            return {
                'success': False,
                'error': 'Sender address does not match'
            }
        
        # Add increment
        amount_sent = tx_data['amount']
        current_prices = self.get_prices()
        amount_usd = amount_sent * current_prices[crypto_type]
        
        cursor.execute('''
        INSERT INTO payment_increments 
        (payment_id, txid, amount_crypto, amount_usd, sender_address, confirmed, verified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (payment_id, txid, amount_sent, amount_usd, sender_address, 
              tx_data['confirmed'], datetime.now().isoformat()))
        
        # Update sender address in payment session
        cursor.execute(
            'UPDATE crypto_payments SET sender_address = ? WHERE payment_id = ?',
            (sender_address, payment_id)
        )
        
        conn.commit()
        conn.close()
        
        # Check if payment is complete
        payment_status = self.get_payment_status(payment_id)
        
        return {
            'success': True,
            'confirmed': tx_data['confirmed'],
            'amount_sent': amount_sent,
            'amount_usd': round(amount_usd, 2),
            'payment_complete': payment_status['complete'],
            'amount_owed': payment_status['amount_owed']
        }
    
    def _verify_on_blockchain(self, txid: str, crypto_type: str) -> Dict:
        """Verify transaction on blockchain.
        
        Args:
            txid: Transaction hash
            crypto_type: 'btc' or 'eth'
        
        Returns:
            Transaction data or error
        """
        try:
            if crypto_type == 'btc':
                return self._verify_btc_transaction(txid)
            elif crypto_type == 'eth':
                return self._verify_eth_transaction(txid)
            else:
                return {'success': False, 'error': 'Unsupported crypto type'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _verify_btc_transaction(self, txid: str) -> Dict:
        """Verify BTC transaction via Blockstream API."""
        url = f"https://blockstream.info/api/tx/{txid}"
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        tx = response.json()
        
        # Get confirmation status
        confirmed = tx.get('status', {}).get('confirmed', False)
        
        # Find output to our receiver address
        receiver_address = self.receiver_wallets['btc']
        amount_satoshis = 0
        sender_address = None
        
        for vout in tx['vout']:
            if vout.get('scriptpubkey_address') == receiver_address:
                amount_satoshis = vout['value']
                break
        
        # Get sender address from first input
        if tx['vin']:
            vin_txid = tx['vin'][0]['txid']
            vin_vout = tx['vin'][0]['vout']
            
            # Fetch input transaction
            vin_url = f"https://blockstream.info/api/tx/{vin_txid}"
            vin_response = requests.get(vin_url, timeout=15)
            vin_response.raise_for_status()
            vin_tx = vin_response.json()
            
            sender_address = vin_tx['vout'][vin_vout].get('scriptpubkey_address')
        
        amount_btc = amount_satoshis / 100000000  # Convert to BTC
        
        return {
            'success': True,
            'confirmed': confirmed,
            'amount': amount_btc,
            'sender': sender_address,
            'receiver': receiver_address
        }
    
    def _verify_eth_transaction(self, txid: str) -> Dict:
        """Verify ETH transaction via Etherscan API."""
        # Note: Requires ETHERSCAN_API_KEY in environment
        import os
        api_key = os.getenv('ETHERSCAN_API_KEY', 'YourApiKeyToken')
        
        url = "https://api.etherscan.io/api"
        params = {
            'module': 'proxy',
            'action': 'eth_getTransactionByHash',
            'txhash': txid,
            'apikey': api_key
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if 'result' not in data or not data['result']:
            return {'success': False, 'error': 'Transaction not found'}
        
        tx = data['result']
        
        # Get receipt for confirmation status
        receipt_params = {
            'module': 'proxy',
            'action': 'eth_getTransactionReceipt',
            'txhash': txid,
            'apikey': api_key
        }
        
        receipt_response = requests.get(url, params=receipt_params, timeout=15)
        receipt_response.raise_for_status()
        receipt_data = receipt_response.json()
        
        confirmed = receipt_data.get('result') is not None
        
        # Convert wei to ETH
        value_wei = int(tx['value'], 16)
        amount_eth = value_wei / 1e18
        
        sender_address = tx['from']
        receiver_address = tx['to']
        
        return {
            'success': True,
            'confirmed': confirmed,
            'amount': amount_eth,
            'sender': sender_address,
            'receiver': receiver_address
        }
    
    def get_payment_status(self, payment_id: int) -> Dict:
        """Get current status of a payment.
        
        Returns:
            Status including amount paid, owed, and completion
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get payment details
        cursor.execute(
            'SELECT amount_usd, amount_crypto, crypto_type, status FROM crypto_payments WHERE payment_id = ?',
            (payment_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return {'error': 'Payment not found'}
        
        required_usd, required_crypto, crypto_type, status = result
        
        # Get all increments
        cursor.execute(
            'SELECT SUM(amount_usd), SUM(amount_crypto) FROM payment_increments WHERE payment_id = ? AND confirmed = 1',
            (payment_id,)
        )
        increment_result = cursor.fetchone()
        
        conn.close()
        
        paid_usd = increment_result[0] or 0.0
        paid_crypto = increment_result[1] or 0.0
        
        owed_usd = max(0, required_usd - paid_usd)
        owed_crypto = self.calculate_crypto_amount(owed_usd, crypto_type) if owed_usd > 0 else 0
        
        complete = owed_usd <= 0.01  # Within 1 cent tolerance
        
        return {
            'payment_id': payment_id,
            'status': 'complete' if complete else status,
            'complete': complete,
            'required_usd': round(required_usd, 2),
            'required_crypto': required_crypto,
            'paid_usd': round(paid_usd, 2),
            'paid_crypto': paid_crypto,
            'amount_owed': round(owed_usd, 2),
            'crypto_owed': owed_crypto,
            'crypto_type': crypto_type.upper()
        }
    
    def _check_pending_payments_for_auto_auth(self):
        """Check pending payments for auto-authorization on price drop."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all pending payments with partial payment
        cursor.execute('''
        SELECT cp.payment_id, cp.amount_usd, cp.crypto_type, cp.amount_crypto,
               SUM(pi.amount_usd) as paid_usd
        FROM crypto_payments cp
        JOIN payment_increments pi ON cp.payment_id = pi.payment_id
        WHERE cp.status = 'pending' AND pi.confirmed = 1
        GROUP BY cp.payment_id
        HAVING paid_usd < cp.amount_usd
        ''')
        
        pending = cursor.fetchall()
        
        for payment_id, required_usd, crypto_type, original_crypto_amount, paid_usd in pending:
            owed_usd = required_usd - paid_usd
            
            # Check if current price makes their crypto sufficient
            current_prices = self.get_prices()
            
            # Get total crypto paid
            cursor.execute(
                'SELECT SUM(amount_crypto) FROM payment_increments WHERE payment_id = ? AND confirmed = 1',
                (payment_id,)
            )
            paid_crypto = cursor.fetchone()[0] or 0.0
            
            # Calculate current USD value of paid crypto
            current_value_usd = paid_crypto * current_prices[crypto_type]
            
            # If within tolerance, auto-authorize
            if current_value_usd >= required_usd * (1 - self.PRICE_TOLERANCE):
                self._complete_payment(payment_id)
                print(f"✅ Payment {payment_id} auto-authorized due to price drop!")
        
        conn.close()
    
    def _complete_payment(self, payment_id: int):
        """Mark payment as complete and activate subscription."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE crypto_payments SET status = ?, completed_at = ? WHERE payment_id = ?',
            ('complete', datetime.now().isoformat(), payment_id)
        )
        
        # Get payment details to activate subscription
        cursor.execute(
            'SELECT user_id, payment_type FROM crypto_payments WHERE payment_id = ?',
            (payment_id,)
        )
        user_id, payment_type = cursor.fetchone()
        
        conn.commit()
        conn.close()
        
        # Activate subscription/refill (integrate with user_manager)
        print(f"🎉 Payment complete! User {user_id} - {payment_type}")
        
        return True
    
    def get_user_payment_history(self, user_id: int) -> List[Dict]:
        """Get all crypto payments for a user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT payment_id, payment_type, crypto_type, amount_usd, status, created_at, completed_at
        FROM crypto_payments
        WHERE user_id = ?
        ORDER BY created_at DESC
        ''', (user_id,))
        
        payments = []
        for row in cursor.fetchall():
            payments.append({
                'payment_id': row[0],
                'payment_type': row[1],
                'crypto_type': row[2].upper(),
                'amount_usd': round(row[3], 2),
                'status': row[4],
                'created_at': row[5],
                'completed_at': row[6]
            })
        
        conn.close()
        return payments
    
    def stop(self):
        """Stop the price updater thread."""
        self.price_updater_running = False
        if self.price_thread.is_alive():
            self.price_thread.join(timeout=5)
