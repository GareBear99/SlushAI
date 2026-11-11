"""Stripe Checkout + webhook handling for SlushAI.

Card payments sit alongside the existing crypto flow (BTC/ETH) — Stripe is
a new rail, not a replacement. Everything here reads from environment
variables; with no keys set the manager reports ``is_configured() == False``
and the routes return 503, so the app starts and runs normally without
Stripe. Real keys + Price IDs come from Gary's Stripe Dashboard (test mode
first) after he connects Stripe — nothing here invents them.

Flow:
  1. Pricing page -> POST /api/stripe/create-checkout-session {plan}
     -> Stripe Checkout URL (the user is redirected there; no Stripe.js).
  2. Stripe -> POST /api/stripe/webhook (signature-verified) ->
     handle_webhook_event() -> upgrade tier / refill / downgrade.
  3. Success returns to /pricing?checkout=success, cancel to
     /pricing?checkout=cancelled.

Plans (keys match user_manager.SUBSCRIPTION_PLANS):
  standard_weekly $3.47/wk (40/wk), standard_yearly $72/yr (40/wk),
  pro_weekly $7.89/wk (120/wk), pro_yearly $164/yr (120/wk),
  refill $1 one-time (+10 models, max 10/week).
"""

import logging
import os
from typing import Dict, Optional

try:
    import stripe
except ImportError:
    # stripe not installed yet (requirements.txt pins stripe==16.1.0).
    # The manager still imports; is_configured() is False and every
    # Stripe call raises a clear error instead of crashing app startup.
    stripe = None

logger = logging.getLogger(__name__)

# plan_key -> Stripe Price env var, Checkout mode, tier, yearly flag.
# The tier/yearly pair is what user_manager.update_subscription() takes;
# the price itself is defined in Stripe (the Price ID), so no amounts
# live here.
PLANS = {
    'standard_weekly': {
        'price_env': 'STRIPE_PRICE_STANDARD_WEEKLY',
        'mode': 'subscription', 'tier': 'standard', 'yearly': False,
    },
    'standard_yearly': {
        'price_env': 'STRIPE_PRICE_STANDARD_YEARLY',
        'mode': 'subscription', 'tier': 'standard', 'yearly': True,
    },
    'pro_weekly': {
        'price_env': 'STRIPE_PRICE_PRO_WEEKLY',
        'mode': 'subscription', 'tier': 'pro', 'yearly': False,
    },
    'pro_yearly': {
        'price_env': 'STRIPE_PRICE_PRO_YEARLY',
        'mode': 'subscription', 'tier': 'pro', 'yearly': True,
    },
    'refill': {
        'price_env': 'STRIPE_PRICE_REFILL',
        'mode': 'payment', 'tier': None, 'yearly': False,
    },
}


class StripeWebhookError(Exception):
    """A webhook payload failed signature verification (or is malformed)."""


