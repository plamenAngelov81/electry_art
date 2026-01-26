from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from electry_art.cart.models import Cart, CartItem
from electry_art.cart.utils import SessionCart
from electry_art.products.models import Product


class UnifiedCartView(View):
    template_name = 'cart/cart.html'

    def get(self, request, *args, **kwargs):
        # Logged user
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            db_items = cart.items.select_related('product')

            items = []
            cart_total = 0
            for ci in db_items:
                row_total = ci.product.price * ci.quantity
                items.append({
                    'product': ci.product,
                    'quantity': ci.quantity,
                    'total': row_total,
                })
                cart_total += row_total

            context = {
                'items': items,
                'cart_total': cart_total,
                'checkout_url_name': 'checkout',
                'is_guest': False,
            }
            return render(request, self.template_name, context)

        # Guest user
        session_cart = SessionCart(request)
        raw_items = list(session_cart.items())

        product_ids = []
        for pid, _ in raw_items:
            try:
                product_ids.append(int(pid))
            except (TypeError, ValueError):
                continue

        products = Product.objects.in_bulk(product_ids)

        items = []
        cart_total = 0
        for pid, qty in raw_items:
            try:
                pid_int = int(pid)
                qty_int = int(qty)
            except (TypeError, ValueError):
                continue

            product = products.get(pid_int)
            if not product:
                continue

            row_total = product.price * qty_int
            items.append({
                'product': product,
                'quantity': qty_int,
                'total': row_total,
            })
            cart_total += row_total

        context = {
            'items': items,
            'cart_total': cart_total,
            'checkout_url_name': 'guest_checkout',
            'is_guest': True,
        }
        return render(request, self.template_name, context)


class AddToCartView(View):
    @staticmethod
    def post(request, pk, *args, **kwargs):
        if request.user.is_authenticated:
            product = get_object_or_404(Product, pk=pk)
            cart, _ = Cart.objects.get_or_create(user=request.user)

            cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
            if not created:
                cart_item.quantity += 1
                cart_item.save()
        else:
            SessionCart(request).add(pk)

        return redirect(request.META.get("HTTP_REFERER", "product list"))


class RemoveFromCartView(View):
    """
    pk = product_id (works for both logged + guest)
    """
    @staticmethod
    def post(request, pk, *args, **kwargs):
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            CartItem.objects.filter(cart=cart, product_id=pk).delete()
        else:
            SessionCart(request).remove(pk)

        return redirect('cart_view')


class UpdateCartItemView(View):
    """
    pk = product_id (works for both logged + guest)
    """
    @staticmethod
    def post(request, pk, *args, **kwargs):
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            quantity = 1

        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            item = get_object_or_404(CartItem, cart=cart, product_id=pk)

            if quantity > 0:
                item.quantity = quantity
                item.save()
            else:
                item.delete()
        else:
            SessionCart(request).update(pk, quantity)

        return redirect('cart_view')
