#!/usr/bin/env python3
"""Unit tests for the SlushAI temp system (HUB pattern).

The temp system follows TizWildin's auth — worker-issued session
tokens, email-based, Google optional not required — so it does NOT
depend on Google. Tests run against UserManager directly with a
throwaway temp database. Run: python3 tests/test_temp_system.py
(exit 0 = all pass). No server needed.

Covers: schema + migrations, temp creation (admin-only shape, bcrypt,
token issued once and stored hashed only), temp token verify/scope/
rotation/revocation, the email_verified gate bypass (at the manager
level: the temp can authenticate while unverified), the daily scrape
(email confirmation -> verified -> discarded in one run), discard
(non-destructive: data preserved, login refused), and the Google
sign-in link-up (get_or_create_user adopts an email_* row instead of
failing UNIQUE users.email; a real Google google_id is never clobbered).
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai3d.utils.user_manager import UserManager

TEMP_EMAIL = 'temp-test@example.com'
TEMP_PASSWORD = 'TempPass123'
FULL_EMAIL = 'full-test@example.com'


class TempSystemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'users.db')
        self.um = UserManager(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _columns(self, table='users'):
        conn = sqlite3.connect(self.db)
        cols = [c[1] for c in conn.execute(
            f'PRAGMA table_info({table})').fetchall()]
        conn.close()
        return cols

    _temp_counter = [0]

    def _make_temp(self, email=TEMP_EMAIL):
        TempSystemTest._temp_counter[0] += 1
        username = f"temp{TempSystemTest._temp_counter[0]:04d}"
        ok, msg, user_id, token = self.um.create_temp_user(
            email, TEMP_PASSWORD, 'Temp Test', username)
        self.assertTrue(ok, msg)
        self.assertIsNotNone(user_id)
        self.assertIsNotNone(token)
        return user_id, token

    # -- schema ------------------------------------------------------------
    def test_schema_has_temp_columns_and_tables(self):
        cols = self._columns()
        for col in ('is_temp', 'temp_verified_at', 'temp_discarded_at'):
            self.assertIn(col, cols, f'users.{col} missing')
        for table in ('temp_api_tokens', 'temp_audit'):
            self.assertIn('id', self._columns(table), f'{table} missing')

    def test_migration_adds_temp_columns_to_old_db(self):
        # A pre-temp database (no is_temp columns) gains them on open.
        old_db = os.path.join(self.tmp.name, 'old.db')
        conn = sqlite3.connect(old_db)
        conn.execute('''CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE, email TEXT UNIQUE NOT NULL,
            password_hash TEXT, name TEXT, username TEXT UNIQUE,
            avatar_url TEXT, email_verified BOOLEAN DEFAULT 0,
            subscription_tier TEXT DEFAULT 'free')''')
        conn.commit()
        conn.close()
        um_old = UserManager(old_db)
        cols = [c[1] for c in sqlite3.connect(old_db).execute(
            'PRAGMA table_info(users)').fetchall()]
        for col in ('is_temp', 'temp_verified_at', 'temp_discarded_at'):
            self.assertIn(col, cols, f'migration missed users.{col}')
        ok, _msg, user_id, token = um_old.create_temp_user(
            'mig@example.com', TEMP_PASSWORD, 'Mig Test', 'migtest')
        self.assertTrue(ok)
        self.assertIsNotNone(token)

    # -- creation ------------------------------------------------------------
    def test_create_temp_marks_temp_free_and_unverified(self):
        user_id, token = self._make_temp()
        row = self.um.get_user_by_id(user_id)
        self.assertEqual(row['is_temp'], 1)
        self.assertEqual(row['subscription_tier'], 'free')
        self.assertEqual(row['email_verified'], 0)
        self.assertTrue(token.startswith(UserManager.TEMP_TOKEN_PREFIX))
        status = self.um.get_temp_status(user_id)
        self.assertEqual(status['state'], 'temp')
        self.assertEqual(status['email_verified'], False)

    def test_create_temp_password_is_bcrypt_hashed_not_plaintext(self):
        user_id, _token = self._make_temp()
        conn = sqlite3.connect(self.db)
        stored = conn.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (user_id,)).fetchone()[0]
        conn.close()
        self.assertNotEqual(stored, TEMP_PASSWORD)
        self.assertTrue(stored.startswith('$2b$'))
        ok, _data = self.um.verify_email_password(TEMP_EMAIL, TEMP_PASSWORD)
        self.assertTrue(ok)

    def test_create_temp_token_stored_hashed_only(self):
        user_id, token = self._make_temp()
        conn = sqlite3.connect(self.db)
        rows = conn.execute(
            'SELECT token_hash FROM temp_api_tokens WHERE user_id = ?',
            (user_id,)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0][0], token)
        import hashlib
        self.assertEqual(
            rows[0][0], hashlib.sha256(token.encode()).hexdigest())

    def test_create_temp_rejects_duplicate_email(self):
        self._make_temp()
        ok, _msg, user_id, token = self.um.create_temp_user(
            TEMP_EMAIL, TEMP_PASSWORD, 'Temp Two', 'temptwo')
        self.assertFalse(ok)
        self.assertIsNone(user_id)
        self.assertIsNone(token)

    # -- token verify / scope / rotation --------------------------------------
    def test_token_verifies_for_its_own_temp(self):
        user_id, token = self._make_temp()
        found = self.um.verify_temp_token(token)
        self.assertIsNotNone(found)
        self.assertEqual(found['id'], user_id)

    def test_token_is_scoped_to_its_own_temp(self):
        _a_id, token_a = self._make_temp('a@example.com')
        b_id, _token_b = self._make_temp('b@example.com')
        found = self.um.verify_temp_token(token_a)
        self.assertEqual(found['id'], _a_id)
        self.assertNotEqual(found['id'], b_id)

    def test_unknown_and_garbage_tokens_fail(self):
        self._make_temp()
        self.assertIsNone(self.um.verify_temp_token('slush_temp_' + '0' * 64))
        self.assertIsNone(self.um.verify_temp_token('not-a-token'))
        self.assertIsNone(self.um.verify_temp_token(''))
        self.assertIsNone(self.um.verify_temp_token(None))

    def test_token_rotation_revokes_the_old_token(self):
        user_id, token1 = self._make_temp()
        token2 = self.um._issue_temp_token(user_id)
        self.assertIsNotNone(token2)
        self.assertNotEqual(token1, token2)
        self.assertIsNone(self.um.verify_temp_token(token1))
        found = self.um.verify_temp_token(token2)
        self.assertIsNotNone(found)
        self.assertEqual(found['id'], user_id)

    def test_token_issue_refuses_non_temp_and_discarded(self):
        ok, _msg, user_id = self.um.create_email_user(
            FULL_EMAIL, TEMP_PASSWORD, 'Full Test', 'fulltest')
        self.assertTrue(ok)
        self.assertIsNone(self.um._issue_temp_token(user_id))
        temp_id, _token = self._make_temp()
        self.um.discard_temp(temp_id)
        self.assertIsNone(self.um._issue_temp_token(temp_id))

    # -- verification + scrape + discard --------------------------------------
    def test_unverified_temp_is_left_alone_by_scrape(self):
        self._make_temp()
        summary = self.um.run_temp_scrape()
        self.assertEqual(summary['checked'], 1)
        self.assertEqual(summary['newly_verified'], 0)
        self.assertEqual(summary['discarded'], 0)

    def test_scrape_verifies_and_discards_on_email_confirmation(self):
        user_id, token = self._make_temp()
        # Confirm the email through the existing 6-digit code flow.
        code = self.um.generate_verification_code(user_id)
        ok, _msg = self.um.verify_email_code(user_id, code)
        self.assertTrue(ok)
        self.assertEqual(self.um.get_user_by_id(user_id)['email_verified'], 1)
        summary = self.um.run_temp_scrape()
        self.assertEqual(summary['newly_verified'], 1)
        self.assertEqual(summary['discarded'], 1)
        status = self.um.get_temp_status(user_id)
        self.assertEqual(status['state'], 'discarded')
        self.assertIsNotNone(status['verified_at'])
        self.assertIsNotNone(status['discarded_at'])
        # Token revoked on discard: it no longer verifies.
        self.assertIsNone(self.um.verify_temp_token(token))

    def test_discard_is_non_destructive_and_idempotent(self):
        user_id, token = self._make_temp()
        ok, _msg = self.um.discard_temp(user_id, reason='test')
        self.assertTrue(ok)
        # The user row still exists (nothing deleted).
        row = self.um.get_user_by_id(user_id)
        self.assertIsNotNone(row)
        self.assertEqual(row['is_temp'], 1)
        self.assertIsNotNone(row['temp_discarded_at'])
        # Token revoked.
        self.assertIsNone(self.um.verify_temp_token(token))
        # Second discard is success (idempotent), not an error.
        ok2, _msg2 = self.um.discard_temp(user_id, reason='test')
        self.assertTrue(ok2)
        # Audit trail records the discard.
        conn = sqlite3.connect(self.db)
        actions = [r[0] for r in conn.execute(
            'SELECT action FROM temp_audit WHERE user_id = ? ORDER BY id',
            (user_id,)).fetchall()]
        conn.close()
        self.assertIn('created', actions)
        self.assertIn('discarded', actions)

    def test_discard_refuses_non_temp(self):
        ok, _msg, user_id = self.um.create_email_user(
            FULL_EMAIL, TEMP_PASSWORD, 'Full Test', 'fulltest')
        self.assertTrue(ok)
        ok, _msg = self.um.discard_temp(user_id)
        self.assertFalse(ok)
        self.assertIsNone(self.um.get_temp_status(user_id))

    def test_mark_verified_refuses_discarded_and_non_temp(self):
        temp_id, _token = self._make_temp()
        self.um.discard_temp(temp_id)
        ok, _msg = self.um.mark_temp_verified(temp_id)
        self.assertFalse(ok)
        _ok, _m, full_id = self.um.create_email_user(
            FULL_EMAIL, TEMP_PASSWORD, 'Full Test', 'fulltest')
        ok, _msg = self.um.mark_temp_verified(full_id)
        self.assertFalse(ok)

    def test_scrape_is_idempotent_across_runs(self):
        user_id, _token = self._make_temp()
        code = self.um.generate_verification_code(user_id)
        self.um.verify_email_code(user_id, code)
        first = self.um.run_temp_scrape()
        self.assertEqual(first['discarded'], 1)
        second = self.um.run_temp_scrape()
        self.assertEqual(second['checked'], 0)
        self.assertEqual(second['discarded'], 0)

    def test_list_temps_shows_derived_state(self):
        a_id, _ta = self._make_temp('a@example.com')
        b_id, _tb = self._make_temp('b@example.com')
        self.um.mark_temp_verified(b_id)
        temps = self.um.list_temps()
        by_id = {t['id']: t for t in temps}
        self.assertEqual(by_id[a_id]['temp_state'], 'temp')
        self.assertEqual(by_id[b_id]['temp_state'], 'verified')
        self.assertEqual(len(temps), 2)

    # -- Google link-up (temp -> full user) ------------------------------------
    def test_google_signin_links_email_temp_row(self):
        temp_id, token = self._make_temp()
        code = self.um.generate_verification_code(temp_id)
        self.um.verify_email_code(temp_id, code)
        self.um.discard_temp(temp_id)
        linked = self.um.get_or_create_user(
            'google-sub-123', TEMP_EMAIL, 'Temp Test', '')
        self.assertEqual(linked['id'], temp_id)
        self.assertEqual(linked['google_id'], 'google-sub-123')
        self.assertEqual(linked['email_verified'], True)
        self.assertEqual(linked['is_temp'], 0)
        # The temp token is revoked by the link-up.
        self.assertIsNone(self.um.verify_temp_token(token))
        # And the linked account signs in via the Google path again.
        again = self.um.get_or_create_user(
            'google-sub-123', TEMP_EMAIL, 'Temp Test', '')
        self.assertEqual(again['id'], temp_id)

    def test_google_signin_does_not_clobber_real_google_row(self):
        # A row whose google_id is a real Google sub is a different
        # person; a sign-in for the same email with another sub must NOT
        # silently link it (the old failure mode is preserved).
        existing = self.um.get_or_create_user(
            'google-sub-AAA', FULL_EMAIL, 'Full Test', '')
        with self.assertRaises(Exception):
            self.um.get_or_create_user(
                'google-sub-BBB', FULL_EMAIL, 'Full Test', '')
        still = self.um.get_user_by_id(existing['id'])
        self.assertEqual(still['google_id'], 'google-sub-AAA')

    # -- OAuth callback link-up (the 2026-11-11 UNIQUE failure) --------------
    def test_google_signin_links_plain_email_row(self):
        # The 2026-11-11 failure: a Google sign-in for an email that
        # already has an email/password row. The old callback shape
        # (get_by_google_id -> create_user) raised UNIQUE constraint
        # failed: users.email and bounced the user to the landing page;
        # get_or_create_user links the row onto the Google identity.
        ok, _msg, email_id = self.um.create_email_user(
            FULL_EMAIL, 'Password1', 'Full Test', 'fulltest')
        self.assertTrue(ok, _msg)
        with self.assertRaises(Exception):
            self.um.create_user(
                'google-sub-123', FULL_EMAIL, 'Full Test', '')
        linked = self.um.get_or_create_user(
            'google-sub-123', FULL_EMAIL, 'Full Test', '')
        self.assertEqual(linked['id'], email_id)
        self.assertEqual(linked['google_id'], 'google-sub-123')
        self.assertEqual(linked['email_verified'], True)

    def test_google_signin_creates_verified_user(self):
        # A fresh Google sign-in creates a verified user: Google
        # attested the email. The old callback's create_user set
        # email_verified=1; the link-up path must preserve that, and a
        # second sign-in must return the same row, not a duplicate.
        user = self.um.get_or_create_user(
            'google-sub-NEW', FULL_EMAIL, 'Full Test', '')
        self.assertEqual(user['email_verified'], True)
        again = self.um.get_or_create_user(
            'google-sub-NEW', FULL_EMAIL, 'Full Test', '')
        self.assertEqual(again['id'], user['id'])
        self.assertEqual(again['email_verified'], True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
