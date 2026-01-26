from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from electry_art.products.models import Product, ProductType
from electry_art.cart.models import Cart, CartItem
from electry_art.user_profiles.models import UserProfile

User = get_user_model()

class CartTests(TestCase):
    def setUp(self):
        self.user = UserProfile.objects.create_user(username='testuser', password='testpass123')
        self.product_type = ProductType.objects.create(product_type='Test Type')
        self.product = Product.objects.create(
            name='Test Product',
            serial_number='TP001',
            type=self.product_type,
            description='A product for testing.',
            size='10x10x10',
            weight=1.0,
            price=9.99
        )
        self.client.login(username='testuser', password='testpass123')

    def test_create_cart_for_user(self):
        response = self.client.get(reverse('cart_view'))
        cart, created = Cart.objects.get_or_create(user=self.user)
        self.assertEqual(cart.user, self.user)
        self.assertEqual(response.status_code, 200)

    def test_add_item_to_cart(self):
        response = self.client.post(reverse('add_to_cart', kwargs={'pk': self.product.pk}))
        cart, created = Cart.objects.get_or_create(user=self.user)
        cart_item = CartItem.objects.get(cart=cart, product=self.product)

        self.assertEqual(cart_item.quantity, 1)
        self.assertEqual(cart_item.total_price, self.product.price)
        self.assertRedirects(response, reverse('cart_view'))

    def test_add_same_item_twice_increases_quantity(self):
        self.client.post(reverse('add_to_cart', kwargs={'pk': self.product.pk}))
        self.client.post(reverse('add_to_cart', kwargs={'pk': self.product.pk}))

        cart, created = Cart.objects.get_or_create(user=self.user)
        cart_item = CartItem.objects.get(cart=cart, product=self.product)
        self.assertEqual(cart_item.quantity, 2)
        self.assertEqual(cart.total_price, self.product.price * 2)

    def test_remove_item_from_cart(self):
        # First add the product
        self.client.post(reverse('add_to_cart', kwargs={'pk': self.product.pk}))

        cart, _ = Cart.objects.get_or_create(user=self.user)
        cart_item = CartItem.objects.filter(cart=cart, product=self.product).first()

        self.assertIsNotNone(cart_item, "CartItem should exist after adding product to cart.")

        # Remove the item
        response = self.client.post(reverse('remove_from_cart', kwargs={'pk': cart_item.pk}))

        # Check that it's gone
        self.assertFalse(CartItem.objects.filter(pk=cart_item.pk).exists())
        self.assertRedirects(response, reverse('cart_view'))