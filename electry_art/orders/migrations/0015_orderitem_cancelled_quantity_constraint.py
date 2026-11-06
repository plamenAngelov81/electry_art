from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0014_alter_orderitem_product_name"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=Q(cancelled_quantity__lte=F("quantity")),
                name="orderitem_cancelled_quantity_lte_quantity",
            ),
        ),
    ]
