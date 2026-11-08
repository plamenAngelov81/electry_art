
from decimal import Decimal

from django.test import SimpleTestCase

from electry_art.cart.models import CartItem
from electry_art.products.models import Product


class CartItemMissingOrUnavailableProductTests(SimpleTestCase):
    def test_deleted_product_string_is_safe(self):
        item = CartItem(product=None, quantity=2)
        self.assertEqual(str(item), "Deleted product x 2")

    def test_deleted_product_has_zero_payable_total(self):
        item = CartItem(product=None, quantity=2)
        self.assertEqual(item.total_price, Decimal("0.00"))

    def test_unavailable_product_has_zero_payable_total(self):
        product = Product(price=Decimal("12.50"), is_available=False)
        item = CartItem(product=product, quantity=2)
        self.assertEqual(item.total_price, Decimal("0.00"))

    def test_available_product_keeps_normal_total(self):
        product = Product(price=Decimal("12.50"), is_available=True)
        item = CartItem(product=product, quantity=2)
        self.assertEqual(item.total_price, Decimal("25.00"))
