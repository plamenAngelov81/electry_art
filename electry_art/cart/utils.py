import secrets

from django.apps import apps


class SessionCart:
    SESSION_KEY = 'cart'
    GUEST_ID_KEY = 'electryart_guest_cart_id'
    RECONCILED_KEY = 'paid_guest_cart_adjusted_orders'

    def __init__(self, request):
        self.session = request.session
        self.cart = dict(self.session.get(self.SESSION_KEY, {}))  # {str(product_id): int(qty)}
        self.guest_cart_id = self.session.get(self.GUEST_ID_KEY)
        if not self.guest_cart_id:
            self.guest_cart_id = secrets.token_hex(24)
            self.session[self.GUEST_ID_KEY] = self.guest_cart_id
        self._reconcile_paid_orders()

    def _reconcile_paid_orders(self):
        """Apply paid guest purchases even if Stripe never redirects the browser.

        The webhook marks the order paid in PostgreSQL. The next cart access
        reconciles the current session, without requiring the success page.
        """
        Order = apps.get_model('orders', 'Order')
        already = set(map(str, self.session.get(self.RECONCILED_KEY, [])))
        orders = (Order.objects.filter(
            guest_cart_id=self.guest_cart_id, user__isnull=True, is_paid=True,
        ).exclude(pk__in=[int(pk) for pk in already if pk.isdecimal()])
                  .order_by('pk').prefetch_related('items'))
        applied = []
        for order in orders:
            purchased = {}
            for item in order.items.all():
                if item.product_id is None:
                    continue
                key = str(item.product_id)
                purchased[key] = purchased.get(key, 0) + item.quantity
            for product_id, quantity in purchased.items():
                remaining = int(self.cart.get(product_id, 0)) - quantity
                if remaining > 0:
                    self.cart[product_id] = remaining
                else:
                    self.cart.pop(product_id, None)
            applied.append(str(order.pk))
        if applied:
            self.session[self.SESSION_KEY] = self.cart
            self.session[self.RECONCILED_KEY] = list(already) + applied
            self.session.modified = True

    def _save(self):
        self.session[self.SESSION_KEY] = self.cart
        self.session.modified = True

    def add(self, product_id, quantity=1):
        product_id = str(product_id)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1

        if quantity == 0:
            return

        current = int(self.cart.get(product_id, 0))
        new_qty = current + quantity

        if new_qty > 0:
            self.cart[product_id] = new_qty
        else:
            self.cart.pop(product_id, None)

        self._save()

    def remove(self, product_id):
        product_id = str(product_id)
        if product_id in self.cart:
            self.cart.pop(product_id, None)
            self._save()

    def update(self, product_id, quantity):
        product_id = str(product_id)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1

        if quantity > 0:
            self.cart[product_id] = quantity
        else:
            self.cart.pop(product_id, None)

        self._save()

    def items(self):
        return self.cart.items()

    def clear(self):
        self.cart = {}
        self._save()

    def __len__(self):
        return sum(int(qty) for qty in self.cart.values())


