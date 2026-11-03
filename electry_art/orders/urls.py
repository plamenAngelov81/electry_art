from django.urls import path
from .views import (
    CheckoutView,
    OrderHistoryView,
    OrderDetailView,
    GuestCheckoutView,
    PreviousMonthOrdersListView,
    Last7DaysOrdersListView,
    OrdersEditView,

    # Stripe views
    StripePaymentSuccessView,
    StripePaymentCancelView,
    OrderSerialSearchView, CancelOrderItemView,
)

urlpatterns = [
    # checkout
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('guest-checkout/', GuestCheckoutView.as_view(), name='guest_checkout'),

    # order pages
    path('history/', OrderHistoryView.as_view(), name='order_history'),
    path('details/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('edit/<int:pk>/', OrdersEditView.as_view(), name='order edit'),
    path("order-item/<int:pk>/cancel/", CancelOrderItemView.as_view(), name="cancel_order_item",
),

    # order lists
    path('new-orders/', Last7DaysOrdersListView.as_view(), name='new order'),
    path('previous-month-orders/', PreviousMonthOrdersListView.as_view(), name='previous-month-orders'),

    # STRIPE
    path('stripe/success/', StripePaymentSuccessView.as_view(), name='stripe_payment_success'),
    path('stripe/cancel/<int:order_id>/', StripePaymentCancelView.as_view(), name='stripe_payment_cancel'),

    # search orders by serial number
    path('search/', OrderSerialSearchView.as_view(), name='order_serial_search'),
]