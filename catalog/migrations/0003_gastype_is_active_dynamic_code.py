# Generated manually for Admin-managed gas master data.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_customeralias_normalized_value")]

    operations = [
        migrations.AlterField(
            model_name="gastype",
            name="code",
            field=models.CharField(max_length=10, primary_key=True, serialize=False),
        ),
        migrations.AddField(
            model_name="gastype",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
