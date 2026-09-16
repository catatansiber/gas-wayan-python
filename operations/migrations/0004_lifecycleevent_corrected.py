# Generated manually for audit-safe cycle corrections.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_alter_cycle_data_quality_flag_and_more")]

    operations = [
        migrations.AlterField(
            model_name="lifecycleevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("DISPATCHED", "Dispatched"), ("RETURNED", "Returned"),
                    ("EXCHANGED_OUT", "Exchanged out"), ("EXCHANGED_IN", "Exchanged in"),
                    ("LOST", "Lost"), ("MAINTENANCE_STARTED", "Maintenance started"),
                    ("MAINTENANCE_COMPLETED", "Maintenance completed"), ("RETIRED", "Retired"),
                    ("REVERSED", "Reversed"), ("CORRECTED", "Corrected"),
                ],
                max_length=30,
            ),
        ),
    ]
