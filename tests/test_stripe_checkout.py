"""Tests for the SlushAI Stripe Checkout integration.

Mocked Stripe, no keys, no network, no real charges. The webhook tests
use a real UserManager against a temp SQLite DB (the dispatch is real;
only the Stripe API is faked).

Run from the project root with the venv Python:
    .venv/bin/python -m unittest tests.test_stripe_checkout -v
(or: .venv/bin/python tests/test_stripe_checkout.py)

What is NOT tested here (waits on Gary connecting Stripe tomorrow):
the end-to-end test-mode run — real test keys, a real Checkout session,
and a real test card (4242 4242 4242 4242) against the live webhook URL.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

# Project root on sys.path (so `src.ai3d...` imports work from anywhere).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Fake `stripe` module, installed BEFORE the manager imports it.
# (The manager does `import stripe` at module import time.)
fake_stripe = mock.MagicMock()
sys.modules['stripe'] = fake_stripe

from src.ai3d.utils.stripe_payment_manager import (
    PLANS,
    StripePaymentManager,
    StripeWebhookError,
    handle_webhook_event,
)
from src.ai3d.utils.user_manager import UserManager

TEST_PRICE_IDS = {
    'standard_weekly': 'price_std_wk',
    'standard_yearly': 'price_std_yr',
    'pro_weekly': 'price_pro_wk',
    'pro_yearly': 'price_pro_yr',
    'refill': 'price_refill',
}


def make_manager(**overrides):
    """A StripePaymentManager with test keys + test Price IDs."""
    kwargs = {
        'secret_key': 'sk_test_fake',
        'webhook_secret': 'whsec_fake',
        'publishable_key': 'pk_test_fake',
        'price_ids': dict(TEST_PRICE_IDS),
    }
    kwargs.update(overrides)
    return StripePaymentManager(**kwargs)


def checkout_event(event_id, user_id, plan, mode, session_id='cs_test_1',
                   subscription_id=None, payment_intent=None):
    """A fake checkout.session.completed event (Stripe's shape)."""
    obj = {
        'id': session_id,
        'mode': mode,
        'client_reference_id': str(user_id),
        'metadata': {'user_id': str(user_id), 'plan': plan},
    }
    if subscription_id:
        obj['subscription'] = subscription_id
    if payment_intent:
        obj['payment_intent'] = payment_intent
    return {'id': event_id, 'type': 'checkout.session.completed',
            'data': {'object': obj}}


def subscription_event(event_id, event_type, user_id, status, price_id,
                       subscription_id='sub_test_1', plan=None):
    """A fake customer.subscription.* event (Stripe's shape)."""
    obj = {
        'id': subscription_id,
        'customer': 'cus_test_1',
        'status': status,
        'metadata': {'user_id': str(user_id)},
        'items': {'data': [{'price': {'id': price_id}}]},
    }
    if plan:
        obj['metadata']['plan'] = plan
    return {'id': event_id, 'type': event_type, 'data': {'object': obj}}


class StripeManagerTest(unittest.TestCase):
    """StripePaymentManager: config, plans, checkout sessions, webhooks."""

    def setUp(self):
        fake_stripe.reset_mock()

    def test_plans_cover_all_pricing_page_keys(self):
        self.assertEqual(set(PLANS), {
            'standard_weekly', 'standard_yearly',
            'pro_weekly', 'pro_yearly', 'refill'})
        for plan_key in ('standard_weekly', 'standard_yearly',
                         'pro_weekly', 'pro_yearly'):
            self.assertEqual(PLANS[plan_key]['mode'], 'subscription')
        self.assertEqual(PLANS['refill']['mode'], 'payment')
        self.assertEqual(PLANS['standard_weekly']['tier'], 'standard')
        self.assertEqual(PLANS['pro_yearly']['tier'], 'pro')
        self.assertTrue(PLANS['standard_yearly']['yearly'])
        self.assertFalse(PLANS['pro_weekly']['yearly'])

    def test_is_configured_false_without_keys(self):
        mgr = StripePaymentManager(secret_key='', webhook_secret='',
                                   publishable_key='', price_ids={})
        self.assertFalse(mgr.is_configured())

    def test_is_configured_true_with_secret_key(self):
        self.assertTrue(make_manager().is_configured())

    def test_create_checkout_session_subscription(self):
        mgr = make_manager()
        session = mock.MagicMock()
        session.url = 'https://checkout.stripe.com/pay/cs_test_1'
        session.id = 'cs_test_1'
        fake_stripe.checkout.Session.create.return_value = session
        result = mgr.create_checkout_session(
            7, 'standard_weekly',
            'http://127.0.0.1:5001/pricing?checkout=success&session_id={CHECKOUT_SESSION_ID}',
            'http://127.0.0.1:5001/pricing?checkout=cancelled')
        self.assertEqual(result, {'url': session.url, 'session_id': 'cs_test_1'})
        _, kwargs = fake_stripe.checkout.Session.create.call_args
        self.assertEqual(kwargs['mode'], 'subscription')
        self.assertEqual(kwargs['line_items'], [{'price': 'price_std_wk', 'quantity': 1}])
        self.assertEqual(kwargs['client_reference_id'], '7')
        self.assertEqual(kwargs['metadata'], {'user_id': '7', 'plan': 'standard_weekly'})
        self.assertEqual(kwargs['subscription_data']['metadata'],
                         {'user_id': '7', 'plan': 'standard_weekly'})
        self.assertNotIn('payment_intent_data', kwargs)
        self.assertIn('{CHECKOUT_SESSION_ID}', kwargs['success_url'])
        self.assertIn('checkout=cancelled', kwargs['cancel_url'])

    def test_create_checkout_session_refill_is_one_time_payment(self):
        mgr = make_manager()
        session = mock.MagicMock()
        session.url = 'https://checkout.stripe.com/pay/cs_test_refill'
        session.id = 'cs_test_refill'
        fake_stripe.checkout.Session.create.return_value = session
        mgr.create_checkout_session(7, 'refill', 'https://x/success', 'https://x/cancel')
        _, kwargs = fake_stripe.checkout.Session.create.call_args
        self.assertEqual(kwargs['mode'], 'payment')
        self.assertEqual(kwargs['line_items'], [{'price': 'price_refill', 'quantity': 1}])
        self.assertEqual(kwargs['payment_intent_data']['metadata'],
                         {'user_id': '7', 'plan': 'refill'})
        self.assertNotIn('subscription_data', kwargs)

    def test_create_checkout_session_unknown_plan(self):
        with self.assertRaises(ValueError):
            make_manager().create_checkout_session(7, 'gold', 'https://x/s', 'https://x/c')

    def test_create_checkout_session_missing_price_id(self):
        mgr = make_manager(price_ids={})
        with self.assertRaisesRegex(RuntimeError, 'STRIPE_PRICE_STANDARD_WEEKLY'):
            mgr.create_checkout_session(7, 'standard_weekly', 'https://x/s', 'https://x/c')

    def test_create_checkout_session_not_configured(self):
        mgr = StripePaymentManager(secret_key='', price_ids=dict(TEST_PRICE_IDS))
        with self.assertRaisesRegex(RuntimeError, 'STRIPE_SECRET_KEY'):
            mgr.create_checkout_session(7, 'standard_weekly', 'https://x/s', 'https://x/c')

    def test_construct_webhook_event_bad_signature(self):
        fake_stripe.Webhook.construct_event.side_effect = Exception('bad signature')
        with self.assertRaises(StripeWebhookError):
            make_manager().construct_webhook_event(b'{}', 't=1,v1=bad')

    def test_construct_webhook_event_no_webhook_secret(self):
        mgr = StripePaymentManager(secret_key='sk_test_fake', webhook_secret='')
        with self.assertRaisesRegex(RuntimeError, 'STRIPE_WEBHOOK_SECRET'):
            mgr.construct_webhook_event(b'{}', 't=1,v1=x')

    def test_plan_for_price_id(self):
        mgr = make_manager()
        self.assertEqual(mgr.plan_for_price_id('price_pro_yr'), 'pro_yearly')
        self.assertEqual(mgr.plan_for_price_id('price_refill'), 'refill')
        self.assertIsNone(mgr.plan_for_price_id('price_nope'))
        self.assertIsNone(mgr.plan_for_price_id(''))


class WebhookDispatchTest(unittest.TestCase):
    """handle_webhook_event against a real UserManager + temp DB."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'users.db')
        self.um = UserManager(self.db_path)
        self.mgr = make_manager()
        self.user_id = self._create_user()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_user(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO users (email, password_hash, name, username, subscription_tier) '
            "VALUES (?, ?, ?, ?, 'free')",
            ('stripe-test@slushai.local', 'x', 'Stripe Test', 'stripetest'))
        conn.commit()
        user_id = conn.execute(
            'SELECT id FROM users WHERE email = ?',
            ('stripe-test@slushai.local',)).fetchone()[0]
        conn.close()
        return user_id

    def _tier(self):
        return self.um.get_user_by_id(self.user_id)['subscription_tier']

    def _quota_limit(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            'SELECT quota_limit FROM weekly_quotas WHERE user_id = ?',
            (self.user_id,)).fetchone()
        conn.close()
        return row[0] if row else None

    def test_checkout_subscription_upgrades_tier_and_quota(self):
        # Start on free (quota row exists at 10).
        self.um.check_quota(self.user_id)
        self.assertEqual(self._quota_limit(), 10)
        event = checkout_event('evt_1', self.user_id, 'standard_weekly',
                               'subscription', subscription_id='sub_test_1')
        status = handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(status, 'processed')
        self.assertEqual(self._tier(), 'standard_weekly')
        self.assertEqual(self._quota_limit(), 40)  # upgrade applies now
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            'SELECT plan_type, billing_cycle, amount_usd, stripe_subscription_id, status '
            'FROM subscriptions WHERE user_id = ?', (self.user_id,)).fetchone()
        conn.close()
        self.assertEqual(row, ('standard', 'weekly', 3.47, 'sub_test_1', 'active'))

    def test_checkout_yearly_plan(self):
        event = checkout_event('evt_yr', self.user_id, 'pro_yearly',
                               'subscription', subscription_id='sub_test_yr')
        handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(self._tier(), 'pro_yearly')
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            'SELECT plan_type, billing_cycle, amount_usd FROM subscriptions '
            'WHERE user_id = ?', (self.user_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 'pro')
        self.assertEqual(row[1], 'yearly')
        self.assertAlmostEqual(row[2], 164.11, places=2)

    def test_checkout_refill_adds_ten_models(self):
        self.um.check_quota(self.user_id)
        event = checkout_event('evt_refill', self.user_id, 'refill', 'payment',
                               session_id='cs_refill_1', payment_intent='pi_test_1')
        status = handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(status, 'processed')
        self.assertEqual(self._quota_limit(), 20)  # 10 free + 10 refill
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            'SELECT amount_usd, models_added, stripe_payment_id FROM refills '
            'WHERE user_id = ?', (self.user_id,)).fetchone()
        conn.close()
        self.assertEqual(row, (1.0, 10, 'pi_test_1'))

    def test_webhook_idempotent_same_event_twice(self):
        self.um.check_quota(self.user_id)
        event = checkout_event('evt_dup', self.user_id, 'refill', 'payment',
                               session_id='cs_dup_1', payment_intent='pi_dup_1')
        self.assertEqual(handle_webhook_event(event, self.um, self.mgr), 'processed')
        self.assertEqual(handle_webhook_event(event, self.um, self.mgr), 'duplicate')
        # Only +10 once, not +20.
        self.assertEqual(self._quota_limit(), 20)
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            'SELECT COUNT(*) FROM refills WHERE user_id = ?',
            (self.user_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_subscription_deleted_downgrades_to_free(self):
        self.um.update_subscription(self.user_id, 'pro', False,
                                    stripe_subscription_id='sub_test_1')
        self.assertEqual(self._tier(), 'pro_weekly')
        event = subscription_event('evt_del', 'customer.subscription.deleted',
                                   self.user_id, 'canceled', 'price_pro_wk')
        status = handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(status, 'processed')
        self.assertEqual(self._tier(), 'free')
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM subscriptions WHERE user_id = ? AND status = 'cancelled'",
            (self.user_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_subscription_updated_syncs_tier_from_price(self):
        event = subscription_event('evt_upd', 'customer.subscription.updated',
                                   self.user_id, 'active', 'price_pro_yr',
                                   subscription_id='sub_test_1')
        handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(self._tier(), 'pro_yearly')

    def test_subscription_updated_unknown_price_uses_metadata_plan(self):
        event = subscription_event('evt_upd2', 'customer.subscription.updated',
                                   self.user_id, 'active', 'price_unknown',
                                   subscription_id='sub_test_1', plan='standard_yearly')
        handle_webhook_event(event, self.um, self.mgr)
        self.assertEqual(self._tier(), 'standard_yearly')

    def test_get_user_id_by_stripe_subscription_id(self):
        self.um.update_subscription(self.user_id, 'standard', False,
                                    stripe_subscription_id='sub_test_1')
        found = self.um.get_user_id_by_stripe_subscription_id('sub_test_1')
        self.assertEqual(found, self.user_id)
        self.assertIsNone(self.um.get_user_id_by_stripe_subscription_id('sub_nope'))
        self.assertIsNone(self.um.get_user_id_by_stripe_subscription_id(''))

    def test_record_stripe_event(self):
        self.assertTrue(self.um.record_stripe_event('evt_a', 'checkout.session.completed'))
        self.assertFalse(self.um.record_stripe_event('evt_a', 'checkout.session.completed'))
        self.assertTrue(self.um.has_stripe_event('evt_a'))
        self.assertFalse(self.um.has_stripe_event('evt_b'))


class UpdateSubscriptionTest(unittest.TestCase):
    """user_manager.update_subscription (also the crypto verify route's call)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'users.db')
        self.um = UserManager(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO users (email, password_hash, name, username, subscription_tier) '
            "VALUES (?, ?, ?, ?, 'free')",
            ('sub-test@slushai.local', 'x', 'Sub Test', 'subtest'))
        conn.commit()
        self.user_id = conn.execute(
            'SELECT id FROM users WHERE email = ?',
            ('sub-test@slushai.local',)).fetchone()[0]
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_invalid_tier(self):
        ok, msg = self.um.update_subscription(self.user_id, 'gold', False)
        self.assertFalse(ok)
        self.assertIn('Invalid tier', msg)

    def test_unknown_user(self):
        ok, msg = self.um.update_subscription(99999, 'standard', False)
        self.assertFalse(ok)
        self.assertEqual(msg, 'User not found')

    def test_upgrade_bumps_current_week_quota(self):
        self.um.check_quota(self.user_id)  # free row, limit 10
        ok, msg = self.um.update_subscription(self.user_id, 'standard', False)
        self.assertTrue(ok)
        self.assertEqual(msg, 'Subscription updated to standard_weekly')
        self.assertEqual(
            self.um.get_user_by_id(self.user_id)['subscription_tier'],
            'standard_weekly')
        conn = sqlite3.connect(self.db_path)
        limit = conn.execute(
            'SELECT quota_limit FROM weekly_quotas WHERE user_id = ?',
            (self.user_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(limit, 40)

    def test_downgrade_to_free_does_not_lower_current_week_limit(self):
        self.um.check_quota(self.user_id)
        self.um.update_subscription(self.user_id, 'pro', False)
        conn = sqlite3.connect(self.db_path)
        limit = conn.execute(
            'SELECT quota_limit FROM weekly_quotas WHERE user_id = ?',
            (self.user_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(limit, 120)
        ok, _ = self.um.update_subscription(self.user_id, 'free', False)
        self.assertTrue(ok)
        self.assertEqual(
            self.um.get_user_by_id(self.user_id)['subscription_tier'], 'free')
        conn = sqlite3.connect(self.db_path)
        limit = conn.execute(
            'SELECT quota_limit FROM weekly_quotas WHERE user_id = ?',
            (self.user_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(limit, 120)  # current week keeps the higher limit

    def test_crypto_verify_signature_still_works(self):
        # The crypto route calls update_subscription(user_id, 'standard',
        # 'yearly' in payment_type) — exactly this 3-arg shape.
        ok, msg = self.um.update_subscription(self.user_id, 'standard', True)
        self.assertTrue(ok)
        self.assertEqual(
            self.um.get_user_by_id(self.user_id)['subscription_tier'],
            'standard_yearly')


if __name__ == '__main__':
    unittest.main(verbosity=2)
