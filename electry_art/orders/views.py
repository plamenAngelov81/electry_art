from datetime import timedelta, date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import secrets

import stripe
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction, connection
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.urls import reverse_lazy, reverse
from django.views import View, generic
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from .models import Order, OrderItem, OrderItemStatus
from .forms import CheckoutForm, GuestCheckoutForm
from electry_art.cart.models import Cart
from ..cart.utils import SessionCart
from ..products.models import Product
from electry_art.cart.signals import checkout_completed
import logging
from electry_art.core.audit import audit_event, Actor, mask_email
from ..products.product_mixins.product_mixins import SuperuserRequiredMixin

log = logging.getLogger("electryart.orders")
stripe.api_key = settings.STRIPE_SECRET_KEY

# All product and order prices are denominated in EUR.
STRIPE_CURRENCY = "eur"


def eur_to_cents(price):
    """Convert an EUR price to Stripe's integer minor units (cents)."""
    return int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_order_serial(order_id):
    # ORD-20260106-000154
    return f"ORD{timezone.now().strftime('%Y%m%d')}{order_id:06d}"



# A checkout token is scoped to one browser checkout attempt, not to a product
# combination. A fresh GET after a paid order starts a new legitimate purchase.
CHECKOUT_TOKEN_SESSION_KEY = "electryart_checkout_attempt_token"


def checkout_token(request, *, new_if_paid=False, cart_signature=None):
    token = request.session.get(CHECKOUT_TOKEN_SESSION_KEY)
    if cart_signature is not None and request.session.get("electryart_checkout_cart_signature") != cart_signature:
        token = None
        request.session["electryart_checkout_cart_signature"] = cart_signature
    if token and new_if_paid and Order.objects.filter(
        checkout_attempt_key=token, is_paid=True
    ).exists():
        token = None
    if not token:
        token = secrets.token_hex(32)
        request.session[CHECKOUT_TOKEN_SESSION_KEY] = token
    return token


def checkout_fingerprint(items, details):
    # Sort items so queryset order does not affect the identity of a snapshot.
    data = {
        "items": sorted((int(pid), int(qty)) for pid, qty in items),
        "details": details,
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def lock_checkout_attempt(token):
    """Serialize concurrent requests with the same token on PostgreSQL."""
    if connection.vendor == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
        if lock_id >= 2**63:
            lock_id -= 2**64
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])


def existing_checkout_response(token, fingerprint):
    # The unique database constraint serializes concurrent requests for the
    # same token; the first request's transaction commits before the next reads.
    existing = Order.objects.select_for_update().filter(
        checkout_attempt_key=token
    ).first()
    if existing is None:
        return None
    if existing.checkout_cart_fingerprint != fingerprint:
        raise ValidationError(
            "The cart or delivery address has changed. Please start checkout again."
        )
    if existing.stripe_checkout_url and not existing.is_paid:
        return redirect(existing.stripe_checkout_url, permanent=False)
    if existing.is_paid and existing.stripe_checkout_session_id:
        return redirect(
            reverse("stripe_payment_success")
            + "?session_id=" + existing.stripe_checkout_session_id
        )
    # Another request may currently be creating the Stripe session.
    # Do not hold PostgreSQL locks while waiting for Stripe.
    if existing.checkout_processing_claim:
        age = (timezone.now() - existing.checkout_processing_started_at) if existing.checkout_processing_started_at else timedelta.max
        if age < timedelta(minutes=5):
            return HttpResponse("Your payment is being prepared. Please try again shortly.", status=409)
        if age > timedelta(minutes=20):
            return HttpResponse("A previous payment attempt could not be completed. Please contact support.", status=409)
    return existing


def release_checkout_claim(order_id, claim):
    # Conditional update prevents an older worker from clearing a newer claim.
    Order.objects.filter(pk=order_id, checkout_processing_claim=claim).update(
        checkout_processing_claim="", checkout_processing_started_at=None
    )


def stripe_items_for_order(order):
    result = []
    for item in order.items.all():
        result.append({
            "price_data": {
                "currency": STRIPE_CURRENCY,
                "product_data": {"name": item.product_name},
                "unit_amount": eur_to_cents(item.price),
            },
            "quantity": item.quantity,
        })
    return result


