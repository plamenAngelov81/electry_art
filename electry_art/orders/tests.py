
from unittest.mock import patch
from types import SimpleNamespace
from decimal import Decimal

from django.test import TestCase, override_settings
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


@override_settings(STRIPE_WEBHOOK_SECRET="test_webhook_secret")
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
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
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

        product.is_available = False
        product.save(update_fields=["is_available"])

        mock_construct_event.return_value = {
            "id": "evt_test_unavailable_product",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_intent": "pi_test_789",
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
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
                    "payment_status": "paid",
                    "client_reference_id": str(self.order.pk),
                    "metadata": {
                        "order_id": str(self.order.pk),
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
