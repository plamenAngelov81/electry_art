from electry_art.cart.models import Cart
from electry_art.cart.utils import SessionCart


def cart_badge(request):
    """
    Adds `cart_count` to every template context.
    - logged user: count from DB cart items quantities
    - guest: count from session cart quantities
    """
    if getattr(request, "user", None) and request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if not cart:
            return {"cart_count": 0}

        # Sum quantities (not number of rows)
        total_qty = sum(item.quantity for item in cart.items.all())
        return {"cart_count": total_qty}

    session_cart = SessionCart(request)
    return {"cart_count": len(session_cart)}