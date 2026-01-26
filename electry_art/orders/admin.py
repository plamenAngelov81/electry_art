from django.contrib import admin

from electry_art.orders.models import Order, OrderItem


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'user', 'created_at', 'total_price')
    search_fields = ('full_name', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price', 'total_price')
    search_fields = ('order__full_name', 'product__name')
