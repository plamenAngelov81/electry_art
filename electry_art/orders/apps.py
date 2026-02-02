from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'electry_art.orders'

    def ready(self):
        import electry_art.orders.receivers