class StripePaymentManager:
    """Stripe Checkout sessions + webhook verification for SlushAI."""

    def __init__(self, secret_key=None, webhook_secret=None,
                 publishable_key=None, price_ids=None):
        self.secret_key = secret_key or os.environ.get('STRIPE_SECRET_KEY', '')
        self.webhook_secret = webhook_secret or os.environ.get('STRIPE_WEBHOOK_SECRET', '')
        self.publishable_key = publishable_key or os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
        self.price_ids = dict(price_ids) if price_ids else {}
        # Any price not passed in falls back to its env var.
        for plan_key, spec in PLANS.items():
            if not self.price_ids.get(plan_key):
                self.price_ids[plan_key] = os.environ.get(spec['price_env'], '')
        if stripe is not None and self.secret_key:
            stripe.api_key = self.secret_key

    def is_configured(self) -> bool:
        """True when a secret key is set AND the stripe lib is installed."""
        return bool(self.secret_key) and stripe is not None

    def get_price_id(self, plan: str) -> Optional[str]:
        """Stripe Price ID for a plan key, or None if not set / unknown."""
        if plan not in PLANS:
            return None
        return self.price_ids.get(plan) or None

    def plan_for_price_id(self, price_id: str) -> Optional[str]:
        """Plan key for a Stripe Price ID (subscription sync), or None."""
        if not price_id:
            return None
        for plan_key, pid in self.price_ids.items():
            if pid and pid == price_id:
                return plan_key
        return None

    def create_checkout_session(self, user_id: int, plan: str,
                                success_url: str, cancel_url: str) -> Dict[str, str]:
        """Create a Stripe Checkout session; returns {'url', 'session_id'}.

        Subscription plans use mode='subscription' (recurring); the refill
        uses mode='payment' (one-time). The user/plan travel in metadata
        (and subscription_data.metadata for subscriptions) so the webhook
        can apply the purchase without trusting the client.
        """
        if stripe is None:
            raise RuntimeError(
                'stripe package is not installed (add stripe to requirements '
                'and install it)')
        if not self.secret_key:
            raise RuntimeError(
                'STRIPE_SECRET_KEY is not set — Stripe is not configured')
        spec = PLANS.get(plan)
        if spec is None:
            raise ValueError(f'Unknown plan: {plan!r}')
        price_id = self.get_price_id(plan)
        if not price_id:
            raise RuntimeError(
                f'No Stripe Price ID for plan {plan!r} — set '
                f'{spec["price_env"]} in .env (create the product in the '
                'Stripe Dashboard first)')

        metadata = {'user_id': str(user_id), 'plan': plan}
        kwargs = {
            'mode': spec['mode'],
            'line_items': [{'price': price_id, 'quantity': 1}],
            'client_reference_id': str(user_id),
            'metadata': metadata,
            'success_url': success_url,
            'cancel_url': cancel_url,
        }
        if spec['mode'] == 'subscription':
            kwargs['subscription_data'] = {'metadata': metadata}
        else:  # one-time payment (refill)
            kwargs['payment_intent_data'] = {'metadata': metadata}

        session = stripe.checkout.Session.create(**kwargs)
        return {'url': session.url, 'session_id': session.id}

    def construct_webhook_event(self, payload, sig_header):
        """Verify a webhook payload; returns the parsed event dict.

        Raises StripeWebhookError on a bad signature / malformed payload,
        and RuntimeError when the webhook secret (or the stripe lib) is
        missing — the route fails CLOSED (never processes unverified).
        """
        if stripe is None:
            raise RuntimeError('stripe package is not installed')
        if not self.webhook_secret:
            raise RuntimeError(
                'STRIPE_WEBHOOK_SECRET is not set — refusing to process '
                'an unverified webhook')
        try:
            return stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception as e:
            raise StripeWebhookError(str(e)) from e


def handle_webhook_event(event, user_manager, stripe_manager, log=None):
    """Apply a VERIFIED Stripe event to the DB (idempotent).

    Returns 'processed', 'duplicate', or 'ignored'. Raises on a handler
    failure — the caller returns 500 so Stripe retries (the dispatch is
    idempotent, so a retry is safe). Call only after signature
    verification; this function never verifies anything itself.
    """
    log = log or logger
    event_id = event.get('id', '') if isinstance(event, dict) else ''
    event_type = event.get('type', '') if isinstance(event, dict) else ''
    if event_id and user_manager.has_stripe_event(event_id):
        log.info(f'Stripe webhook {event_type} {event_id} already processed — skipping')
        return 'duplicate'
    _dispatch_stripe_event(event, user_manager, stripe_manager, log)
    if event_id:
        user_manager.record_stripe_event(event_id, event_type)
    return 'processed'


def _dispatch_stripe_event(event, user_manager, stripe_manager, log):
    """Route one verified event to the right DB change. Idempotent."""
    event_type = event.get('type', '')
    obj = (event.get('data') or {}).get('object') or {}

    if event_type == 'checkout.session.completed':
        _handle_checkout_completed(obj, user_manager, log)
        return

    if event_type in ('customer.subscription.updated', 'customer.subscription.deleted'):
        _handle_subscription_change(event_type, obj, user_manager, stripe_manager, log)
        return

    if event_type == 'invoice.payment_failed':
        log.warning(
            f"Stripe invoice payment failed for customer {obj.get('customer')} "
            f"(invoice {obj.get('id')})")
        return

    log.info(f'Stripe webhook: unhandled event type {event_type}')