class CheckoutView(LoginRequiredMixin, View):
    @staticmethod
    def get(request):
        cart = Cart.objects.filter(user=request.user).first()

        if not cart or not cart.items.exists():
            return redirect("cart_view")

        if not request.user.addresses.exists():
            return redirect("address_add")

        checkout_token(
            request, new_if_paid=True,
            cart_signature=checkout_fingerprint(
                cart.items.values_list("product_id", "quantity"), {}
            ),
        )
        form = CheckoutForm(user=request.user)

        return render(request, "orders/checkout.html", {
            "form": form,
            "cart": cart,
        })

    @staticmethod
    def post(request):
        actor = Actor(type="user", id=getattr(request.user, "pk", None))
        rid = getattr(request, "request_id", None)

        log.info("CHECKOUT_STARTED user_id=%s request_id=%s", actor.id, rid)
        audit_event("CHECKOUT_STARTED", actor=actor, request_id=rid)

        cart = (
            Cart.objects
            .filter(user=request.user)
            .prefetch_related("items__product")
            .first()
        )

        if not cart or not cart.items.exists():
            log.info("CHECKOUT_EMPTY_CART user_id=%s request_id=%s", actor.id, rid)
            audit_event("CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
            return redirect("cart_view")

        if not request.user.addresses.exists():
            return redirect("address_add")

        form = CheckoutForm(request.POST, user=request.user)

        if not form.is_valid():
            bad_fields = list(form.errors.keys())

            log.info(
                "CHECKOUT_VALIDATION_FAILED user_id=%s request_id=%s fields=%s",
                actor.id, rid, bad_fields
            )
            audit_event(
                "CHECKOUT_VALIDATION_FAILED",
                actor=actor,
                request_id=rid,
                extra={"fields": bad_fields},
            )

            return render(request, "orders/checkout.html", {
                "form": form,
                "cart": cart,
            })

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            token = checkout_token(request)
            snapshot_items = list(cart.items.values_list("product_id", "quantity"))
            selected_address = form.cleaned_data["delivery_address"]
            fingerprint = checkout_fingerprint(
                snapshot_items,
                {"address_id": selected_address.pk, "user_id": request.user.pk},
            )

            with transaction.atomic():
                lock_checkout_attempt(token)
                previous = existing_checkout_response(token, fingerprint)
                if previous is not None and not isinstance(previous, Order):
                    return previous
                log.info("ORDER_CREATE_STARTED user_id=%s request_id=%s", actor.id, rid)
                audit_event("ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                items = list(cart.items.select_related("product"))
                items_count = len(items)

                if not items:
                    log.info("CHECKOUT_EMPTY_CART user_id=%s request_id=%s", actor.id, rid)
                    audit_event("CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
                    return redirect("cart_view")

                product_ids = [it.product_id for it in items if it.product_id]

                products = (
                    Product.objects
                    .select_for_update()
                    .filter(id__in=product_ids)
                    .only("id", "name", "price", "is_available")
                )

                products_map = {p.id: p for p in products}

                unavailable_products = []
                missing_products = []

                for it in items:
                    product = products_map.get(it.product_id)

                    if product is None:
                        missing_products.append({"product_id": it.product_id})
                        continue

                    if not product.is_available:
                        unavailable_products.append({
                            "product_id": product.id,
                            "requested": it.quantity,
                            "is_available": product.is_available,
                        })

                if missing_products:
                    log.info(
                        "CHECKOUT_PRODUCTS_MISSING user_id=%s request_id=%s details=%s",
                        actor.id, rid, missing_products
                    )
                    audit_event(
                        "CHECKOUT_PRODUCTS_MISSING",
                        actor=actor,
                        request_id=rid,
                        extra={"details": missing_products},
                    )
                    raise ValidationError("Some products are no longer available.")

                if unavailable_products:
                    log.info(
                        "CHECKOUT_UNAVAILABLE_PRODUCTS user_id=%s request_id=%s details=%s",
                        actor.id, rid, unavailable_products
                    )
                    audit_event(
                        "CHECKOUT_UNAVAILABLE_PRODUCTS",
                        actor=actor,
                        request_id=rid,
                        extra={"details": unavailable_products},
                    )
                    raise ValidationError("One or more products are no longer offered.")

                selected_address = form.cleaned_data["delivery_address"]

                if previous is None:
                    order = Order.objects.create(
                        user=request.user,
                        full_name=request.user.get_name or request.user.username,
                        phone=selected_address.phone_num,
                        address=selected_address.get_full_address,
                        user_email=request.user.email or None,
                        is_paid=False,
                        checkout_attempt_key=token,
                        checkout_cart_fingerprint=fingerprint,
                        payment_provider="stripe",
                    )

                    order.order_serial_number = build_order_serial(order.id)
                    order.save(update_fields=["order_serial_number"])

                    stripe_line_items = []
                    stripe_expected_amount = 0

                    for it in items:
                        product = products_map[it.product_id]

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            product_name=product.name,
                            quantity=it.quantity,
                            price=product.price,
                        )

                        stripe_line_items.append({
                            "price_data": {
                                "currency": STRIPE_CURRENCY,
                                "product_data": {
                                    "name": product.name,
                                },
                                "unit_amount": eur_to_cents(product.price),
                            },
                            "quantity": it.quantity,
                        })
                        stripe_expected_amount += eur_to_cents(product.price) * it.quantity

                else:
                    order = previous
                    stripe_line_items = []
                    stripe_expected_amount = 0
                    for item in order.items.all():
                        unit_amount = eur_to_cents(item.price)
                        stripe_line_items.append({
                            "price_data": {
                                "currency": STRIPE_CURRENCY,
                                "product_data": {"name": item.product_name},
                                "unit_amount": unit_amount,
                            },
                            "quantity": item.quantity,
                        })
                        stripe_expected_amount += unit_amount * item.quantity

                # Persist the exact Stripe amount before the external request.
                # All row locks are released when this transaction commits.
                order.stripe_expected_amount = stripe_expected_amount
                order.stripe_expected_currency = STRIPE_CURRENCY
                claim = secrets.token_hex(16)
                order.checkout_processing_claim = claim
                order.checkout_processing_started_at = timezone.now()
                order.save(update_fields=[
                    "stripe_expected_amount", "stripe_expected_currency",
                    "checkout_processing_claim", "checkout_processing_started_at",
                ])

            # IMPORTANT: Stripe network call is outside transaction.atomic().
            # The claim was committed, so a concurrent POST cannot start another
            # request for the same checkout attempt.
            success_url = request.build_absolute_uri(
                reverse("stripe_payment_success")
            ) + "?session_id={CHECKOUT_SESSION_ID}"
            cancel_url = request.build_absolute_uri(
                reverse("stripe_payment_cancel", kwargs={"order_id": order.pk})
            )
            stripe_line_items = stripe_items_for_order(order)
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=stripe_line_items,
                client_reference_id=str(order.pk),
                customer_email=order.user_email,
                metadata={
                    "order_id": str(order.pk),
                    "order_serial_number": order.order_serial_number,
                    "user_id": str(request.user.pk),
                },
                success_url=success_url,
                cancel_url=cancel_url,
                idempotency_key="electryart-checkout-" + token,
            )
            # Persist Stripe's response in a separate short transaction.
            with transaction.atomic():
                saved = Order.objects.select_for_update().get(pk=order.pk)
                if saved.checkout_processing_claim != claim:
                    raise ValidationError("The payment attempt has been superseded. Please try again.")
                saved.stripe_checkout_url = session.url
                saved.stripe_checkout_session_id = session.id
                saved.checkout_processing_claim = ""
                saved.checkout_processing_started_at = None
                saved.save(update_fields=[
                    "stripe_checkout_session_id", "stripe_checkout_url",
                    "checkout_processing_claim", "checkout_processing_started_at",
                ])
            log.info(
                "STRIPE_CHECKOUT_SESSION_CREATED order_id=%s session_id=%s request_id=%s",
                order.pk, session.id, rid,
            )

        except ValidationError as exc:
            form.add_error(None, str(exc))
            return render(request, "orders/checkout.html", {
                "form": form,
                "cart": cart,
            })

        except stripe.error.StripeError as exc:
            if "order" in locals() and "claim" in locals():
                release_checkout_claim(order.pk, claim)
            log.exception(
                "STRIPE_CHECKOUT_SESSION_CREATE_FAILED user_id=%s request_id=%s error=%s",
                actor.id,
                rid,
                str(exc),
            )
            audit_event(
                "STRIPE_CHECKOUT_SESSION_CREATE_FAILED",
                actor=actor,
                request_id=rid,
                extra={"error": str(exc)},
            )
            form.add_error(None, f"Stripe error: {exc}")

            return render(request, "orders/checkout.html", {
                "form": form,
                "cart": cart,
            })

        except Exception:  # noqa: BLE001
            if "order" in locals() and "claim" in locals():
                release_checkout_claim(order.pk, claim)
            log.exception("ORDER_CREATE_FAILED user_id=%s request_id=%s", actor.id, rid)
            audit_event("ORDER_CREATE_FAILED", actor=actor, request_id=rid)
            raise

        return redirect(session.url, permanent=False)


class OrderHistoryView(LoginRequiredMixin, generic.ListView):
    model = Order
    template_name = 'orders/history.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return (Order.objects
                .filter(user=self.request.user)
                .prefetch_related("items__product")
                .order_by("-created_at")[:10]
        )


