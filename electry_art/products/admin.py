from django.contrib import admin

from electry_art.products.models import Product, ProductType, ProductPhoto


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "serial_number",
        "name",
        "type",
        "price",
        "is_available",
        "date_created",
    )
    list_filter = (
        "is_available",
        "type",
        "material",
        "color",
    )
    search_fields = (
        "serial_number",
        "name",
        "name_en",
        "name_bg",
    )


@admin.register(ProductPhoto)
class ProductPhotoAdmin(admin.ModelAdmin):
    pass

