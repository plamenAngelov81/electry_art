from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from electry_art.user_profiles.models import UserProfile, Address


@admin.register(UserProfile)
class UserProfileAdmin(UserAdmin):
    list_display = (
        'id',
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_active',
    )

    list_filter = (
        'is_staff',
        'is_active',
        'is_superuser',
    )

    search_fields = (
        'username',
        'email',
        'first_name',
        'last_name',
    )

    ordering = (
        'id',
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'country',
        'town',
        'address',
        'courier_company',
        'courier_office',
        'phone_num',
        'is_default',
        'created_at',
    )

    list_filter = (
        'country',
        'town',
        'courier_company',
        'is_default',
    )

    search_fields = (
        'user__username',
        'user__email',
        'country',
        'town',
        'address',
        'phone_num',
        'courier_company',
        'courier_office',
    )

    ordering = (
        '-is_default',
        '-created_at',
    )

    readonly_fields = (
        'created_at',
    )