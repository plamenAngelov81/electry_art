
class SessionCart:
    SESSION_KEY = 'cart'

    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.get(self.SESSION_KEY, {})  # {str(product_id): int(qty)}

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


