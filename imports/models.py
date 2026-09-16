import uuid

from django.conf import settings
from django.db import models

from operations.models import Cycle


class ImportBatch(models.Model):
    """Satu kali eksekusi importer terhadap satu snapshot workbook. Tidak menulis
    master/lifecycle - hanya RawRow/StagingRow (lihat docs/phase-plan.md F3)."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Sedang berjalan"
        COMPLETED = "COMPLETED", "Selesai"
        FAILED = "FAILED", "Gagal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workbook_filename = models.CharField(max_length=255)
    workbook_sha256 = models.CharField(max_length=64, db_index=True)
    sheet_name = models.CharField(max_length=100)
    parser_version = models.CharField(max_length=50)
    dry_run = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    raw_rows_seen = models.PositiveIntegerField(default=0)
    raw_rows_created = models.PositiveIntegerField(default=0)
    raw_rows_already_existing = models.PositiveIntegerField(default=0)
    blank_rows_seen = models.PositiveIntegerField(default=0)
    staging_rows_created = models.PositiveIntegerField(default=0)
    staging_rows_already_existing = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"ImportBatch {self.id} ({self.status})"


class RawRow(models.Model):
    """Arsip mentah, immutable, satu baris fisik sheet Database = satu RawRow (termasuk
    baris kosong). Tidak pernah diupdate setelah dibuat - re-run snapshot yang sama hanya
    membaca ulang, tidak menimpa (lihat docs/migration-policy.md A1)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workbook_sha256 = models.CharField(max_length=64, db_index=True)
    sheet_name = models.CharField(max_length=100)
    source_row_number = models.PositiveIntegerField()
    is_blank = models.BooleanField(default=False)
    raw_json = models.JSONField(help_text="Enam nilai asli + tipe sel, apa adanya dari workbook.")
    first_seen_batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, related_name="raw_rows_first_seen"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workbook_sha256", "sheet_name", "source_row_number"],
                name="uniq_raw_row_per_snapshot_position",
            )
        ]
        indexes = [models.Index(fields=["workbook_sha256", "is_blank"])]

    def __str__(self):
        return f"RawRow baris {self.source_row_number} ({self.workbook_sha256[:8]})"


class StagingRow(models.Model):
    """Hasil parse terkontrol satu RawRow non-kosong. Belum master/lifecycle - hanya
    kandidat yang menunggu review (F4). Immutable per parser_version: re-run dengan
    parser_version sama tidak menulis ulang (idempotent)."""

    class ReturnStatus(models.TextChoices):
        NONE = "NONE", "Kosong"
        DATE = "DATE", "Tanggal"
        K = "K", "K"
        KEMBALI = "KEMBALI", "KEMBALI"
        SDH_KEMBALI = "SDH_KEMBALI", "SDH KEMBALI"
        SDH_BALIK = "SDH_BALIK", "SDH BALIK (belum dipetakan - MIG-B05)"
        OTHER_TEXT = "OTHER_TEXT", "Teks lain tidak dikenal"

    class ReviewStatus(models.TextChoices):
        READY = "READY", "Siap direview"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Perlu review"
        ERROR = "ERROR", "Error - tidak bisa membentuk lifecycle"

    class PublishOutcome(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Menunggu review/publish"
        PUBLISHED = "PUBLISHED", "Sudah dipublish"
        EXCLUDED_APPROVED = "EXCLUDED_APPROVED", "Dikecualikan Admin (beralasan)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_row = models.OneToOneField(RawRow, on_delete=models.PROTECT, related_name="staging_row")
    parser_version = models.CharField(max_length=50)

    legacy_nomor_raw = models.CharField(max_length=255, blank=True)

    serial_number_raw = models.CharField(max_length=255, blank=True)
    serial_number_present = models.BooleanField(default=False)

    customer_name_raw = models.CharField(max_length=255, blank=True)
    customer_name_normalized = models.CharField(max_length=255, blank=True, db_index=True)

    sent_at_raw = models.CharField(max_length=255, blank=True)
    sent_at = models.DateField(null=True, blank=True)
    sent_at_is_native = models.BooleanField(default=False)
    sent_at_parseable = models.BooleanField(default=False)

    returned_at_raw = models.CharField(max_length=255, blank=True)
    returned_at = models.DateField(null=True, blank=True)
    returned_at_is_native = models.BooleanField(default=False)
    returned_status = models.CharField(
        max_length=20, choices=ReturnStatus.choices, default=ReturnStatus.NONE
    )
    returned_date_unknown = models.BooleanField(
        default=False,
        help_text="True bila status kembali dikenal (K/KEMBALI/SDH KEMBALI) tapi tanpa "
        "tanggal terparse - occurred_at tidak pernah diisi tanggal impor (MIG-B04).",
    )

    gas_code_raw = models.CharField(max_length=255, blank=True)
    gas_type_code = models.CharField(max_length=10, blank=True)
    gas_type_known = models.BooleanField(default=False)

    dedupe_key = models.CharField(
        max_length=512,
        blank=True,
        db_index=True,
        help_text="Kunci kandidat duplikat bisnis (mengabaikan kolom Nomor) - lihat B3.",
    )

    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.READY
    )
    publish_outcome = models.CharField(
        max_length=20,
        choices=PublishOutcome.choices,
        default=PublishOutcome.PENDING_REVIEW,
        db_index=True,
        help_text="F4: hasil review/publish. Rekonsiliasi wajib raw(non-blank) = "
        "PUBLISHED + PENDING_REVIEW + EXCLUDED_APPROVED - lihat docs/reports/F4.md.",
    )

    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, related_name="staging_rows_created_in"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["review_status"]),
            models.Index(fields=["serial_number_raw"]),
        ]

    def __str__(self):
        return f"StagingRow untuk RawRow {self.raw_row_id} ({self.review_status})"


