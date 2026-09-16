from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_gastype_is_active_dynamic_code")]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="phone_number",
            field=models.CharField(blank=True, default="", max_length=32),
        )
    ]
