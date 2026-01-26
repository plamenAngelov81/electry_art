from django.db import models
from decimal import Decimal
from electry_art.products.models import Product
from electry_art.user_profiles.models import UserProfile


class Order(models.Model):
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    order_serial_number = models.CharField(max_length=100, unique=True)
    full_name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    user_email = models.EmailField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_accepted = models.BooleanField(default=False, db_index=True)
    is_sent = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_serial_number} by {self.full_name}"

    @property
    def total_price(self):
        # Decimal safe
        return sum((item.total_price for item in self.items.all()), Decimal('0.00'))


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=255)  # snapshot
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        name = self.product_name or (self.product.name if self.product else "Deleted product")
        return f"{name} x {self.quantity}"

    @property
    def total_price(self):
        return self.price * self.quantity


class Inquiry(models.Model):
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inquiry from {self.email} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"