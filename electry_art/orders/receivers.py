from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import logging
from electry_art.cart.signals import checkout_completed



logger = logging.getLogger("electryart.orders")
audit_logger = logging.getLogger("electryart.audit")


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "unknown"
    name, domain = email.split("@", 1)
    if len(name) <= 1:
        return f"*@{domain}"
    return f"{name[0]}***@{domain}"


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
    is_registered_user = order.user is not None
    subject = f"ElectryArt - Потвърждение на поръчка {order.order_serial_number}"

    message = f"""\
    Здравейте, {order.full_name},

    Вашата поръчка беше успешно приета!

    Сериен номер: {order.order_serial_number}
    Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}
    Обща сума: {order.total_price} лв.
    """

    if is_registered_user:
        message += f"""

    [ Виж поръчката ]
    {order_url}

    Ако линкът не се отваря, копирайте адреса и го поставете в браузъра:
    {order_url}
    """

    # For guest user
    message += """
    Благодарим ви, че избрахте ElectryArt!
    """
    


    # send_mail(
    #     subject=subject,
    #     message=message,
    #     from_email=settings.DEFAULT_FROM_EMAIL,
    #     recipient_list=[order.user_email],
    #     fail_silently=False
    # )

    email_mask = _mask_email(order.user_email)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user_email],
            fail_silently=False
        )

        logger.info(
            f"Order confirmation email sent. order_id={order.pk} serial={order.order_serial_number} email={email_mask}"
        )
        audit_logger.info(
            f"ORDER_CONFIRMATION_EMAIL_SENT order_id={order.pk} serial={order.order_serial_number} email={email_mask}"
        )

    except Exception as exc:  # noqa: BLE001 intentional logging boundary
        logger.exception(
            f"Order confirmation email failed. order_id={order.pk} serial={order.order_serial_number} email={email_mask}"
        )
        audit_logger.info(
            f"ORDER_CONFIRMATION_EMAIL_FAILED order_id={order.pk} serial={order.order_serial_number} email={email_mask}"
        )