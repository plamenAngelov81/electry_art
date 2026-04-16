from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'electry_art.products'

    def ready(self):
        import electry_art.products.translation