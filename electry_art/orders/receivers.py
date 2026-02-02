from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

from electry_art.cart.signals import checkout_completed


@receiver(checkout_completed)
def send_order_confirmation_on_checkout(sender, order=None, user=None, **kwargs):
    """
    Send order confirmation email AFTER successful checkout (after cart is cleared).
    Expects `order` to be passed when the signal is sent.
    """
    if order is None:
        return

    if not order.user_email:
        return

    order_path = reverse("order_detail", kwargs={"pk": order.pk})
    order_url = f"{settings.SITE_PROTOCOL}://{settings.SITE_DOMAIN}{order_path}"

    subject = f"ElectryArt - Потвърждение на поръчка {order.order_serial_number}"

    message = f"""\
Здравейте, {order.full_name},

Вашата поръчка беше успешно приета!

Сериен номер: {order.order_serial_number}
Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}
Обща сума: {order.total_price} лв.

[ Виж поръчката ]
{order_url}

Ако линкът не се отваря, копирайте адреса и го поставете в браузъра:
{order_url}

Благодарим ви, че избрахте ElectryArt!
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user_email],
        fail_silently=False
    )
