from django.contrib import admin

from electry_art.products.models import Product, ProductType, ProductPhoto


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    pass


@admin.register(ProductPhoto)
class ProductPhotoAdmin(admin.ModelAdmin):
    pass

