from django.test import TestCase, RequestFactory
from electry_art.cart.utils import SessionCart


class SessionCartTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/')
        self.request.session = {}

    def test_add_item_to_session_cart(self):
        cart = SessionCart(self.request)
        cart.add(1)
        self.assertIn('1', self.request.session[SessionCart.SESSION_KEY])
        self.assertEqual(self.request.session[SessionCart.SESSION_KEY]['1'], 1)

    def test_add_multiple_quantities(self):
        cart = SessionCart(self.request)
        cart.add(1, quantity=2)
        cart.add(1, quantity=3)
        self.assertEqual(self.request.session[SessionCart.SESSION_KEY]['1'], 5)

    def test_remove_item_from_session_cart(self):
        cart = SessionCart(self.request)
        cart.add(1)
        cart.remove(1)
        self.assertNotIn('1', self.request.session[SessionCart.SESSION_KEY])

    def test_update_quantity(self):
        cart = SessionCart(self.request)
        cart.add(1)
        cart.update(1, 10)
        self.assertEqual(self.request.session[SessionCart.SESSION_KEY]['1'], 10)

    def test_update_to_zero_removes_item(self):
        cart = SessionCart(self.request)
        cart.add(1)
        cart.update(1, 0)
        self.assertNotIn('1', self.request.session[SessionCart.SESSION_KEY])

    def test_items_returns_correct_data(self):
        cart = SessionCart(self.request)
        cart.add(1)
        cart.add(2, 3)
        items = dict(cart.items())
        self.assertEqual(items['1'], 1)
        self.assertEqual(items['2'], 3)

    def test_clear_cart(self):
        cart = SessionCart(self.request)
        cart.add(1)
        cart.clear()
        self.assertEqual(self.request.session[SessionCart.SESSION_KEY], {})