class OrderDetailView(LoginRequiredMixin, generic.DetailView):
    model = Order
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        qs = (super().get_queryset().prefetch_related("items__product"))

        """Staff/superuser can see all orders"""
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs

        """Ordinary users orders"""
        return qs.filter(user=self.request.user)


class GuestCheckoutView(View):
    @staticmethod
    def _build_cart_context(cart):
        items = list(cart.items())
        if not items:
            return None

        product_ids = [int(pid) for pid, _ in items]
        products = Product.objects.in_bulk(product_ids)

        cart_items = []
        total = 0
        for pid, quantity in items:
            pid = int(pid)
            quantity = int(quantity)
            product = products.get(pid)
            if not product:
                continue

            item_total = product.price * quantity
            cart_items.append({
                "product": product,
                "quantity": quantity,
                "total": item_total,
            })
            total += item_total

        return {
            "items": items,
            "products": products,
            "cart_items": cart_items,
            "total": total,
        }

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("checkout")

        cart = SessionCart(request)
        ctx = self._build_cart_context(cart)
        if not ctx:
            return redirect("cart_view")

        checkout_token(
            request, new_if_paid=True,
            cart_signature=checkout_fingerprint(ctx["items"], {}),
        )
        form = GuestCheckoutForm()
        return render(request, "orders/guest_checkout.html", {
            "form": form,
            "cart_items": ctx["cart_items"],
            "total": ctx["total"],
        })

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("checkout")

        actor = Actor(type="guest", id=None)
        rid = getattr(request, "request_id", None)

        log.info("GUEST_CHECKOUT_STARTED request_id=%s", rid)
        audit_event("GUEST_CHECKOUT_STARTED", actor=actor, request_id=rid)

        cart = SessionCart(request)
        ctx = self._build_cart_context(cart)
        if not ctx:
            log.info("GUEST_CHECKOUT_EMPTY_CART request_id=%s", rid)
            audit_event("GUEST_CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
            return redirect("cart_view")

        form = GuestCheckoutForm(request.POST)
        if not form.is_valid():
            bad_fields = list(form.errors.keys())

            log.info(
                "GUEST_CHECKOUT_VALIDATION_FAILED request_id=%s fields=%s",
                rid,
                bad_fields,
            )
            audit_event(
                "GUEST_CHECKOUT_VALIDATION_FAILED",
                actor=actor,
                request_id=rid,
                extra={"fields": bad_fields},
            )

            return render(request, "orders/guest_checkout.html", {
                "form": form,
                "cart_items": ctx["cart_items"],
                "total": ctx["total"],
            })

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            token = checkout_token(request)
            fingerprint = checkout_fingerprint(
                ctx["items"],
                {key: form.cleaned_data[key] for key in
                 ("full_name", "phone", "email", "address")},
            )

            with transaction.atomic():
                lock_checkout_attempt(token)
                previous = existing_checkout_response(token, fingerprint)
                if previous is not None and not isinstance(previous, Order):
                    return previous
                log.info("GUEST_ORDER_CREATE_STARTED request_id=%s", rid)
                audit_event("GUEST_ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                items = list(ctx["items"])

                unavailable_products = []
                missing_products = []

                product_ids = [int(pid) for pid, _ in items]
                locked_products = (
                    Product.objects.select_for_update()
                    .filter(id__in=product_ids)
                    .only("id", "name", "price", "is_available")
                )
                locked_products_map = {p.id: p for p in locked_products}

                for pid, quantity in items:
                    pid = int(pid)
                    quantity = int(quantity)

                    product = locked_products_map.get(pid)
                    if product is None:
                        missing_products.append({"product_id": pid})
                        continue

                    if not product.is_available:
                        unavailable_products.append({
                            "product_id": product.id,
                            "requested": quantity,
                            "is_available": product.is_available,
                        })

                if missing_products:
                    log.info(
                        "GUEST_CHECKOUT_PRODUCTS_MISSING request_id=%s details=%s",
                        rid,
                        missing_products,
                    )
                    audit_event(
                        "GUEST_CHECKOUT_PRODUCTS_MISSING",
                        actor=actor,
                        request_id=rid,
                        extra={"details": missing_products},
                    )
                    raise ValidationError("Some products are no longer available.")

                if unavailable_products:
                    log.info(
                        "GUEST_CHECKOUT_UNAVAILABLE_PRODUCTS request_id=%s details=%s",
                        rid,
                        unavailable_products,
                    )
                    audit_event(
                        "GUEST_CHECKOUT_UNAVAILABLE_PRODUCTS",
                        actor=actor,
                        request_id=rid,
                        extra={"details": unavailable_products},
                    )
                    raise ValidationError("One or more products are no longer offered.")

                if previous is None:
                    order = Order.objects.create(
                        user=None,
                        full_name=form.cleaned_data["full_name"],
                        phone=form.cleaned_data["phone"],
                        address=form.cleaned_data["address"],
                        user_email=form.cleaned_data["email"],
                        is_paid=False,
                        checkout_attempt_key=token,
                        checkout_cart_fingerprint=fingerprint,
                        guest_cart_id=cart.guest_cart_id,
                        payment_provider="stripe",
                    )

                    order.order_serial_number = build_order_serial(order.id)
                    order.save(update_fields=["order_serial_number"])

                    items_count = 0
                    stripe_line_items = []
                    stripe_expected_amount = 0

                    for pid, quantity in items:
                        pid = int(pid)
                        quantity = int(quantity)

                        product = locked_products_map.get(pid)
                        if not product:
                            continue

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            product_name=product.name,
                            quantity=quantity,
                            price=product.price,
                        )
                        items_count += 1

                        stripe_line_items.append(
                            {
                                "price_data": {
                                    "currency": STRIPE_CURRENCY,
                                    "product_data": {
                                        "name": product.name,
                                    },
                                    "unit_amount": eur_to_cents(product.price),
                                },
                                "quantity": quantity,
                            }
                        )
                        stripe_expected_amount += eur_to_cents(product.price) * quantity

                else:
                    order = previous
                    items_count = order.items.count()
                    stripe_line_items = []
                    stripe_expected_amount = 0
                    for item in order.items.all():
                        unit_amount = eur_to_cents(item.price)
                        stripe_line_items.append({
                            "price_data": {
                                "currency": STRIPE_CURRENCY,
                                "product_data": {"name": item.product_name},
                                "unit_amount": unit_amount,
                            },
                            "quantity": item.quantity,
                        })
                        stripe_expected_amount += unit_amount * item.quantity

                # Persist the exact Stripe amount before the external request.
                # All row locks are released when this transaction commits.
                order.stripe_expected_amount = stripe_expected_amount
                order.stripe_expected_currency = STRIPE_CURRENCY
                claim = secrets.token_hex(16)
                order.checkout_processing_claim = claim
                order.checkout_processing_started_at = timezone.now()
                order.save(update_fields=[
                    "stripe_expected_amount", "stripe_expected_currency",
                    "checkout_processing_claim", "checkout_processing_started_at",
                ])

            # IMPORTANT: Stripe network call is outside transaction.atomic().
            # The claim was committed, so a concurrent POST cannot start another
            # request for the same checkout attempt.
            success_url = request.build_absolute_uri(
                reverse("stripe_payment_success")
            ) + "?session_id={CHECKOUT_SESSION_ID}"
            cancel_url = request.build_absolute_uri(
                reverse("stripe_payment_cancel", kwargs={"order_id": order.pk})
            )
            stripe_line_items = stripe_items_for_order(order)
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=stripe_line_items,
                client_reference_id=str(order.pk),
                customer_email=order.user_email,
                metadata={
                    "order_id": str(order.pk),
                    "order_serial_number": order.order_serial_number,
                    "guest_checkout": "true",
                },
                payment_intent_data={
                    "metadata": {
                        "order_id": str(order.pk),
                        "order_serial_number": order.order_serial_number,
                        "guest_checkout": "true",
                    }
                },
                success_url=success_url,
                cancel_url=cancel_url,
                idempotency_key="electryart-checkout-" + token,
            )
            # Persist Stripe's response in a separate short transaction.
            with transaction.atomic():
                saved = Order.objects.select_for_update().get(pk=order.pk)
                if saved.checkout_processing_claim != claim:
                    raise ValidationError("The payment attempt has been superseded. Please try again.")
                saved.stripe_checkout_url = session.url
                saved.stripe_checkout_session_id = session.id
                saved.checkout_processing_claim = ""
                saved.checkout_processing_started_at = None
                saved.save(update_fields=[
                    "stripe_checkout_session_id", "stripe_checkout_url",
                    "checkout_processing_claim", "checkout_processing_started_at",
                ])
            log.info(
                "STRIPE_CHECKOUT_SESSION_CREATED order_id=%s session_id=%s request_id=%s",
                order.pk, session.id, rid,
            )

        except ValidationError as exc:
            form.add_error(None, str(exc))
            return render(request, "orders/guest_checkout.html", {
                "form": form,
                "cart_items": ctx["cart_items"],
                "total": ctx["total"],
            })

        except stripe.error.StripeError as exc:
            if "order" in locals() and "claim" in locals():
                release_checkout_claim(order.pk, claim)
            log.exception(
                "GUEST_STRIPE_CHECKOUT_SESSION_CREATE_FAILED request_id=%s error=%s",
                rid,
                str(exc),
            )
            audit_event(
                "GUEST_STRIPE_CHECKOUT_SESSION_CREATE_FAILED",
                actor=actor,
                request_id=rid,
                extra={"error": str(exc)},
            )
            form.add_error(None, "There was a problem connecting to the payment provider. Please try again.")
            return render(request, "orders/guest_checkout.html", {
                "form": form,
                "cart_items": ctx["cart_items"],
                "total": ctx["total"],
            })

        except Exception:
            if "order" in locals() and "claim" in locals():
                release_checkout_claim(order.pk, claim)
            log.exception("GUEST_ORDER_CREATE_FAILED request_id=%s", rid)
            audit_event("GUEST_ORDER_CREATE_FAILED", actor=actor, request_id=rid)
            raise

        return redirect(session.url, permanent=False)


