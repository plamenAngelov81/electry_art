
from unittest.mock import patch
from types import SimpleNamespace
from decimal import Decimal

from django.test import TestCase, TransactionTestCase, Client, override_settings, SimpleTestCase
from django.urls import reverse

from .models import Order, OrderItem
from electry_art.cart.models import Cart, CartItem
from electry_art.user_profiles.models import UserProfile, Address
from electry_art.products.models import (
    Product,
    ProductType,
    ProductMaterial,
    ProductColor,
)


@override_settings(STRIPE_WEBHOOK_SECRET="test_webhook_secret", STRIPE_SECRET_KEY="sk_test_example")
class StripeWebhookTests(TestCase):

    def setUp(self):
        self.order = Order.objects.create(
            order_serial_number="ORD-TEST-000001",
            full_name="Test Customer",
            address="Test Address",
            phone="0888000000",
            user_email="test@example.com",
            is_paid=False,
            payment_provider="stripe",
            stripe_checkout_session_id="cs_test_123",
            stripe_expected_amount=3000,
            stripe_expected_currency="eur",
        )

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_paid_order_with_missing_product(self, mock_construct_event):
        OrderItem.objects.create(
            order=self.order,
            product=None,
            product_name="Deleted Test Product",
            quantity=2,
            price="15.00",
        )

        mock_construct_event.return_value = {
            "id": "evt_test_missing_product",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_intent": "pi_test_456",
                    "amount_total": 3000,
                    "currency": "eur",
                    "mode": "payment",
                    "livemode": False,
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
                        "order_serial_number": self.order.order_serial_number,
                    },
                }
            },
        }

        response = self.client.post(
            reverse("stripe_webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.order.is_paid)
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(
            self.order.stripe_payment_intent_id,
            "pi_test_456",
        )

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_paid_order_with_unavailable_product(self, mock_construct_event):
        product_type = ProductType.objects.create(name="Decorations")
        material = ProductMaterial.objects.create(name="Wood")
        color = ProductColor.objects.create(name="Brown")

        product = Product.objects.create(
            name="Test Decoration",
            serial_number="TEST-00002",
            type=product_type,
            material=material,
            color=color,
            size="10x10 cm",
            weight="0.250",
            price="15.00",
            is_available=True,
        )

        OrderItem.objects.create(
            order=self.order,
            product=product,
            product_name=product.name,
            quantity=2,
            price=product.price,
        )

        # Продуктът става недостъпен след създаване на поръчката.
        product.is_available = False
        product.save(update_fields=["is_available"])

        mock_construct_event.return_value = {
            "id": "evt_test_unavailable_product",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_intent": "pi_test_789",
                    "amount_total": 3000,
                    "currency": "eur",
                    "mode": "payment",
                    "livemode": False,
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
                        "order_serial_number": self.order.order_serial_number,
                    },
                }
            },
        }

        response = self.client.post(
            reverse("stripe_webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.order.is_paid)
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(
            self.order.stripe_payment_intent_id,
            "pi_test_789",
        )

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_session_id(self, mock_construct_event):
        mock_construct_event.return_value = {
            "id": "evt_wrong_session",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_WRONG",
                    "payment_intent": "pi_test_wrong",
                    "amount_total": 3000,
                    "currency": "eur",
                    "mode": "payment",
                    "livemode": False,
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
                        "order_serial_number": self.order.order_serial_number,
                    },
                }
            },
        }

        response = self.client.post(
            reverse("stripe_webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)
        self.assertEqual(
            self.order.stripe_checkout_session_id,
            "cs_test_123",
        )


    def _post_reconciliation_event(self, mock_construct_event, **overrides):
        session = {
            "id": "cs_test_123",
            "payment_intent": "pi_test_reconcile",
            "payment_status": "paid",
            "amount_total": 3000,
            "currency": "eur",
            "mode": "payment",
            "livemode": False,
            "client_reference_id": str(self.order.pk),
            "metadata": {
                "order_id": str(self.order.pk),
                "order_serial_number": self.order.order_serial_number,
            },
        }
        session.update(overrides)
        mock_construct_event.return_value = {
            "id": "evt_reconciliation",
            "type": "checkout.session.completed",
            "data": {"object": session},
        }
        response = self.client.post(
            reverse("stripe_webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )
        self.order.refresh_from_db()
        return response

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_amount(self, mock_construct_event):
        response = self._post_reconciliation_event(mock_construct_event, amount_total=2000)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_currency(self, mock_construct_event):
        response = self._post_reconciliation_event(mock_construct_event, currency="usd")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_mode(self, mock_construct_event):
        response = self._post_reconciliation_event(mock_construct_event, mode="subscription")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_order_reference(self, mock_construct_event):
        response = self._post_reconciliation_event(
            mock_construct_event, client_reference_id="99999999"
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_environment(self, mock_construct_event):
        response = self._post_reconciliation_event(mock_construct_event, livemode=True)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_accepts_matching_payment(self, mock_construct_event):
        response = self._post_reconciliation_event(mock_construct_event)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_missing_expected_amount(self, mock_construct_event):
        self.order.stripe_expected_amount = None
        self.order.save(update_fields=["stripe_expected_amount"])
        response = self._post_reconciliation_event(mock_construct_event)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_wrong_metadata_serial(self, mock_construct_event):
        response = self._post_reconciliation_event(
            mock_construct_event,
            metadata={"order_id": str(self.order.pk), "order_serial_number": "WRONG"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.order.is_paid)


class StripeCheckoutAmountTests(TestCase):
    """Checkout must persist the exact amount sent to Stripe, in cents."""

    def setUp(self):
        product_type = ProductType.objects.create(name="Decorations")
        material = ProductMaterial.objects.create(name="Wood")
        color = ProductColor.objects.create(name="Brown")
        self.product = Product.objects.create(
            name="Test Decoration",
            serial_number="TEST-AMOUNT-001",
            type=product_type,
            material=material,
            color=color,
            size="10x10 cm",
            weight="0.250",
            price=Decimal("12.50"),
            is_available=True,
        )

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_registered_checkout_saves_expected_amount(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            id="cs_test_registered", url="https://checkout.stripe.com/test"
        )
        user = UserProfile.objects.create_user(
            username="testbuyer", email="buyer@example.com", password="test-password"
        )
        address = Address.objects.create(
            user=user,
            country="Bulgaria",
            town="Gabrovo",
            address="Test street 123",
            phone_num="0888000000",
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=3)
        self.client.force_login(user)

        response = self.client.post(
            reverse("checkout"), {"delivery_address": str(address.pk)}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.com/test")
        order = Order.objects.get(user=user)
        self.assertEqual(order.stripe_expected_amount, 3750)
        self.assertEqual(order.stripe_expected_currency, "eur")
        self.assertEqual(order.stripe_checkout_session_id, "cs_test_registered")
        sent_items = mock_create.call_args.kwargs["line_items"]
        self.assertEqual(
            sum(item["price_data"]["unit_amount"] * item["quantity"] for item in sent_items),
            order.stripe_expected_amount,
        )

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_guest_checkout_saves_expected_amount(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            id="cs_test_guest", url="https://checkout.stripe.com/test"
        )
        session = self.client.session
        session["cart"] = {str(self.product.pk): 3}
        session.save()

        response = self.client.post(
            reverse("guest_checkout"),
            {
                "full_name": "Test Customer",
                "phone": "0888000000",
                "email": "guest@example.com",
                "address": "Test street 123, Gabrovo",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.com/test")
        order = Order.objects.get(user__isnull=True, user_email="guest@example.com")
        self.assertEqual(order.stripe_expected_amount, 3750)
        self.assertEqual(order.stripe_expected_currency, "eur")
        self.assertEqual(order.stripe_checkout_session_id, "cs_test_guest")
        sent_items = mock_create.call_args.kwargs["line_items"]
        self.assertEqual(
            sum(item["price_data"]["unit_amount"] * item["quantity"] for item in sent_items),
            order.stripe_expected_amount,
        )


@override_settings(STRIPE_SECRET_KEY="sk_test_example")
class CheckoutIdempotencyTests(StripeCheckoutAmountTests):
    """Repeated POSTs must reuse the same order and Stripe Checkout session."""

    def _registered(self):
        user = UserProfile.objects.create_user(
            username="retrybuyer", email="retry@example.com", password="test-password"
        )
        address = Address.objects.create(
            user=user, country="Bulgaria", town="Gabrovo",
            address="Test street 123", phone_num="0888000000",
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        self.client.force_login(user)
        self.client.get(reverse("checkout"))
        return address, cart

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_registered_duplicate_post_reuses_session(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            id="cs_retry_registered", url="https://checkout.stripe.com/retry"
        )
        address, _ = self._registered()
        url = reverse("checkout")
        first = self.client.post(url, {"delivery_address": str(address.pk)})
        second = self.client.post(url, {"delivery_address": str(address.pk)})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.filter(user=address.user).count(), 1)
        self.assertEqual(mock_create.call_count, 1)
        self.assertTrue(mock_create.call_args.kwargs["idempotency_key"])

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_guest_duplicate_post_reuses_session(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            id="cs_retry_guest", url="https://checkout.stripe.com/retry"
        )
        session = self.client.session
        session["cart"] = {str(self.product.pk): 2}
        session.save()
        url = reverse("guest_checkout")
        self.client.get(url)
        payload = {
            "full_name": "Guest Customer", "phone": "0888000000",
            "email": "retryguest@example.com", "address": "Gabrovo street 1",
        }
        first = self.client.post(url, payload)
        second = self.client.post(url, payload)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.filter(user_email=payload["email"]).count(), 1)
        self.assertEqual(mock_create.call_count, 1)

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_changed_cart_new_checkout_creates_new_attempt(self, mock_create):
        mock_create.side_effect = [
            SimpleNamespace(id="cs_first", url="https://checkout.stripe.com/first"),
            SimpleNamespace(id="cs_second", url="https://checkout.stripe.com/second"),
        ]
        address, cart = self._registered()
        url = reverse("checkout")
        self.assertEqual(self.client.post(url, {"delivery_address": str(address.pk)}).status_code, 302)
        cart_item = cart.items.get(product=self.product)
        cart_item.quantity = 3
        cart_item.save(update_fields=["quantity"])
        self.client.get(url)
        self.assertEqual(self.client.post(url, {"delivery_address": str(address.pk)}).status_code, 302)
        self.assertEqual(Order.objects.filter(user=address.user).count(), 2)
        self.assertEqual(mock_create.call_count, 2)

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_paid_order_allows_new_checkout(self, mock_create):
        mock_create.side_effect = [
            SimpleNamespace(id="cs_paid_first", url="https://checkout.stripe.com/first"),
            SimpleNamespace(id="cs_paid_second", url="https://checkout.stripe.com/second"),
        ]
        address, _ = self._registered()
        url = reverse("checkout")
        self.client.post(url, {"delivery_address": str(address.pk)})
        order = Order.objects.get(user=address.user)
        order.is_paid = True
        order.save(update_fields=["is_paid"])
        self.client.get(url)
        self.client.post(url, {"delivery_address": str(address.pk)})
        self.assertEqual(Order.objects.filter(user=address.user).count(), 2)
        self.assertEqual(mock_create.call_count, 2)


@override_settings(STRIPE_SECRET_KEY="sk_test_example")
class CheckoutTransactionBoundaryTests(CheckoutIdempotencyTests):
    """The Stripe request must happen after local checkout locks commit."""

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_registered_stripe_call_outside_checkout_atomic(self, mock_create):
        from django.db import connection
        address, _ = self._registered()
        initial_depth = len(connection.savepoint_ids)

        def fake_stripe(**kwargs):
            self.assertEqual(len(connection.savepoint_ids), initial_depth)
            order = Order.objects.get(user=address.user)
            self.assertTrue(order.checkout_processing_claim)
            self.assertEqual(order.stripe_expected_amount, 2500)
            return SimpleNamespace(id="cs_outside_reg", url="https://checkout.stripe.com/outside")

        mock_create.side_effect = fake_stripe
        response = self.client.post(reverse("checkout"), {"delivery_address": str(address.pk)})
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=address.user)
        self.assertEqual(order.checkout_processing_claim, "")

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_guest_stripe_call_outside_checkout_atomic(self, mock_create):
        from django.db import connection
        session = self.client.session
        session["cart"] = {str(self.product.pk): 2}
        session.save()
        initial_depth = len(connection.savepoint_ids)

        def fake_stripe(**kwargs):
            self.assertEqual(len(connection.savepoint_ids), initial_depth)
            order = Order.objects.get(user_email="guest9@example.com")
            self.assertTrue(order.checkout_processing_claim)
            return SimpleNamespace(id="cs_outside_guest", url="https://checkout.stripe.com/outside")

        mock_create.side_effect = fake_stripe
        response = self.client.post(reverse("guest_checkout"), {
            "full_name": "Guest", "phone": "0888000000",
            "email": "guest9@example.com", "address": "Gabrovo",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get(user_email="guest9@example.com").checkout_processing_claim, "")

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_second_post_during_stripe_call_is_rejected_without_duplicate(self, mock_create):
        address, _ = self._registered()
        responses = []

        def fake_stripe(**kwargs):
            responses.append(self.client.post(reverse("checkout"), {
                "delivery_address": str(address.pk),
            }))
            return SimpleNamespace(id="cs_inflight", url="https://checkout.stripe.com/inflight")

        mock_create.side_effect = fake_stripe
        response = self.client.post(reverse("checkout"), {"delivery_address": str(address.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(responses[0].status_code, 409)
        self.assertEqual(Order.objects.filter(user=address.user).count(), 1)
        self.assertEqual(mock_create.call_count, 1)

    @patch("electry_art.orders.views.stripe.checkout.Session.create")
    def test_stripe_failure_can_retry_same_order(self, mock_create):
        import stripe
        address, _ = self._registered()
        mock_create.side_effect = [
            stripe.error.APIConnectionError("Network unavailable"),
            SimpleNamespace(id="cs_retry_after_error", url="https://checkout.stripe.com/recovered"),
        ]
        first = self.client.post(reverse("checkout"), {"delivery_address": str(address.pk)})
        self.assertEqual(first.status_code, 200)
        second = self.client.post(reverse("checkout"), {"delivery_address": str(address.pk)})
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Order.objects.filter(user=address.user).count(), 1)
        self.assertEqual(mock_create.call_count, 2)
        self.assertEqual(mock_create.call_args_list[0].kwargs["idempotency_key"],
                         mock_create.call_args_list[1].kwargs["idempotency_key"])


@override_settings(STRIPE_WEBHOOK_SECRET="test_webhook_secret", STRIPE_SECRET_KEY="sk_test_example")
class PaidCartPreservationTests(StripeWebhookTests):
    """Regression checks for audit finding 10."""

    def _product(self, serial):
        pt, _ = ProductType.objects.get_or_create(name="Paid Cart Test Type")
        material, _ = ProductMaterial.objects.get_or_create(name="Paid Cart Test Material")
        color, _ = ProductColor.objects.get_or_create(name="Paid Cart Test Color")
        return Product.objects.create(
            name=serial, serial_number=serial, type=pt, material=material,
            color=color, size="10x10", weight="0.250", price=Decimal("15.00"),
            is_available=True,
        )

    def _paid_webhook(self, mock_event):
        return self._post_reconciliation_event(mock_event)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_paid_order_preserves_new_products_and_extra_quantities(self, mock_event):
        user = UserProfile.objects.create_user(username="cartbuyer", password="password")
        self.order.user = user
        self.order.save(update_fields=["user"])
        purchased = self._product("PURCHASED-10")
        added = self._product("ADDED-10")
        OrderItem.objects.create(order=self.order, product=purchased, product_name=purchased.name, quantity=2, price="15.00")
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=purchased, quantity=5)
        CartItem.objects.create(cart=cart, product=added, quantity=4)
        response = self._paid_webhook(mock_event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.get(cart=cart, product=purchased).quantity, 3)
        self.assertEqual(CartItem.objects.get(cart=cart, product=added).quantity, 4)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_paid_order_removes_exactly_purchased_quantity(self, mock_event):
        user = UserProfile.objects.create_user(username="cartbuyer2", password="password")
        self.order.user = user
        self.order.save(update_fields=["user"])
        product = self._product("PURCHASED-EXACT-10")
        OrderItem.objects.create(order=self.order, product=product, product_name=product.name, quantity=2, price="15.00")
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)
        self.assertEqual(self._paid_webhook(mock_event).status_code, 200)
        self.assertFalse(CartItem.objects.filter(cart=cart, product=product).exists())

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_replayed_webhook_does_not_deduct_twice(self, mock_event):
        user = UserProfile.objects.create_user(username="cartbuyer3", password="password")
        self.order.user = user
        self.order.save(update_fields=["user"])
        product = self._product("PURCHASED-REPLAY-10")
        OrderItem.objects.create(order=self.order, product=product, product_name=product.name, quantity=2, price="15.00")
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=5)
        self.assertEqual(self._paid_webhook(mock_event).status_code, 200)
        self.assertEqual(self._paid_webhook(mock_event).status_code, 200)
        self.assertEqual(CartItem.objects.get(cart=cart, product=product).quantity, 3)

    def test_guest_paid_cart_deduction_runs_once(self):
        from electry_art.orders.views import subtract_purchased_from_guest_cart
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware
        product = self._product("GUEST-PURCHASED-10")
        added = self._product("GUEST-ADDED-10")
        OrderItem.objects.create(order=self.order, product=product, product_name=product.name, quantity=2, price="15.00")
        request = RequestFactory().get("/")
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session["cart"] = {str(product.pk): 5, str(added.pk): 1}
        self.assertTrue(subtract_purchased_from_guest_cart(request, self.order))
        self.assertEqual(request.session["cart"], {str(product.pk): 3, str(added.pk): 1})
        self.assertFalse(subtract_purchased_from_guest_cart(request, self.order))
        self.assertEqual(request.session["cart"][str(product.pk)], 3)


@override_settings(STRIPE_WEBHOOK_SECRET="test_webhook_secret", STRIPE_SECRET_KEY="sk_test_example")
class GuestCartReconciliationTests(TestCase):
    """Guest cart reconciles from paid orders without visiting Stripe success URL."""

    def setUp(self):
        from electry_art.cart.utils import SessionCart
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware
        self.request = RequestFactory().get('/')
        SessionMiddleware(lambda request: None).process_request(self.request)
        self.cart = SessionCart(self.request)
        product_type = ProductType.objects.create(name="Guest Cart Type")
        material = ProductMaterial.objects.create(name="Guest Cart Material")
        color = ProductColor.objects.create(name="Guest Cart Color")
        self.product = Product.objects.create(
            name="Guest Cart Product", serial_number="GUEST-CART-11",
            type=product_type, material=material, color=color,
            size="10x10 cm", weight="0.250", price=Decimal("15.00"),
            is_available=True,
        )
        self.cart.add(self.product.pk, 5)
        self.order = Order.objects.create(
            order_serial_number="ORD-GUEST-11", full_name="Guest", address="Gabrovo",
            phone="0888000000", user_email="guest11@example.com",
            guest_cart_id=self.cart.guest_cart_id, is_paid=False,
            stripe_checkout_session_id="cs_guest_11", stripe_expected_amount=3000,
            stripe_expected_currency="eur",
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, price="15.00",
        )

    def _webhook(self, mock_event):
        mock_event.return_value = {
            "id": "evt_guest_11", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_guest_11", "payment_intent": "pi_guest_11",
                "payment_status": "paid", "amount_total": 3000, "currency": "eur",
                "mode": "payment", "livemode": False,
                "client_reference_id": str(self.order.pk),
                "metadata": {"order_id": str(self.order.pk),
                             "order_serial_number": self.order.order_serial_number},
            }},
        }
        return self.client.post(reverse('stripe_webhook'), data=b'{}',
                                content_type='application/json',
                                HTTP_STRIPE_SIGNATURE='test_signature')

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_webhook_paid_without_success_page_reconciles_on_next_cart_access(self, mock_event):
        from electry_art.cart.utils import SessionCart
        self.assertEqual(self._webhook(mock_event).status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(SessionCart(self.request).cart[str(self.product.pk)], 3)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_repeated_webhook_and_cart_access_do_not_deduct_twice(self, mock_event):
        from electry_art.cart.utils import SessionCart
        self.assertEqual(self._webhook(mock_event).status_code, 200)
        self.assertEqual(self._webhook(mock_event).status_code, 200)
        self.assertEqual(SessionCart(self.request).cart[str(self.product.pk)], 3)
        self.assertEqual(SessionCart(self.request).cart[str(self.product.pk)], 3)

    @patch("electry_art.orders.views.stripe.Webhook.construct_event")
    def test_new_quantities_after_payment_are_preserved(self, mock_event):
        from electry_art.cart.utils import SessionCart
        self.assertEqual(self._webhook(mock_event).status_code, 200)
        self.assertEqual(SessionCart(self.request).cart[str(self.product.pk)], 3)
        SessionCart(self.request).add(self.product.pk, 4)
        self.assertEqual(SessionCart(self.request).cart[str(self.product.pk)], 7)


class OrderItemCancellationTests(TestCase):
    """Regression checks for cancellation validation and quantity bounds."""

    def setUp(self):
        self.staff = UserProfile.objects.create_user(
            username="cancel_staff_17", email="cancel_staff_17@example.com", password="test-password", is_staff=True,
        )
        self.customer = UserProfile.objects.create_user(
            username="cancel_customer_17", email="cancel_customer_17@example.com", password="test-password",
        )
        self.order = Order.objects.create(
            order_serial_number="ORD-CANCEL-17", full_name="Customer",
            address="Gabrovo", phone="0888000000", is_paid=True,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product_name="Cancellation test product",
            quantity=5, price=Decimal("10.00"),
        )
        self.url = reverse("cancel_order_item", kwargs={"pk": self.item.pk})
        self.client.force_login(self.staff)

    def test_partial_then_full_cancellation(self):
        from .models import OrderItemStatus
        response = self.client.post(self.url, {"cancel_quantity": "3"})
        self.assertRedirects(response, reverse("order_edit", kwargs={"pk": self.order.pk}), fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.cancelled_quantity, 3)
        self.assertEqual(self.item.status, OrderItemStatus.ACTIVE)
        self.assertEqual(self.item.cancelled_by, self.staff)
        self.assertIsNotNone(self.item.cancelled_at)
        self.client.post(self.url, {"cancel_quantity": "2"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.cancelled_quantity, 5)
        self.assertEqual(self.item.status, OrderItemStatus.CANCELLED)

    def test_invalid_and_excessive_quantities_leave_item_unchanged(self):
        for value in ("abc", "", "0", "-1", "6"):
            with self.subTest(value=value):
                response = self.client.post(self.url, {"cancel_quantity": value})
                self.assertEqual(response.status_code, 302)
                self.item.refresh_from_db()
                self.assertEqual(self.item.cancelled_quantity, 0)

    def test_second_request_revalidates_remaining_quantity(self):
        self.client.post(self.url, {"cancel_quantity": "3"})
        self.client.post(self.url, {"cancel_quantity": "3"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.cancelled_quantity, 3)

    def test_non_staff_cannot_cancel(self):
        self.client.force_login(self.customer)
        response = self.client.post(self.url, {"cancel_quantity": "1"})
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.cancelled_quantity, 0)

    def test_database_rejects_cancelled_quantity_above_quantity(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderItem.objects.filter(pk=self.item.pk).update(cancelled_quantity=6)
        self.item.refresh_from_db()
        self.assertEqual(self.item.cancelled_quantity, 0)


class OrderItemCancellationConcurrencyTests(TransactionTestCase):
    """Exercise two real PostgreSQL connections through the cancellation view."""

    def test_simultaneous_cancellations_do_not_exceed_remaining_quantity(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection, close_old_connections
        from .models import OrderItemStatus

        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row-level locking is required")

        staff = UserProfile.objects.create_user(
            username="concurrency_staff_17",
            email="concurrency_staff_17@example.com",
            password="test-password",
            is_staff=True,
        )
        order = Order.objects.create(
            order_serial_number="ORD-CONCURRENT-17",
            full_name="Concurrent Customer",
            address="Gabrovo",
            phone="0888000000",
            is_paid=True,
        )
        item = OrderItem.objects.create(
            order=order,
            product_name="Concurrency test product",
            quantity=5,
            price=Decimal("10.00"),
        )
        url = reverse("cancel_order_item", kwargs={"pk": item.pk})

        # Hold the first transaction open after its UPDATE but before COMMIT.
        # The second request must wait for the row lock and then revalidate.
        first_saved = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_finished = threading.Event()
        original_save = OrderItem.save

        def delayed_save(instance, *args, **kwargs):
            result = original_save(instance, *args, **kwargs)
            if threading.current_thread().name == "cancel-first":
                first_saved.set()
                if not release_first.wait(timeout=10):
                    raise AssertionError("Timed out waiting to release first transaction")
            return result

        def submit_cancel(started=None, finished=None):
            close_old_connections()
            try:
                client = Client()
                client.force_login(staff)
                if started is not None:
                    started.set()
                response = client.post(url, {"cancel_quantity": "3"})
                return response.status_code
            finally:
                if finished is not None:
                    finished.set()
                connection.close()

        from unittest.mock import patch as mock_patch
        with mock_patch.object(OrderItem, "save", delayed_save):
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cancel") as pool:
                # Executor thread names are 'cancel_0' etc., so set the
                # first worker name explicitly for the controlled pause.
                def first_request():
                    threading.current_thread().name = "cancel-first"
                    return submit_cancel()

                first = pool.submit(first_request)
                try:
                    self.assertTrue(first_saved.wait(timeout=10), "First transaction never reached save")
                    second = pool.submit(submit_cancel, second_started, second_finished)
                    self.assertTrue(second_started.wait(timeout=5), "Second request did not start")
                    self.assertFalse(
                        second_finished.wait(timeout=0.3),
                        "Second request completed while the first held the row lock",
                    )
                finally:
                    release_first.set()
                self.assertEqual(first.result(timeout=10), 302)
                self.assertEqual(second.result(timeout=10), 302)

        item.refresh_from_db()
        self.assertEqual(item.cancelled_quantity, 3)
        self.assertEqual(item.active_quantity, 2)
        self.assertEqual(item.status, OrderItemStatus.ACTIVE)


class OrderItemCancellationPropertyTests(SimpleTestCase):
    def test_not_cancelled(self):
        item = OrderItem(quantity=5, cancelled_quantity=0)
        self.assertFalse(item.is_cancelled)
        self.assertFalse(item.is_partially_cancelled)
        self.assertEqual(item.active_quantity, 5)

    def test_partially_cancelled(self):
        item = OrderItem(quantity=5, cancelled_quantity=2)
        self.assertFalse(item.is_cancelled)
        self.assertTrue(item.is_partially_cancelled)
        self.assertEqual(item.active_quantity, 3)

    def test_fully_cancelled(self):
        item = OrderItem(quantity=5, cancelled_quantity=5)
        self.assertTrue(item.is_cancelled)
        self.assertFalse(item.is_partially_cancelled)
        self.assertEqual(item.active_quantity, 0)
