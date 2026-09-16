"""SQL manual (ADR-P004): constraint kompleks yang tidak dapat dinyatakan lewat Django model API
biasa. Menjaga invariant: siklus OPEN tidak boleh punya returned_at/close_reason terisi; siklus
CLOSED selalu punya close_reason. Constraint database, bukan hanya validasi Python di services.py -
supaya baris yang lolos lewat jalur lain (mis. skrip migrasi F3/F4 nanti) tetap ditolak DB bila
melanggar invariant ini."""

from django.db import migrations

CHECK_SQL = """
ALTER TABLE operations_cycle
ADD CONSTRAINT cycle_status_consistency_check
CHECK (
    (status = 'OPEN' AND returned_at IS NULL AND close_reason = '')
    OR
    (status = 'CLOSED' AND close_reason <> '')
);
"""

DROP_SQL = "ALTER TABLE operations_cycle DROP CONSTRAINT cycle_status_consistency_check;"


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CHECK_SQL, reverse_sql=DROP_SQL),
    ]
