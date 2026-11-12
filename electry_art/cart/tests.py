"""Cart tests: product availability and problem #24-A concurrency.

Run: python manage.py test electry_art.cart.tests -v 2
Concurrent database tests require PostgreSQL.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connection
from django.test import Client, SimpleTestCase, TransactionTestCase
from django.urls import reverse

from electry_art.cart.models import Cart, CartItem
from electry_art.products.models import (
    Product, ProductType, ProductMaterial, ProductColor,
)

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


class CartConcurrencyTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='cart24_user', password='testpass123')
        product_type = ProductType.objects.create(name='Test Type 24')
        material = ProductMaterial.objects.create(name='Wood 24')
        color = ProductColor.objects.create(name='Brown 24')
        self.product = Product.objects.create(
            name_en='Test Product 24', name_bg='Тестов продукт 24',
            description_en='Test description', description_bg='Описание',
            serial_number='TEST24A', type=product_type, material=material,
            color=color, size='10x10', weight='1.000', price='9.99',
            product_image='test_images/product.jpg', is_available=True,
        )
        self.cart = Cart.objects.create(user=self.user)

    def test_two_concurrent_adds_to_existing_cart_item(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Concurrent transaction test requires PostgreSQL')
        item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        start = Barrier(2)
        url = reverse('add_to_cart', kwargs={'pk': self.product.pk})

        def add_once(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.user)
                start.wait(timeout=10)
                response = client.post(url)
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            codes = list(executor.map(add_once, range(2)))
        self.assertEqual(codes, [302, 302])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)

    def test_two_concurrent_first_adds_create_one_item_with_quantity_two(self):
        """Two HTTP requests add the same product to an initially empty cart.

        The barrier synchronizes request starts, but cannot guarantee that both
        requests reach get_or_create at precisely the same instant.
        """
        if connection.vendor != 'postgresql':
            self.skipTest('Concurrent transaction test requires PostgreSQL')

        url = reverse('add_to_cart', kwargs={'pk': self.product.pk})
        start = Barrier(2)

        def add_once(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.user)
                start.wait(timeout=10)
                return client.post(url).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            codes = list(executor.map(add_once, range(2)))

        self.assertEqual(codes, [302, 302])
        items = CartItem.objects.filter(cart=self.cart, product=self.product)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().quantity, 2)

    def test_first_add_creates_single_row(self):
        client = Client()
        client.force_login(self.user)
        url = reverse('add_to_cart', kwargs={'pk': self.product.pk})
        self.assertEqual(client.post(url).status_code, 302)
        self.assertEqual(client.post(url).status_code, 302)
        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 1)
        self.assertEqual(CartItem.objects.get(cart=self.cart, product=self.product).quantity, 2)

    def test_two_concurrent_guest_adds_preserve_both_updates(self):
        """Exercise two HTTP requests sharing the same guest session cookie."""
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL advisory locks required')

        original = SessionStore()
        original['cart'] = {str(self.product.pk): 2}
        original.save()
        key = original.session_key
        url = reverse('add_to_cart', kwargs={'pk': self.product.pk})
        start = Barrier(2)

        # Delay *after* SessionCart has loaded its session snapshot.
        # Without end-to-end request locking, concurrent requests can
        # overwrite each other's updates.
        from electry_art.cart.utils import SessionCart
        real_init = SessionCart.__init__

        def delayed_init(cart_self, request):
            real_init(cart_self, request)
            time.sleep(0.15)

        def add_once(_):
            close_old_connections()
            try:
                client = Client()
                client.cookies[settings.SESSION_COOKIE_NAME] = key
                start.wait(timeout=10)
                return client.post(url).status_code
            finally:
                close_old_connections()

        with patch.object(SessionCart, '__init__', delayed_init):
            with ThreadPoolExecutor(max_workers=2) as executor:
                codes = list(executor.map(add_once, range(2)))

        self.assertEqual(codes, [302, 302])
        final = SessionStore(session_key=key)
        self.assertEqual(final['cart'][str(self.product.pk)], 4)
