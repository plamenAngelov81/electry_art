from datetime import timedelta, date
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
# from django.http import Http404
from django.urls import reverse_lazy
from django.views import View, generic
from django.shortcuts import render, redirect
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

        cart = Cart.objects.filter(user=request.user).first()
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
            with transaction.atomic():
                log.info("ORDER_CREATE_STARTED user_id=%s request_id=%s", actor.id, rid)
                audit_event("ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                order = Order.objects.create(
                    user=request.user,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                    user_email=request.user.email or None,
                )

                order.order_serial_number = build_order_serial(order.id)
                order.save(update_fields=["order_serial_number"])

                items_qs = cart.items.select_related("product")
                items_count = items_qs.count()

                for item in items_qs:
                    product = item.product
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=item.quantity,
                        price=product.price,
                    )

                cart.items.all().delete()

                log.info(
                    "ORDER_CREATED order_id=%s serial=%s items=%s user_id=%s request_id=%s",
                    order.pk,
                    order.order_serial_number,
                    items_count,
                    actor.id,
                    rid,
                )
                audit_event(
                    "ORDER_CREATED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                    email_mask=mask_email(order.user_email),
                    extra={"items": items_count},
                )

                transaction.on_commit(
                    lambda: checkout_completed.send(
                        sender=CheckoutView,
                        order=order,
                        user=request.user,
                        request_id=rid,  # <--- добавяме request_id към сигнала
                    )
                )

                log.info("CHECKOUT_COMPLETED_SIGNAL_QUEUED order_id=%s request_id=%s", order.pk, rid)
                audit_event(
                    "CHECKOUT_COMPLETED_SIGNAL_QUEUED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                )

        except Exception:  # noqa: BLE001
            log.exception("ORDER_CREATE_FAILED user_id=%s request_id=%s", actor.id, rid)
            audit_event("ORDER_CREATE_FAILED", actor=actor, request_id=rid)
            raise

        return redirect("order_success", order_id=order.pk)


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


class GuestCheckoutView(View):
    @staticmethod
    def _build_cart_context(cart):
        items = list(cart.items())  # [("12", 2), ("5", 1)]
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
            cart_items.append({"product": product, "quantity": quantity, "total": item_total})
            total += item_total

        return {"items": items, "products": products, "cart_items": cart_items, "total": total}

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
                rid, bad_fields
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
            with transaction.atomic():
                log.info("GUEST_ORDER_CREATE_STARTED request_id=%s", rid)
                audit_event("GUEST_ORDER_CREATE_STARTED", actor=actor, request_id=rid)

                order = Order.objects.create(
                    user=None,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                    user_email=form.cleaned_data["email"],
                )

                order.order_serial_number = build_order_serial(order.id)
                order.save(update_fields=["order_serial_number"])

                items_count = 0
                for pid, quantity in ctx["items"]:
                    pid = int(pid)
                    product = ctx["products"].get(pid)
                    if not product:
                        continue

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,  # snapshot
                        quantity=quantity,
                        price=product.price,  # snapshot
                    )
                    items_count += 1

                cart.clear()

                log.info(
                    "GUEST_ORDER_CREATED order_id=%s serial=%s items=%s request_id=%s",
                    order.pk,
                    order.order_serial_number,
                    items_count,
                    rid,
                )
                audit_event(
                    "GUEST_ORDER_CREATED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                    email_mask=mask_email(order.user_email),
                    extra={"items": items_count},
                )

                transaction.on_commit(
                    lambda: checkout_completed.send(
                        sender=GuestCheckoutView,
                        order=order,
                        user=None,
                        request_id=rid,  # <--- важно за receiver-а
                    )
                )

                log.info("GUEST_CHECKOUT_COMPLETED_SIGNAL_QUEUED order_id=%s request_id=%s", order.pk, rid)
                audit_event(
                    "GUEST_CHECKOUT_COMPLETED_SIGNAL_QUEUED",
                    actor=actor,
                    request_id=rid,
                    order_id=order.pk,
                    serial=order.order_serial_number,
                )

        except Exception:  # noqa: BLE001
            log.exception("GUEST_ORDER_CREATE_FAILED request_id=%s", rid)
            audit_event("GUEST_ORDER_CREATE_FAILED", actor=actor, request_id=rid)
            raise

        return redirect("order_success", order_id=order.pk)


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