def _event_user_id(obj, user_manager, log):
    """Resolve the user for a webhook object: metadata.user_id first,
    then client_reference_id, then the subscriptions table (by Stripe
    subscription ID). Returns an int user_id or None."""
    metadata = obj.get('metadata') or {}
    for raw in (metadata.get('user_id'), obj.get('client_reference_id')):
        if raw:
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
    sub_id = obj.get('subscription') or obj.get('id')
    if sub_id:
        user_id = user_manager.get_user_id_by_stripe_subscription_id(sub_id)
        if user_id:
            return user_id
    return None


def _handle_checkout_completed(session, user_manager, log):
    """checkout.session.completed: subscription -> upgrade tier;
    payment (refill) -> +10 models. Idempotent (refills are guarded by
    the recorded stripe_payment_id)."""
    user_id = _event_user_id(session, user_manager, log)
    if not user_id:
        log.warning(
            'Stripe checkout completed with no resolvable user '
            f"(session {session.get('id')}) — no tier change applied")
        return
    metadata = session.get('metadata') or {}
    plan = metadata.get('plan') or ''
    mode = session.get('mode')

    if mode == 'subscription':
        spec = PLANS.get(plan)
        if not spec:
            log.warning(f'Stripe checkout completed with unknown plan: {plan!r}')
            return
        ok, msg = user_manager.update_subscription(
            user_id, spec['tier'], spec['yearly'],
            stripe_subscription_id=session.get('subscription'))
        log.info(f'Stripe subscription checkout: user {user_id} -> {plan} ({msg})')
        return

    if mode == 'payment' and plan == 'refill':
        payment_intent = session.get('payment_intent') or session.get('id')
        if payment_intent and user_manager.has_stripe_refill(payment_intent):
            log.info(f'Stripe refill {payment_intent} already applied — skipping')
            return
        ok, msg = user_manager.purchase_refill(
            user_id, stripe_payment_id=payment_intent)
        log.info(f'Stripe refill checkout: user {user_id} ({msg})')
        return

    log.info(f'Stripe checkout completed (mode={mode}, plan={plan!r}) — no action')


def _handle_subscription_change(event_type, sub, user_manager, stripe_manager, log):
    """customer.subscription.updated/deleted: sync the tier from the
    subscription's status + price (or its metadata plan as a fallback).
    A deleted / cancelled / unpaid subscription drops the user to free."""
    user_id = _event_user_id(sub, user_manager, log)
    if not user_id:
        log.warning(
            f'Stripe subscription {event_type} with no resolvable user '
            f"(subscription {sub.get('id')}) — no tier change applied")
        return

    if (event_type == 'customer.subscription.deleted'
            or sub.get('status') in ('canceled', 'unpaid', 'incomplete_expired')):
        ok, msg = user_manager.update_subscription(user_id, 'free', False)
        log.info(f'Stripe subscription ended: user {user_id} -> free ({msg})')
        return

    # Active / trialing / past_due: sync the tier from the price.
    items = (sub.get('items') or {}).get('data') or []
    price_id = items[0].get('price', {}).get('id') if items else None
    plan = stripe_manager.plan_for_price_id(price_id) if price_id else None
    if not plan:
        plan = (sub.get('metadata') or {}).get('plan') or ''
    spec = PLANS.get(plan)
    if not spec:
        log.warning(
            f'Stripe subscription updated with unknown price {price_id} '
            f'/ plan {plan!r} — no tier change applied')
        return
    ok, msg = user_manager.update_subscription(
        user_id, spec['tier'], spec['yearly'],
        stripe_subscription_id=sub.get('id'))
    log.info(f'Stripe subscription updated: user {user_id} -> {plan} ({msg})')
