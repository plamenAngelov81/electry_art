from datetime import timedelta, date
from decimal import Decimal

import stripe
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.urls import reverse_lazy, reverse
from django.views import View, generic
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Order, OrderItem
from .forms import CheckoutForm, GuestCheckoutForm
from electry_art.cart.models import Cart
from ..cart.utils import SessionCart
from ..products.models import Product
from electry_art.cart.signals import checkout_completed
import logging
from electry_art.core.audit import audit_event, Actor, mask_email


log = logging.getLogger("electryart.orders")
stripe.api_key = settings.STRIPE_SECRET_KEY


def build_order_serial(order_id):
    # ORD-20260106-000154
    return f"ORD{timezone.now().strftime('%Y%m%d')}{order_id:06d}"


class CheckoutView(LoginRequiredMixin, View):
    @staticmethod
    def get(request):
        cart = Cart.objects.filter(user=request.user).first()
        if not cart or not cart.items.exists():
            return redirect("cart_view")

        form = CheckoutForm(user=request.user)
        return render(request, "orders/checkout.html", {"form": form, "cart": cart})

    @staticmethod
    def post(request):
        actor = Actor(type="user", id=getattr(request.user, "pk", None))
        rid = getattr(request, "request_id", None)

        log.info("CHECKOUT_STARTED user_id=%s request_id=%s", actor.id, rid)
        audit_event("CHECKOUT_STARTED", actor=actor, request_id=rid)

        cart = Cart.objects.filter(user=request.user).prefetch_related("items__product").first()
        if not cart or not cart.items.exists():
            log.info("CHECKOUT_EMPTY_CART user_id=%s request_id=%s", actor.id, rid)
            audit_event("CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
            return redirect("cart_view")

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
            return render(request, "orders/checkout.html", {"form": form, "cart": cart})

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY

            with transaction.atomic():
                log.info("ORDER_CREATE_STARTED user_id=%s request_id=%s", actor.id, rid)
                audit_event("ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                items = list(cart.items.select_related("product"))
                items_count = len(items)

                if not items:
                    log.info("CHECKOUT_EMPTY_CART user_id=%s request_id=%s", actor.id, rid)
                    audit_event("CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
                    return redirect("cart_view")

                product_ids = [it.product_id for it in items]
                products = (
                    Product.objects.select_for_update()
                    .filter(id__in=product_ids)
                    .only("id", "name", "price", "quantity", "is_available")
                )
                products_map = {p.id: p for p in products}

                insufficient = []
                missing_products = []

                for it in items:
                    product = products_map.get(it.product_id)

                    if product is None:
                        missing_products.append({"product_id": it.product_id})
                        continue

                    if not product.is_available or product.quantity < it.quantity:
                        insufficient.append(
                            {
                                "product_id": product.id,
                                "requested": it.quantity,
                                "available": product.quantity,
                                "is_available": product.is_available,
                            }
                        )

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
                    raise ValidationError("Някои продукти вече не са налични.")

                if insufficient:
                    log.info(
                        "CHECKOUT_INSUFFICIENT_STOCK user_id=%s request_id=%s details=%s",
                        actor.id, rid, insufficient
                    )
                    audit_event(
                        "CHECKOUT_INSUFFICIENT_STOCK",
                        actor=actor,
                        request_id=rid,
                        extra={"details": insufficient},
                    )
                    raise ValidationError("Недостатъчна наличност за един или повече продукти.")

                order = Order.objects.create(
                    user=request.user,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                    user_email=request.user.email or None,
                    is_paid=False,
                    payment_provider="stripe",
                )

                order.order_serial_number = build_order_serial(order.id)
                order.save(update_fields=["order_serial_number"])

                stripe_line_items = []

                for it in items:
                    product = products_map[it.product_id]

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=it.quantity,
                        price=product.price,
                    )

                    stripe_line_items.append(
                        {
                            "price_data": {
                                "currency": "eur",
                                "product_data": {
                                    "name": product.name,
                                },
                                "unit_amount": int(product.price * 100),
                            },
                            "quantity": it.quantity,
                        }
                    )

                success_url = request.build_absolute_uri(
                    reverse("stripe_payment_success")
                ) + "?session_id={CHECKOUT_SESSION_ID}"

                cancel_url = request.build_absolute_uri(
                    reverse("stripe_payment_cancel", kwargs={"order_id": order.pk})
                )

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
                        "request_id": str(rid or ""),
                    },
                    success_url=success_url,
                    cancel_url=cancel_url,
                )

                order.stripe_checkout_session_id = session.id
                order.save(update_fields=["stripe_checkout_session_id"])

                log.info(
                    "STRIPE_CHECKOUT_SESSION_CREATED order_id=%s serial=%s session_id=%s user_id=%s request_id=%s",
                    order.pk,
                    order.order_serial_number,
                    session.id,
                    actor.id,
                    rid,
                )
                audit_event(
                    "STRIPE_CHECKOUT_SESSION_CREATED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                    email_mask=mask_email(order.user_email),
                    extra={
                        "items": items_count,
                        "stripe_checkout_session_id": session.id,
                    },
                )

        except ValidationError as exc:
            form.add_error(None, str(exc))
            return render(request, "orders/checkout.html", {"form": form, "cart": cart})

        except stripe.error.StripeError as exc:
            # log.exception(
            #     "STRIPE_CHECKOUT_SESSION_CREATE_FAILED user_id=%s request_id=%s",
            #     actor.id,
            #     rid,
            # )
            # audit_event(
            #     "STRIPE_CHECKOUT_SESSION_CREATE_FAILED",
            #     actor=actor,
            #     request_id=rid,
            # )
            # form.add_error(None, "Възникна проблем при връзката с платежната система. Опитайте отново.")
            # return render(request, "orders/checkout.html", {"form": form, "cart": cart})

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
            return render(request, "orders/checkout.html", {"form": form, "cart": cart})


        except Exception:  # noqa: BLE001
            log.exception("ORDER_CREATE_FAILED user_id=%s request_id=%s", actor.id, rid)
            audit_event("ORDER_CREATE_FAILED", actor=actor, request_id=rid)
            raise

        return redirect(session.url, permanent=False)


