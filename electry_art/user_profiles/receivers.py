from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from electry_art.user_profiles.signals import user_registered


@receiver(user_registered)
def send_welcome_email(sender, user=None, **kwargs):
    """
    Send a welcome email when a user successfully registers.
    Expects `user` to be passed with the signal.
    """
    if user is None:
        return

    if not user.email:
        return

    protocol = getattr(settings, "SITE_PROTOCOL", "http")
    domain = getattr(settings, "SITE_DOMAIN", "127.0.0.1:8000")

    site_url = f"{protocol}://{domain}"

    subject = "Добре дошли в ElectryArt 🎉"

    message = f"""\
Здравейте, {user.first_name or user.username},

Добре дошли в ElectryArt!

Вашият акаунт беше създаден успешно и вече сте логнати в системата.

Можете да разгледате продуктите и да направите поръчка тук:
{site_url}

Ако имате въпроси, просто отговорете на този имейл или пишете на нашия екип за поддръжка.

Приятно пазаруване!
Екипът на ElectryArt
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False
    )
