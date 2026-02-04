from django.apps import AppConfig


class UserProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'electry_art.user_profiles'

    def ready(self):
        import electry_art.user_profiles.receivers