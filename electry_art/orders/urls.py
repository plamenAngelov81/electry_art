from django.urls import path
from .views import (CheckoutView, OrderSuccessView, OrderHistoryView, OrderDetailView, GuestCheckoutView,
                    PreviousMonthOrdersListView, Last7DaysOrdersListView, OrdersEditView)

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('success/<int:order_id>/', OrderSuccessView.as_view(), name='order_success'),
    path('history/', OrderHistoryView.as_view(), name='order_history'),
    path('details/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('edit/<int:pk>', OrdersEditView.as_view(), name='order edit'),
    path('guest-checkout/', GuestCheckoutView.as_view(), name='guest_checkout'),
    path('new-orders/', Last7DaysOrdersListView.as_view(), name='new order'),
    path('previous-month-orders/', PreviousMonthOrdersListView.as_view(), name='previous-month-orders'),


]