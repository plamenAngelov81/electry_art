from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from electry_art.products.models import Product, ProductType
from electry_art.cart.models import Cart, CartItem

User = get_user_model()

class CartModelTests(TestCase):
    """
        Have to change every time serial_number whale testing
    """


    def setUp(self):
        self.user = User.objects.create(
            username=f'testuser_{timezone.now().timestamp()}',
            password='testpass',
            first_name='Test',
            last_name='User',
            email='test@example.com'
        )
        self.product_type = ProductType.objects.create(product_type='TestType')
        self.product = Product.objects.create(
            name='Test Product',
            serial_number='SP194486',
            type=self.product_type,
            description='A test product',
            size='10x10x10',
            weight=1.0,
            price=50.0
        )
        self.cart = Cart.objects.create(user=self.user)

    def test_cart_creation(self):
        self.assertEqual(self.cart.user.username, f'testuser_{timezone.now().timestamp()}')
        self.assertEqual(self.cart.items.count(), 0)

    def test_add_item_to_cart(self):
        item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        self.assertEqual(item.total_price, 100.0)
        self.assertEqual(self.cart.items.count(), 1)

    def test_cart_total_price(self):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=3)
        self.assertEqual(self.cart.total_price, 150.0)

    def test_unique_cart_items(self):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        with self.assertRaises(Exception):
            CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)

