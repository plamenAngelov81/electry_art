from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0009_order_stripe_expected_amount_and_more")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_attempt_key",
            field=models.CharField(max_length=64, unique=True, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="order",
            name="checkout_cart_fingerprint",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="order",
            name="stripe_checkout_url",
            field=models.URLField(max_length=2048, blank=True, default=""),
        ),
    ]