class Last7DaysOrdersListView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    model = Order
    template_name = "orders/new_orders.html"
    context_object_name = "orders"
    paginate_by = 20

    def test_func(self):

        return self.request.user.is_staff or self.request.user.is_superuser

    def get_queryset(self):
        """
        All orders for last 7 days including today.
        """
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        return (
            Order.objects
            .filter(created_at__gte=seven_days_ago)
            .select_related("user")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        context["from_date"] = seven_days_ago.date()
        context["to_date"] = now.date()

        # Total sum for all orders in this period
        all_orders = self.get_queryset()
        total_revenue = sum(order.total_price for order in all_orders)
        context["total_revenue"] = total_revenue

        return context


class PreviousMonthOrdersListView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    model = Order
    template_name = "orders/previous_month_orders.html"
    context_object_name = "orders"
    paginate_by = 20

    def test_func(self):
        # Only superuser and staff can see all orders
        return self.request.user.is_staff or self.request.user.is_superuser

    @staticmethod
    def _get_prev_month_year():
        """
        Returns last month (year, month).
        """
        today = timezone.now().date()
        if today.month == 1:
            return today.year - 1, 12
        return today.year, today.month - 1

    def _get_prev_month_period(self):

        year, month = self._get_prev_month_year()
        from_date = date(year, month, 1)

        # Found the first number of the current month
        today = timezone.now().date()
        first_day_current_month = today.replace(day=1)
        last_day_prev_month = first_day_current_month - timedelta(days=1)

        return from_date, last_day_prev_month

    def get_queryset(self):
        year, month = self._get_prev_month_year()

        # All orders from last month
        return (
            Order.objects
            .filter(created_at__year=year, created_at__month=month)
            .select_related("user")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year, month = self._get_prev_month_year()
        from_date, to_date = self._get_prev_month_period()

        context["prev_month_year"] = year
        context["prev_month"] = month
        context["from_date"] = from_date
        context["to_date"] = to_date

        # Total sum for all orders from last month
        all_orders = self.get_queryset()
        total_revenue = sum(order.total_price for order in all_orders)
        context["total_revenue"] = total_revenue

        return context


class OrdersEditView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Order
    template_name = "orders/order_edit.html"
    context_object_name = "order"
    fields = [
        "full_name",
        "user_email",
        "phone",
        "address",
        "is_accepted",
        "is_sent",
    ]

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order_items"] = self.object.items.all()
        return context

    def form_valid(self, form):
        rid = getattr(self.request, "request_id", None)
        actor = Actor(type="staff", id=getattr(self.request.user, "pk", None))

        # snapshot BEFORE
        before_accepted = form.instance.is_accepted
        before_sent = form.instance.is_sent
        before = f"accepted={before_accepted},sent={before_sent}"

        # Business rule: Not allowed sent without accept
        if form.cleaned_data.get("is_sent"):
            form.instance.is_accepted = True

        response = super().form_valid(form)

        # Snapshot AFTER (self.object has already been saved).
        after = f"accepted={self.object.is_accepted},sent={self.object.is_sent}"

        log.info(
            "ORDER_STATUS_CHANGED order_id=%s serial=%s from=%s to=%s staff_id=%s request_id=%s",
            self.object.pk,
            self.object.order_serial_number,
            before,
            after,
            actor.id,
            rid,
        )

        audit_event(
            "ORDER_STATUS_CHANGED",
            actor=actor,
            request_id=rid,
            order_id=self.object.pk,
            serial=self.object.order_serial_number,
            status_from=before,
            status_to=after,
        )

        return response


    def get_success_url(self):
        return reverse_lazy("order_detail", kwargs={"pk": self.object.pk})


class CancelOrderItemView(LoginRequiredMixin, UserPassesTestMixin, View):

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    @staticmethod
    def post(request, pk):
        item = get_object_or_404(OrderItem, pk=pk)

        try:
            cancel_quantity = int(request.POST.get("cancel_quantity", 0))
        except ValueError:
            messages.error(request, "Invalid cancel quantity.")
            return redirect("order_edit", pk=item.order.pk)

        if cancel_quantity <= 0:
            messages.error(request, "Cancel quantity must be greater than zero.")
            return redirect("order_edit", pk=item.order.pk)

        remaining_quantity = item.quantity - item.cancelled_quantity

        if cancel_quantity > remaining_quantity:
            messages.error(request, "Cancel quantity cannot be greater than remaining quantity.")
            return redirect("order_edit", pk=item.order.pk)

        item.cancelled_quantity += cancel_quantity

        if item.cancelled_quantity >= item.quantity:
            item.status = OrderItemStatus.CANCELLED
        else:
            item.status = OrderItemStatus.ACTIVE

        item.cancelled_at = timezone.now()
        item.cancelled_by = request.user

        item.save(
            update_fields=[
                "cancelled_quantity",
                "status",
                "cancelled_at",
                "cancelled_by",
            ]
        )

        messages.success(request, "Order item quantity cancelled successfully.")
        return redirect("order edit", pk=item.order.pk)


def subtract_purchased_from_registered_cart(order):
    """Remove only quantities captured by the paid order, not later additions."""
    if not order.user_id:
        return
    cart = Cart.objects.filter(user_id=order.user_id).first()
    if not cart:
        return
    purchased = {}
    for product_id, quantity in order.items.filter(product_id__isnull=False).values_list("product_id", "quantity"):
        purchased[product_id] = purchased.get(product_id, 0) + quantity
    # The webhook already holds the order row lock. Lock cart rows too so
    # simultaneous cart edits cannot overwrite the deduction.
    for item in cart.items.select_for_update().filter(product_id__in=purchased):
        remaining = item.quantity - purchased[item.product_id]
        if remaining > 0:
            item.quantity = remaining
            item.save(update_fields=["quantity"])
        else:
            item.delete()


def subtract_purchased_from_guest_cart(request, order):
    """Session-local deduction, once per paid order and browser session."""
    marker = "paid_guest_cart_adjusted_orders"
    adjusted = request.session.get(marker, [])
    if str(order.pk) in adjusted:
        return False
    cart = SessionCart(request)
    purchased = {}
    for product_id, quantity in order.items.filter(product_id__isnull=False).values_list("product_id", "quantity"):
        key = str(product_id)
        purchased[key] = purchased.get(key, 0) + quantity
    for product_id, quantity in purchased.items():
        current = int(cart.cart.get(product_id, 0))
        if current > quantity:
            cart.update(product_id, current - quantity)
        elif current:
            cart.remove(product_id)
    request.session[marker] = (adjusted + [str(order.pk)])[-100:]
    request.session.modified = True
    return True


class StripePaymentSuccessView(View):
    template_name = "orders/stripe_payment_success.html"

    def get(self, request):
        is_authenticated = request.user.is_authenticated
        actor = Actor(
            type="user" if is_authenticated else "guest",
            id=getattr(request.user, "pk", None) if is_authenticated else None,
        )
        rid = getattr(request, "request_id", None)

        session_id = request.GET.get("session_id")
        if not session_id:
            log.info(
                "STRIPE_SUCCESS_PAGE_MISSING_SESSION_ID actor_type=%s actor_id=%s request_id=%s",
                actor.type,
                actor.id,
                rid,
            )
            audit_event(
                "STRIPE_SUCCESS_PAGE_MISSING_SESSION_ID",
                actor=actor,
                request_id=rid,
            )
            return redirect("cart_view")

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id)

            order_id = session.client_reference_id
            if not order_id:
                log.warning(
                    "STRIPE_SUCCESS_PAGE_MISSING_ORDER_ID session_id=%s actor_type=%s actor_id=%s request_id=%s",
                    session_id,
                    actor.type,
                    actor.id,
                    rid,
                )
                audit_event(
                    "STRIPE_SUCCESS_PAGE_MISSING_ORDER_ID",
                    actor=actor,
                    request_id=rid,
                    extra={"stripe_checkout_session_id": session_id},
                )
                return redirect("cart_view")

            order = get_object_or_404(Order, pk=order_id)

            # access control:
            # 1) logged user -> order must belong to that user
            # 2) guest -> order must be guest order and session id must match
            if is_authenticated:
                if order.user_id != request.user.pk:
                    log.warning(
                        "STRIPE_SUCCESS_PAGE_FORBIDDEN_USER order_id=%s session_id=%s actor_id=%s request_id=%s",
                        order.pk,
                        session_id,
                        actor.id,
                        rid,
                    )
                    audit_event(
                        "STRIPE_SUCCESS_PAGE_FORBIDDEN_USER",
                        actor=actor,
                        request_id=rid,
                        order_id=order.pk,
                        serial=order.order_serial_number,
                        extra={"stripe_checkout_session_id": session_id},
                    )
                    return redirect("cart_view")
            else:
                if order.user_id is not None:
                    log.warning(
                        "STRIPE_SUCCESS_PAGE_GUEST_FORBIDDEN_NON_GUEST_ORDER order_id=%s session_id=%s request_id=%s",
                        order.pk,
                        session_id,
                        rid,
                    )
                    audit_event(
                        "STRIPE_SUCCESS_PAGE_GUEST_FORBIDDEN_NON_GUEST_ORDER",
                        actor=actor,
                        request_id=rid,
                        order_id=order.pk,
                        serial=order.order_serial_number,
                        extra={"stripe_checkout_session_id": session_id},
                    )
                    return redirect("cart_view")

                if order.stripe_checkout_session_id != session_id:
                    log.warning(
                        "STRIPE_SUCCESS_PAGE_GUEST_SESSION_MISMATCH order_id=%s expected_session_id=%s actual_session_id=%s request_id=%s",
                        order.pk,
                        order.stripe_checkout_session_id,
                        session_id,
                        rid,
                    )
                    audit_event(
                        "STRIPE_SUCCESS_PAGE_GUEST_SESSION_MISMATCH",
                        actor=actor,
                        request_id=rid,
                        order_id=order.pk,
                        serial=order.order_serial_number,
                        extra={
                            "expected_stripe_checkout_session_id": order.stripe_checkout_session_id,
                            "actual_stripe_checkout_session_id": session_id,
                        },
                    )
                    return redirect("cart_view")

            # Preserve items added after checkout began. Deduct once per guest session.
            if not is_authenticated and order.user_id is None and order.is_paid:
                subtract_purchased_from_guest_cart(request, order)

                log.info(
                    "GUEST_SESSION_CART_CLEARED_AFTER_STRIPE_SUCCESS order_id=%s serial=%s session_id=%s request_id=%s",
                    order.pk,
                    order.order_serial_number,
                    session_id,
                    rid,
                )
                audit_event(
                    "GUEST_SESSION_CART_CLEARED_AFTER_STRIPE_SUCCESS",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                    email_mask=mask_email(order.user_email),
                    extra={"stripe_checkout_session_id": session_id},
                )

            log.info(
                "STRIPE_SUCCESS_PAGE_OPENED order_id=%s serial=%s session_id=%s actor_type=%s actor_id=%s request_id=%s",
                order.pk,
                order.order_serial_number,
                session_id,
                actor.type,
                actor.id,
                rid,
            )
            audit_event(
                "STRIPE_SUCCESS_PAGE_OPENED",
                actor=actor,
                request_id=rid,
                order_id=order.pk,
                serial=order.order_serial_number,
                email_mask=mask_email(order.user_email),
                extra={
                    "stripe_checkout_session_id": session_id,
                    "payment_status": getattr(session, "payment_status", None),
                },
            )

        except stripe.error.StripeError:
            log.exception(
                "STRIPE_SUCCESS_PAGE_SESSION_RETRIEVE_FAILED actor_type=%s actor_id=%s request_id=%s session_id=%s",
                actor.type,
                actor.id,
                rid,
                session_id,
            )
            audit_event(
                "STRIPE_SUCCESS_PAGE_SESSION_RETRIEVE_FAILED",
                actor=actor,
                request_id=rid,
                extra={"stripe_checkout_session_id": session_id},
            )
            return redirect("cart_view")

        context = {
            "order": order,
            "stripe_session": session,
            "payment_status": getattr(session, "payment_status", None),
        }
        return render(request, self.template_name, context)


class StripePaymentCancelView(View):
    template_name = "orders/stripe_payment_cancel.html"

    def get(self, request, order_id):
        rid = getattr(request, "request_id", None)

        if request.user.is_authenticated:
            actor = Actor(type="user", id=request.user.pk)

            order = get_object_or_404(
                Order,
                pk=order_id,
                user=request.user,
            )
        else:
            actor = Actor(type="guest", id=None)

            order = get_object_or_404(
                Order,
                pk=order_id,
                user__isnull=True,
            )

        log.info(
            "STRIPE_PAYMENT_CANCEL_PAGE_OPENED order_id=%s serial=%s user_id=%s request_id=%s",
            order.pk,
            order.order_serial_number,
            getattr(request.user, "pk", None),
            rid,
        )

        audit_event(
            "STRIPE_PAYMENT_CANCEL_PAGE_OPENED",
            actor=actor,
            request_id=rid,
            order_id=order.pk,
            serial=order.order_serial_number,
            email_mask=mask_email(order.user_email),
        )

        return render(request, self.template_name, {
            "order": order,
        })


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    http_method_names = ["post"]

    @staticmethod
    def post(request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        rid = getattr(request, "request_id", None)
        actor = Actor(type="system", id=None)

        if not settings.STRIPE_WEBHOOK_SECRET:
            log.error("STRIPE_WEBHOOK_SECRET_MISSING request_id=%s", rid)
            audit_event("STRIPE_WEBHOOK_SECRET_MISSING", actor=actor, request_id=rid)
            return HttpResponse(status=500)

        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
        except ValueError:
            log.warning("STRIPE_WEBHOOK_INVALID_PAYLOAD request_id=%s", rid)
            audit_event("STRIPE_WEBHOOK_INVALID_PAYLOAD", actor=actor, request_id=rid)
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            log.warning("STRIPE_WEBHOOK_INVALID_SIGNATURE request_id=%s", rid)
            audit_event("STRIPE_WEBHOOK_INVALID_SIGNATURE", actor=actor, request_id=rid)
            return HttpResponse(status=400)

        event_type = event["type"]
        data_object = event["data"]["object"]

        log.info(
            "STRIPE_WEBHOOK_RECEIVED event_type=%s event_id=%s request_id=%s",
            event_type,
            event.get("id"),
            rid,
        )
        audit_event(
            "STRIPE_WEBHOOK_RECEIVED",
            actor=actor,
            request_id=rid,
            extra={
                "event_type": event_type,
                "event_id": event.get("id"),
            },
        )

        if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            session = data_object

            session_id = session.get("id")
            payment_intent_id = session.get("payment_intent")
            payment_status = session.get("payment_status")
            client_reference_id = session.get("client_reference_id")
            metadata = session.get("metadata", {}) or {}

            order_id = metadata.get("order_id") or client_reference_id

            if not order_id:
                log.error(
                    "STRIPE_WEBHOOK_ORDER_ID_MISSING session_id=%s event_id=%s request_id=%s",
                    session_id,
                    event.get("id"),
                    rid,
                )
                audit_event(
                    "STRIPE_WEBHOOK_ORDER_ID_MISSING",
                    actor=actor,
                    request_id=rid,
                    extra={
                        "session_id": session_id,
                        "event_id": event.get("id"),
                    },
                )
                return HttpResponse(status=400)

            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order_id)

                    # A signed event must refer to this order's stored Checkout Session.
                    if (
                        not session_id
                        or not order.stripe_checkout_session_id
                        or order.stripe_checkout_session_id != session_id
                    ):
                        log.error(
                            "STRIPE_WEBHOOK_SESSION_MISMATCH "
                            "order_id=%s expected=%s received=%s",
                            order.pk,
                            order.stripe_checkout_session_id,
                            session_id,
                        )
                        return HttpResponse(status=409)

                    # Reconcile the signed Stripe Checkout event with the original order.
                    # Fail closed: missing values are not evidence of a valid payment.
                    expected_live = settings.STRIPE_SECRET_KEY.startswith("sk_live_") if settings.STRIPE_SECRET_KEY else None
                    metadata_order_id = metadata.get("order_id")
                    if (
                        order.stripe_expected_amount is None
                        or session.get("amount_total") != order.stripe_expected_amount
                        or not order.stripe_expected_currency
                        or session.get("currency") != order.stripe_expected_currency.lower()
                        or session.get("mode") != "payment"
                        or expected_live is None
                        or session.get("livemode") is not expected_live
                        or str(client_reference_id) != str(order.pk)
                        or str(metadata_order_id) != str(order.pk)
                        or metadata.get("order_serial_number") != order.order_serial_number
                    ):
                        log.error(
                            "STRIPE_WEBHOOK_RECONCILIATION_FAILED order_id=%s session_id=%s "
                            "amount=%s expected_amount=%s currency=%s expected_currency=%s "
                            "mode=%s livemode=%s expected_live=%s client_reference_id=%s "
                            "metadata_order_id=%s metadata_serial=%s",
                            order.pk, session_id,
                            session.get("amount_total"), order.stripe_expected_amount,
                            session.get("currency"), order.stripe_expected_currency,
                            session.get("mode"), session.get("livemode"), expected_live,
                            client_reference_id, metadata_order_id,
                            metadata.get("order_serial_number"),
                        )
                        return HttpResponse(status=409)

                    if order.is_paid:
                        log.info(
                            "STRIPE_WEBHOOK_ORDER_ALREADY_PAID order_id=%s serial=%s session_id=%s payment_intent_id=%s request_id=%s",
                            order.pk,
                            order.order_serial_number,
                            session_id,
                            payment_intent_id,
                            rid,
                        )
                        audit_event(
                            "STRIPE_WEBHOOK_ORDER_ALREADY_PAID",
                            actor=actor,
                            request_id=rid,
                            order_id=order.pk,
                            serial=order.order_serial_number,
                            email_mask=mask_email(order.user_email),
                            extra={
                                "stripe_checkout_session_id": session_id,
                                "stripe_payment_intent_id": payment_intent_id,
                            },
                        )
                        return HttpResponse(status=200)

                    if payment_status != "paid":
                        log.warning(
                            "STRIPE_WEBHOOK_SESSION_NOT_PAID order_id=%s serial=%s session_id=%s payment_status=%s request_id=%s",
                            order.pk,
                            order.order_serial_number,
                            session_id,
                            payment_status,
                            rid,
                        )
                        audit_event(
                            "STRIPE_WEBHOOK_SESSION_NOT_PAID",
                            actor=actor,
                            request_id=rid,
                            order_id=order.pk,
                            serial=order.order_serial_number,
                            email_mask=mask_email(order.user_email),
                            extra={
                                "stripe_checkout_session_id": session_id,
                                "payment_status": payment_status,
                            },
                        )
                        return HttpResponse(status=200)

                    # mark paid
                    order.is_paid = True
                    order.paid_at = timezone.now()
                    order.payment_provider = "stripe"
                    order.stripe_checkout_session_id = session_id
                    order.stripe_payment_intent_id = payment_intent_id
                    order.save(
                        update_fields=[
                            "is_paid",
                            "paid_at",
                            "payment_provider",
                            "stripe_checkout_session_id",
                            "stripe_payment_intent_id",
                        ]
                    )

                    # Remove only the purchased quantities; preserve later additions.
                    # The order row lock makes webhook retries safe: an already-paid
                    # order returns above without deducting twice.
                    subtract_purchased_from_registered_cart(order)

                    log.info(
                        "STRIPE_PAYMENT_CONFIRMED order_id=%s serial=%s session_id=%s payment_intent_id=%s request_id=%s",
                        order.pk,
                        order.order_serial_number,
                        session_id,
                        payment_intent_id,
                        rid,
                    )
                    audit_event(
                        "STRIPE_PAYMENT_CONFIRMED",
                        actor=actor,
                        request_id=rid,
                        order_id=order.pk,
                        serial=order.order_serial_number,
                        email_mask=mask_email(order.user_email),
                        extra={
                            "stripe_checkout_session_id": session_id,
                            "stripe_payment_intent_id": payment_intent_id,
                        },
                    )

                    transaction.on_commit(
                        lambda: checkout_completed.send(
                            sender=StripeWebhookView,
                            order=order,
                            user=order.user,
                            request_id=rid,
                        )
                    )

                    log.info(
                        "CHECKOUT_COMPLETED_SIGNAL_QUEUED_FROM_STRIPE order_id=%s request_id=%s",
                        order.pk,
                        rid,
                    )
                    audit_event(
                        "CHECKOUT_COMPLETED_SIGNAL_QUEUED_FROM_STRIPE",
                        actor=actor,
                        request_id=rid,
                        order_id=order.pk,
                        serial=order.order_serial_number,
                    )

            except Order.DoesNotExist:
                log.error(
                    "STRIPE_WEBHOOK_ORDER_NOT_FOUND order_id=%s session_id=%s event_id=%s request_id=%s",
                    order_id,
                    session_id,
                    event.get("id"),
                    rid,
                )
                audit_event(
                    "STRIPE_WEBHOOK_ORDER_NOT_FOUND",
                    actor=actor,
                    request_id=rid,
                    extra={
                        "order_id": order_id,
                        "session_id": session_id,
                        "event_id": event.get("id"),
                    },
                )
                return HttpResponse(status=404)

            except Exception as exc:
                log.exception(
                    "STRIPE_WEBHOOK_PROCESSING_FAILED event_type=%s event_id=%s request_id=%s error=%s",
                    event_type,
                    event.get("id"),
                    rid,
                    str(exc),
                )
                audit_event(
                    "STRIPE_WEBHOOK_PROCESSING_FAILED",
                    actor=actor,
                    request_id=rid,
                    extra={
                        "event_type": event_type,
                        "event_id": event.get("id"),
                        "error": str(exc),
                    },
                )
                return HttpResponse(status=500)

        elif event_type == "checkout.session.async_payment_failed":
            session = data_object
            log.warning(
                "STRIPE_ASYNC_PAYMENT_FAILED session_id=%s event_id=%s request_id=%s",
                session.get("id"),
                event.get("id"),
                rid,
            )
            audit_event(
                "STRIPE_ASYNC_PAYMENT_FAILED",
                actor=actor,
                request_id=rid,
                extra={
                    "session_id": session.get("id"),
                    "event_id": event.get("id"),
                },
            )

        return HttpResponse(status=200)


class OrderSerialSearchView(SuperuserRequiredMixin, View):
    template_name = 'orders/order_serial_search.html'

    def get(self, request, *args, **kwargs):
        serial = request.GET.get('serial_number', '').strip()

        if serial:
            result = Order.objects.filter(
                Q(order_serial_number=serial)
            ).select_related('user').prefetch_related('items').first()

            if result:
                return redirect('order_detail', pk=result.pk)

            return render(request, self.template_name, {
                'searched': True,
                'no_results': True,
                'serial_number': serial,
            })

        return render(request, self.template_name, {
            'searched': False,
        })