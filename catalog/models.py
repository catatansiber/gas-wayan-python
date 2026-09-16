import uuid

from django.db import models


class Customer(models.Model):
    """Relasi/pelanggan. Nama tampilan boleh berubah; alias legacy disimpan di CustomerAlias.
    Merge dua Customer TIDAK dilakukan di sini secara otomatis - itu tindakan Admin eksplisit
    dengan audit (FR-03), belum diimplementasikan di F2."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name


class CustomerAlias(models.Model):
    """Nilai nama mentah/legacy yang merujuk ke Customer yang sama - dipakai agar pencarian nama
    lama tetap berfungsi (FR-03). Diisi manual/F4, belum otomatis di F2."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, related_name="aliases", on_delete=models.PROTECT)
    raw_value = models.CharField(max_length=255)
    normalized_value = models.CharField(
        max_length=255,
        db_index=True,
        blank=True,
        help_text="Trim+uppercase+collapse spasi dari raw_value - dipakai F4 untuk kandidat "
        "match exact-normalized (FR-03). Diisi oleh pemanggil, bukan otomatis di save().",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "raw_value"], name="uniq_customer_alias_raw"
            )
        ]

    def __str__(self):
        return self.raw_value


class GasType(models.Model):
    """Master jenis gas yang dikelola Admin.

    Kode disimpan sebagai primary key agar tetap ringkas di riwayat siklus.  Jenis gas lama
    tidak dihapus karena dapat dirujuk oleh histori; Admin cukup menonaktifkannya dari pilihan
    pengiriman baru.
    """

    class Code(models.TextChoices):
        O2 = "O2", "O2"
        AR = "AR", "AR"
        C2H2 = "C2H2", "C2H2"
        N2 = "N2", "N2"
        CO2 = "CO2", "CO2"

    code = models.CharField(max_length=10, primary_key=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Cylinder(models.Model):
    """Master tabung. `status` adalah ringkasan state saat ini - sumber kebenaran urutan
    kejadian tetap `operations.LifecycleEvent` (append-only). Jangan mengubah `status` di luar
    `operations.services` - lihat CLAUDE.md."""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        OUT = "OUT", "Out"
        LOST = "LOST", "Lost"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        RETIRED = "RETIRED", "Retired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serial_number = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["serial_number"]

    def __str__(self):
        return self.serial_number

    @property
    def latest_cycle(self):
        """Cycle paling baru (berdasarkan `created_at`) untuk tabung ini, atau None. Dipakai
        layar F5 untuk menampilkan `data_quality_flag` terpisah dari `Cylinder.status` -
        TIDAK menyimpan apa pun, hanya query read-only."""
        return self.cycles.order_by("-created_at").first()