class OrderSuccessView(generic.DetailView):
    model = Order
    template_name = 'orders/success.html'
    context_object_name = 'order'

    def get_object(self, queryset=None):
        return Order.objects.get(pk=self.kwargs['order_id'])

    def get_queryset(self):
        return Order.objects.prefetch_related("items__product")


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


# class GuestCheckoutView(View):
#     @staticmethod
#     def _build_cart_context(cart):
#         items = list(cart.items())
#         if not items:
#             return None
#
#         product_ids = [int(pid) for pid, _ in items]
#         products = Product.objects.in_bulk(product_ids)
#
#         cart_items = []
#         total = 0
#         for pid, quantity in items:
#             pid = int(pid)
#             quantity = int(quantity)
#             product = products.get(pid)
#             if not product:
#                 continue
#
#             item_total = product.price * quantity
#             cart_items.append({"product": product, "quantity": quantity, "total": item_total})
#             total += item_total
#
#         return {"items": items, "products": products, "cart_items": cart_items, "total": total}
#
#     def get(self, request):
#         if request.user.is_authenticated:
#             return redirect("checkout")
#
#         cart = SessionCart(request)
#         ctx = self._build_cart_context(cart)
#         if not ctx:
#             return redirect("cart_view")
#
#         form = GuestCheckoutForm()
#         return render(request, "orders/guest_checkout.html", {
#             "form": form,
#             "cart_items": ctx["cart_items"],
#             "total": ctx["total"],
#         })
#
#     def post(self, request):
#         if request.user.is_authenticated:
#             return redirect("checkout")
#
#         actor = Actor(type="guest", id=None)
#         rid = getattr(request, "request_id", None)
#
#         log.info("GUEST_CHECKOUT_STARTED request_id=%s", rid)
#         audit_event("GUEST_CHECKOUT_STARTED", actor=actor, request_id=rid)
#
#         cart = SessionCart(request)
#         ctx = self._build_cart_context(cart)
#         if not ctx:
#             log.info("GUEST_CHECKOUT_EMPTY_CART request_id=%s", rid)
#             audit_event("GUEST_CHECKOUT_EMPTY_CART", actor=actor, request_id=rid)
#             return redirect("cart_view")
#
#         form = GuestCheckoutForm(request.POST)
#         if not form.is_valid():
#             bad_fields = list(form.errors.keys())
#
#             log.info(
#                 "GUEST_CHECKOUT_VALIDATION_FAILED request_id=%s fields=%s",
#                 rid, bad_fields
#             )
#             audit_event(
#                 "GUEST_CHECKOUT_VALIDATION_FAILED",
#                 actor=actor,
#                 request_id=rid,
#                 extra={"fields": bad_fields},
#             )
#
#             return render(request, "orders/guest_checkout.html", {
#                 "form": form,
#                 "cart_items": ctx["cart_items"],
#                 "total": ctx["total"],
#             })
#
#         try:
#             with transaction.atomic():
#                 log.info("GUEST_ORDER_CREATE_STARTED request_id=%s", rid)
#                 audit_event("GUEST_ORDER_CREATE_STARTED", actor=actor, request_id=rid)
#
#                 order = Order.objects.create(
#                     user=None,
#                     full_name=form.cleaned_data["full_name"],
#                     phone=form.cleaned_data["phone"],
#                     address=form.cleaned_data["address"],
#                     user_email=form.cleaned_data["email"],
#                 )
#
#                 order.order_serial_number = build_order_serial(order.id)
#                 order.save(update_fields=["order_serial_number"])
#
#                 items_count = 0
#                 for pid, quantity in ctx["items"]:
#                     pid = int(pid)
#                     product = ctx["products"].get(pid)
#                     if not product:
#                         continue
#
#                     OrderItem.objects.create(
#                         order=order,
#                         product=product,
#                         product_name=product.name,  # snapshot
#                         quantity=quantity,
#                         price=product.price,  # snapshot
#                     )
#                     items_count += 1
#
#                 cart.clear()
#
#                 log.info(
#                     "GUEST_ORDER_CREATED order_id=%s serial=%s items=%s request_id=%s",
#                     order.pk,
#                     order.order_serial_number,
#                     items_count,
#                     rid,
#                 )
#                 audit_event(
#                     "GUEST_ORDER_CREATED",
#                     actor=actor,
#                     request_id=rid,
#                     order_id=order.pk,
#                     serial=order.order_serial_number,
#                     email_mask=mask_email(order.user_email),
#                     extra={"items": items_count},
#                 )
#
#                 transaction.on_commit(
#                     lambda: checkout_completed.send(
#                         sender=GuestCheckoutView,
#                         order=order,
#                         user=None,
#                         request_id=rid,  # <--- важно за receiver-а
#                     )
#                 )
#
#                 log.info("GUEST_CHECKOUT_COMPLETED_SIGNAL_QUEUED order_id=%s request_id=%s", order.pk, rid)
#                 audit_event(
#                     "GUEST_CHECKOUT_COMPLETED_SIGNAL_QUEUED",
#                     actor=actor,
#                     request_id=rid,
#                     order_id=order.pk,
#                     serial=order.order_serial_number,
#                 )
#
#         except Exception:  # noqa: BLE001
#             log.exception("GUEST_ORDER_CREATE_FAILED request_id=%s", rid)
#             audit_event("GUEST_ORDER_CREATE_FAILED", actor=actor, request_id=rid)
#             raise
#
#         return redirect("order_success", order_id=order.pk)

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

            with transaction.atomic():
                log.info("GUEST_ORDER_CREATE_STARTED request_id=%s", rid)
                audit_event("GUEST_ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                items = list(ctx["items"])
                products_map = ctx["products"]

                insufficient = []
                missing_products = []

                product_ids = [int(pid) for pid, _ in items]
                locked_products = (
                    Product.objects.select_for_update()
                    .filter(id__in=product_ids)
                    .only("id", "name", "price", "quantity", "is_available")
                )
                locked_products_map = {p.id: p for p in locked_products}

                for pid, quantity in items:
                    pid = int(pid)
                    quantity = int(quantity)

                    product = locked_products_map.get(pid)
                    if product is None:
                        missing_products.append({"product_id": pid})
                        continue

                    if not product.is_available or product.quantity < quantity:
                        insufficient.append({
                            "product_id": product.id,
                            "requested": quantity,
                            "available": product.quantity,
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
                    raise ValidationError("Някои продукти вече не са налични.")

                if insufficient:
                    log.info(
                        "GUEST_CHECKOUT_INSUFFICIENT_STOCK request_id=%s details=%s",
                        rid,
                        insufficient,
                    )
                    audit_event(
                        "GUEST_CHECKOUT_INSUFFICIENT_STOCK",
                        actor=actor,
                        request_id=rid,
                        extra={"details": insufficient},
                    )
                    raise ValidationError("Недостатъчна наличност за един или повече продукти.")

                order = Order.objects.create(
                    user=None,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                    user_email=form.cleaned_data["email"],
                    is_paid=False,
                    payment_provider="stripe",
                )

                order.order_serial_number = build_order_serial(order.id)
                order.save(update_fields=["order_serial_number"])

                items_count = 0
                stripe_line_items = []

                BGN_TO_EUR = Decimal("0.51129")

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

                    price_eur = (product.price * BGN_TO_EUR).quantize(Decimal("0.01"))
                    unit_amount = int(price_eur * 100)

                    stripe_line_items.append(
                        {
                            "price_data": {
                                "currency": "eur",
                                "product_data": {
                                    "name": product.name,
                                },
                                "unit_amount": unit_amount,
                            },
                            "quantity": quantity,
                        }
                    )

                success_url = request.build_absolute_uri(
                    reverse("stripe_payment_success")
                ) + "?session_id={CHECKOUT_SESSION_ID}"

                cancel_url = request.build_absolute_uri(
                    reverse("stripe_payment_cancel", kwargs={"order_id": order.pk})
                )

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
                        "request_id": str(rid or ""),
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
                )

                order.stripe_checkout_session_id = session.id
                order.save(update_fields=["stripe_checkout_session_id"])

                log.info(
                    "GUEST_STRIPE_CHECKOUT_SESSION_CREATED order_id=%s serial=%s session_id=%s request_id=%s",
                    order.pk,
                    order.order_serial_number,
                    session.id,
                    rid,
                )
                audit_event(
                    "GUEST_STRIPE_CHECKOUT_SESSION_CREATED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                    email_mask=mask_email(order.user_email),
                    extra={
                        "items": items_count,
                        "stripe_checkout_session_id": session.id,
                    },
                )

        except ValidationError as exc:
            form.add_error(None, str(exc))
            return render(request, "orders/guest_checkout.html", {
                "form": form,
                "cart_items": ctx["cart_items"],
                "total": ctx["total"],
            })

        except stripe.error.StripeError as exc:
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
            form.add_error(None, "Възникна проблем при връзката с платежната система. Опитайте отново.")
            return render(request, "orders/guest_checkout.html", {
                "form": form,
                "cart_items": ctx["cart_items"],
                "total": ctx["total"],
            })

        except Exception:
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

    # def form_valid(self, form):
    #     """Not allowed sent without accept"""
    #     if form.cleaned_data.get("is_sent"):
    #         form.instance.is_accepted = True
    #     return super().form_valid(form)

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

        # snapshot AFTER (self.object е вече saved)
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

            # guest session cart clear happens here, not in webhook
            if not is_authenticated and order.user_id is None and order.is_paid:
                cart = SessionCart(request)
                cart.clear()

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



class StripePaymentCancelView(LoginRequiredMixin, View):
    template_name = "orders/stripe_payment_cancel.html"

    def get(self, request, order_id):
        actor = Actor(type="user", id=getattr(request.user, "pk", None))
        rid = getattr(request, "request_id", None)

        order = get_object_or_404(
            Order,
            pk=order_id,
            user=request.user,
        )

        log.info(
            "STRIPE_PAYMENT_CANCEL_PAGE_OPENED order_id=%s serial=%s user_id=%s request_id=%s",
            order.pk,
            order.order_serial_number,
            actor.id,
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

        context = {
            "order": order,
        }
        return render(request, self.template_name, context)


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

        if event_type == "checkout.session.completed":
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
                    order = (
                        Order.objects.select_for_update()
                        .prefetch_related("items__product")
                        .get(pk=order_id)
                    )

                    # idempotency: ако вече е платена, не правим нищо повторно
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

                    items = list(order.items.select_related("product"))
                    insufficient = []
                    missing_products = []

                    product_ids = [item.product_id for item in items if item.product_id]
                    products = (
                        Product.objects.select_for_update()
                        .filter(id__in=product_ids)
                        .only("id", "name", "quantity", "is_available")
                    )
                    products_map = {product.id: product for product in products}

                    for item in items:
                        if not item.product_id:
                            missing_products.append(
                                {
                                    "order_item_id": item.pk,
                                    "product_name": item.product_name,
                                }
                            )
                            continue

                        product = products_map.get(item.product_id)
                        if product is None:
                            missing_products.append(
                                {
                                    "product_id": item.product_id,
                                    "product_name": item.product_name,
                                }
                            )
                            continue

                        if product.quantity < item.quantity:
                            insufficient.append(
                                {
                                    "product_id": product.id,
                                    "product_name": product.name,
                                    "requested": item.quantity,
                                    "available": product.quantity,
                                }
                            )

                    if missing_products:
                        log.error(
                            "STRIPE_WEBHOOK_PRODUCTS_MISSING order_id=%s serial=%s details=%s request_id=%s",
                            order.pk,
                            order.order_serial_number,
                            missing_products,
                            rid,
                        )
                        audit_event(
                            "STRIPE_WEBHOOK_PRODUCTS_MISSING",
                            actor=actor,
                            request_id=rid,
                            order_id=order.pk,
                            serial=order.order_serial_number,
                            email_mask=mask_email(order.user_email),
                            extra={"details": missing_products},
                        )
                        return HttpResponse(status=409)

                    if insufficient:
                        log.error(
                            "STRIPE_WEBHOOK_INSUFFICIENT_STOCK order_id=%s serial=%s details=%s request_id=%s",
                            order.pk,
                            order.order_serial_number,
                            insufficient,
                            rid,
                        )
                        audit_event(
                            "STRIPE_WEBHOOK_INSUFFICIENT_STOCK",
                            actor=actor,
                            request_id=rid,
                            order_id=order.pk,
                            serial=order.order_serial_number,
                            email_mask=mask_email(order.user_email),
                            extra={"details": insufficient},
                        )
                        return HttpResponse(status=409)

                    # stock decrement
                    for item in items:
                        product = products_map[item.product_id]
                        product.quantity = product.quantity - item.quantity
                        product.is_available = product.quantity > 0
                        product.save(update_fields=["quantity", "is_available"])

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

                    # clear cart after successful payment
                    if order.user_id:
                        cart = Cart.objects.filter(user=order.user).first()
                        if cart:
                            cart.items.all().delete()

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

            # except Exception:
            #     log.exception(
            #         "STRIPE_WEBHOOK_PROCESSING_FAILED event_type=%s event_id=%s request_id=%s",
            #         event_type,
            #         event.get("id"),
            #         rid,
            #     )
            #     audit_event(
            #         "STRIPE_WEBHOOK_PROCESSING_FAILED",
            #         actor=actor,
            #         request_id=rid,
            #         extra={
            #             "event_type": event_type,
            #             "event_id": event.get("id"),
            #         },
            #     )
            #     return HttpResponse(status=500)

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

        elif event_type == "checkout.session.async_payment_succeeded":
            session = data_object
            log.info(
                "STRIPE_ASYNC_PAYMENT_SUCCEEDED session_id=%s event_id=%s request_id=%s",
                session.get("id"),
                event.get("id"),
                rid,
            )
            audit_event(
                "STRIPE_ASYNC_PAYMENT_SUCCEEDED",
                actor=actor,
                request_id=rid,
                extra={
                    "session_id": session.get("id"),
                    "event_id": event.get("id"),
                },
            )

        return HttpResponse(status=200)