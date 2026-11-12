from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from electry_art.cart.models import Cart, CartItem
from electry_art.cart.utils import SessionCart
from electry_art.products.models import Product
from django.contrib import messages
from django.db.models import F


class UnifiedCartView(View):
    template_name = 'cart/cart.html'

    def get(self, request, *args, **kwargs):
        # Logged user
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            db_items = cart.items.select_related('product')

            items = []
            cart_total = 0
            has_unavailable = False
            for ci in db_items:
                if ci.product is None:
                    # A physically deleted product leaves a nullable cart reference.
                    # Only remove the broken cart row, never an unavailable product.
                    ci.delete()
                    messages.warning(request, "A deleted product was removed from your cart.")
                    continue
                available = ci.product.is_available
                if not available:
                    has_unavailable = True
                row_total = ci.product.price * ci.quantity if available else 0
                items.append({
                    'product': ci.product,
                    'quantity': ci.quantity,
                    'total': row_total,
                    'available': available,
                })
                cart_total += row_total

            context = {
                'items': items,
                'cart_total': cart_total,
                'checkout_url_name': 'checkout',
                'is_guest': False,
                'has_unavailable': has_unavailable,
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
        has_unavailable = False
        for pid, qty in raw_items:
            try:
                pid_int = int(pid)
                qty_int = int(qty)
            except (TypeError, ValueError):
                continue

            product = products.get(pid_int)
            if not product:
                session_cart.remove(pid)
                messages.warning(request, "A deleted product was removed from your cart.")
                continue

            available = product.is_available
            if not available:
                has_unavailable = True
            row_total = product.price * qty_int if available else 0
            items.append({
                'product': product,
                'quantity': qty_int,
                'total': row_total,
                'available': available,
            })
            cart_total += row_total

        context = {
            'items': items,
            'cart_total': cart_total,
            'checkout_url_name': 'guest_checkout',
            'is_guest': True,
            'has_unavailable': has_unavailable,
        }
        return render(request, self.template_name, context)


class AddToCartView(View):
    @staticmethod
    def post(request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)

        if not product.is_available:
            messages.error(request, f"Product '{product.name}' is currently not available.")
            return redirect(request.META.get("HTTP_REFERER", "product list"))

        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
            )

            if not created:
                # Increment in PostgreSQL, avoiding lost updates from concurrent adds.
                # The unique (cart, product) constraint and get_or_create()
                # handle competing attempts to create the first row.
                CartItem.objects.filter(pk=cart_item.pk).update(
                    quantity=F("quantity") + 1
                )
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
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1

        if quantity < 0:
            quantity = 0

        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            item = get_object_or_404(CartItem, cart=cart, product_id=pk)

            if quantity == 0:
                item.delete()
                return redirect("cart_view")

            product = item.product

            if not product or not product.is_available:
                messages.error(request, "This product cannot be updated while unavailable.")
                return redirect("cart_view")

            item.quantity = quantity
            item.save(update_fields=["quantity"])

        else:
            if quantity == 0:
                SessionCart(request).update(pk, 0)
                return redirect("cart_view")

            product = get_object_or_404(Product, pk=pk)

            if not product.is_available:
                messages.error(request, "This product cannot be updated while unavailable.")
                return redirect("cart_view")

            SessionCart(request).update(pk, quantity)

        return redirect("cart_view")
