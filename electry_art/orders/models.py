from django.core.validators import MinValueValidator
from django.db import models
from decimal import Decimal
from electry_art.products.models import Product
from electry_art.user_profiles.models import UserProfile
from django.conf import settings


class OrderItemStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    order_serial_number = models.CharField(
        max_length=100, unique=True
    )

    full_name = models.CharField(
        max_length=100
    )
    address = models.TextField()

    phone = models.CharField(
        max_length=20
    )
    user_email = models.EmailField(
        max_length=50,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    is_accepted = models.BooleanField(
        default=False,
        db_index=True
    )

    is_sent = models.BooleanField(
        default=False,
        db_index=True
    )

    is_paid = models.BooleanField(
        default=False,
        db_index=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    payment_provider = models.CharField(
        max_length=20,
        default="stripe"
    )

    stripe_checkout_session_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )

    stripe_expected_amount = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    stripe_expected_currency = models.CharField(
        max_length=3,
        default="eur",
    )


    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_serial_number} by {self.full_name}"

    @property
    def total_price(self):
        return sum(
            (
                item.total_price
                for item in self.items.filter(status=OrderItemStatus.ACTIVE)
            ),
            Decimal("0.00")
        )



class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    product_name = models.CharField(
        max_length=255
    )

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )

    status = models.CharField(
        max_length=20,
        choices=OrderItemStatus.choices,
        default=OrderItemStatus.ACTIVE,
        db_index=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_order_items",
    )

    cancelled_quantity = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )

    cancel_reason = models.TextField(
        blank=True,
    )

    def __str__(self):
        name = self.product_name or (self.product.name if self.product else "Deleted product")
        return f"{name} x {self.quantity}"

    @property
    def active_quantity(self):
        return self.quantity - self.cancelled_quantity

    @property
    def is_partially_cancelled(self):
        return (
                0 < self.cancelled_quantity < self.quantity
        )

    @property
    def total_price(self):
        return self.price * self.active_quantity