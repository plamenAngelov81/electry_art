from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0010_checkout_attempt_idempotency")]

    operations = [
        migrations.AddField(
            model_name="order", name="checkout_processing_claim",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="order", name="checkout_processing_started_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
