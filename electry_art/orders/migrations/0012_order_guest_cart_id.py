from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0011_checkout_processing_claim'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='guest_cart_id',
            field=models.CharField(max_length=64, blank=True, default='', db_index=True),
        ),
    ]
