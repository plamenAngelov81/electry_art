from django.urls import path
from electry_art.cart.views import UnifiedCartView, AddToCartView, RemoveFromCartView, UpdateCartItemView

urlpatterns = [
    path('', UnifiedCartView.as_view(), name='cart_view'),
    path('add/<int:pk>/', AddToCartView.as_view(), name='add_to_cart'),
    path('remove/<int:pk>/', RemoveFromCartView.as_view(), name='remove_from_cart'),
    path('update/<int:pk>/', UpdateCartItemView.as_view(), name='update_cart_item'),
]

