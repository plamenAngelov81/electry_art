from django.contrib import admin

from electry_art.orders.models import Order, OrderItem


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order_serial_number',
        'full_name',
        'user',
        'is_paid',
        'is_sent',
        'created_at',
        'total_price',
    )

    search_fields = (
        'order_serial_number',
        'full_name',
        'user__username',
        'user_email',
    )

    list_filter = (
        'is_paid',
        'is_sent',
        'is_accepted',
        'created_at',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
        'paid_at',
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'product_name',
        'quantity',
        'price',
        'total_price',
        'status',
        'cancelled_at',
        'cancelled_by',
    )

    search_fields = (
        'order__order_serial_number',
        'order__full_name',
        'product_name',
    )

    list_filter = (
        'status',
        'cancelled_at',
    )

    readonly_fields = (
        'cancelled_at',
        'cancelled_by',
    )