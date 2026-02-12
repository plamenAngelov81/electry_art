
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import logging

from electry_art.cart.signals import checkout_completed
from electry_art.core.audit import audit_event, Actor, mask_email

log = logging.getLogger("electryart.orders")


@receiver(checkout_completed)
def send_order_confirmation_on_checkout(sender, order=None, user=None, request_id=None, **kwargs):
    """
    Send order confirmation email AFTER successful checkout (after cart is cleared).
    Expects `order` to be passed when the signal is sent.
    """
    if order is None:
        return

    if not order.user_email:
        return

    actor = Actor(type="user" if order.user_id else "guest", id=order.user_id)
    email_mask = mask_email(order.user_email)

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

    message += """
Благодарим ви, че избрахте ElectryArt!
"""

    # Attempt (audit + app)
    log.info(
        "ORDER_CONFIRMATION_EMAIL_ATTEMPT order_id=%s serial=%s request_id=%s email=%s",
        order.pk, order.order_serial_number, request_id, email_mask
    )
    audit_event(
        "ORDER_CONFIRMATION_EMAIL_ATTEMPT",
        actor=actor,
        request_id=request_id,
        order_id=order.pk,
        serial=order.order_serial_number,
        email_mask=email_mask,
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user_email],
            fail_silently=False
        )

        log.info(
            "ORDER_CONFIRMATION_EMAIL_SENT order_id=%s serial=%s request_id=%s email=%s",
            order.pk, order.order_serial_number, request_id, email_mask
        )
        audit_event(
            "ORDER_CONFIRMATION_EMAIL_SENT",
            actor=actor,
            request_id=request_id,
            order_id=order.pk,
            serial=order.order_serial_number,
            email_mask=email_mask,
        )

    except Exception:  # noqa: BLE001
        log.exception(
            "ORDER_CONFIRMATION_EMAIL_FAILED order_id=%s serial=%s request_id=%s email=%s",
            order.pk, order.order_serial_number, request_id, email_mask
        )
        audit_event(
            "ORDER_CONFIRMATION_EMAIL_FAILED",
            actor=actor,
            request_id=request_id,
            order_id=order.pk,
            serial=order.order_serial_number,
            email_mask=email_mask,
        )
