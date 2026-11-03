
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, OrderItem
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