class PublishBatch(models.Model):
    """Satu kali eksekusi `publish_staging`. Memproses per kelompok (satu kelompok = satu
    `serial_number_raw`) - masing-masing kelompok dalam transaksi atomic sendiri, supaya crash
    di tengah jalan hanya membatalkan kelompok yang sedang diproses, bukan seluruh batch, dan
    re-run berikutnya bisa melanjutkan (resume) tanpa menduplikasi kelompok yang sudah selesai."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Sedang berjalan"
        COMPLETED = "COMPLETED", "Selesai"
        FAILED = "FAILED", "Berhenti karena error (bisa di-resume)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    groups_seen = models.PositiveIntegerField(default=0)
    groups_already_resolved = models.PositiveIntegerField(default=0)
    groups_published = models.PositiveIntegerField(default=0)
    groups_blocked = models.PositiveIntegerField(default=0)
    rows_published = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"PublishBatch {self.id} ({self.status})"


class SourceLink(models.Model):
    """Jejak wajib raw -> hasil publish (docs/migration-policy.md A1). Satu StagingRow F4 ini
    selalu menghasilkan tepat satu Cycle (dispatch+return lengkap - lihat imports/publisher.py),
    jadi OneToOne cukup; event individual tetap bisa ditelusuri lewat `cycle.events`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staging_row = models.OneToOneField(
        StagingRow, on_delete=models.PROTECT, related_name="source_link"
    )
    raw_row = models.ForeignKey(RawRow, on_delete=models.PROTECT, related_name="source_links")
    cycle = models.ForeignKey(Cycle, on_delete=models.PROTECT, related_name="source_links")
    publish_batch = models.ForeignKey(
        PublishBatch, on_delete=models.PROTECT, related_name="source_links"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SourceLink baris {self.raw_row.source_row_number} -> Cycle {self.cycle_id}"


class ReviewDecision(models.Model):
    """Keputusan Admin beralasan atas satu StagingRow - append-only (siapa, kapan, alasan),
    lihat docs/column-mapping.md. F4 hanya mendukung EXCLUDE (mengecualikan baris dari publish
    dengan alasan) - keputusan yang butuh kebijakan bisnis PENDING (mis. menebak gas/tanggal)
    TIDAK bisa dilakukan lewat sini, hanya lewat konfirmasi kebijakan resmi (lihat CLAUDE.md)."""

    class Decision(models.TextChoices):
        EXCLUDE = "EXCLUDE", "Kecualikan dari publish"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staging_row = models.ForeignKey(
        StagingRow, on_delete=models.PROTECT, related_name="review_decisions"
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.decision} StagingRow {self.staging_row_id} oleh {self.actor_id}"
