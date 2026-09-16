"""Reset transaksi lama lalu impor relasi dan transaksi dari ekspor Google Sheets.

Master Cylinder dipertahankan. Perintah ini secara sengaja menghapus Cycle, LifecycleEvent,
IdempotencyRecord, CustomerAlias, dan Customer sebelum membangun ulang snapshot transaksi.
"""

from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from catalog.models import Customer, CustomerAlias, Cylinder, GasType
from imports.models import SourceLink
from operations.models import Cycle, IdempotencyRecord, LifecycleEvent

GAS_CODES = {
    "ARGON": "AR",
    "ASETILIN": "C2H2",
    "CO2": "CO2",
    "NITROGEN": "N2",
    "OKSIGEN": "O2",
}


def clean_text(value):
    return " ".join(str(value or "").strip().split())


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError(f"Tanggal tidak valid: {value!r}")


class Command(BaseCommand):
    help = "Reset relasi/transaksi dan impor data dari sheet Distribusi Tabung Gas."

    def add_arguments(self, parser):
        parser.add_argument("workbook", type=Path)

    def handle(self, *args, **options):
        workbook_path = options["workbook"]
        if not workbook_path.is_file():
            raise CommandError(f"File tidak ditemukan: {workbook_path}")

        book = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            relation_sheet = book["Database Relasi"]
            transaction_sheet = book["Transaksi"]
        except KeyError as exc:
            raise CommandError("Sheet 'Database Relasi' dan 'Transaksi' wajib tersedia.") from exc

        relations = {}
        for name, phone, *_ in relation_sheet.iter_rows(min_row=5, values_only=True):
            name = clean_text(name)
            if name:
                relations.setdefault(name.casefold(), (name, clean_text(phone)))

        rows = []
        skipped_duplicates = 0
        skipped_invalid = 0
        for row_number, row in enumerate(
            transaction_sheet.iter_rows(min_row=5, max_col=9, values_only=True), start=5
        ):
            serial, name, phone, sent_at, returned_at, gas_name, status, _, validation = row
            serial, name, status, validation = (
                clean_text(serial),
                clean_text(name),
                clean_text(status).upper(),
                clean_text(validation).upper(),
            )
            if not any(row):
                continue
            if validation == "DUPLIKAT AKTIF":
                skipped_duplicates += 1
                continue
            if validation != "OK" or not serial or not name or not sent_at:
                skipped_invalid += 1
                continue
            try:
                sent_at = as_date(sent_at)
                returned_at = as_date(returned_at) if returned_at else None
            except ValueError:
                skipped_invalid += 1
                continue
            if status not in {"DIKIRIM", "KEMBALI"} or (status == "KEMBALI" and not returned_at):
                skipped_invalid += 1
                continue
            relations.setdefault(name.casefold(), (name, clean_text(phone)))
            rows.append(
                (
                    serial,
                    name.casefold(),
                    sent_at,
                    returned_at,
                    clean_text(gas_name),
                    status,
                    row_number,
                )
            )

        rows.sort(key=lambda item: (item[0], item[2], item[6]))
        with transaction.atomic():
            # Hapus dependensi sebelum master pelanggan. Tabung tidak dihapus.
            LifecycleEvent.objects.all().delete()
            IdempotencyRecord.objects.all().delete()
            SourceLink.objects.all().delete()
            Cycle.objects.all().delete()
            CustomerAlias.objects.all().delete()
            Customer.objects.all().delete()
            Cylinder.objects.update(status=Cylinder.Status.AVAILABLE)

            customers = {}
            for key, (name, phone) in relations.items():
                customers[key] = Customer.objects.create(display_name=name, phone_number=phone)

            for code in sorted(set(GAS_CODES.values())):
                GasType.objects.update_or_create(code=code, defaults={"is_active": True})

            active_serials = set()
            imported = 0
            skipped_conflicts = 0
            for serial, customer_key, sent_at, returned_at, gas_name, status, _ in rows:
                if status == "DIKIRIM" and serial in active_serials:
                    skipped_conflicts += 1
                    continue
                cylinder, _ = Cylinder.objects.get_or_create(serial_number=serial)
                gas_code = GAS_CODES.get(gas_name.upper())
                gas_type = GasType.objects.filter(code=gas_code).first() if gas_code else None
                closed = status == "KEMBALI"
                cycle = Cycle.objects.create(
                    cylinder=cylinder,
                    customer=customers[customer_key],
                    gas_type_at_dispatch=gas_type,
                    status=Cycle.Status.CLOSED if closed else Cycle.Status.OPEN,
                    sent_at=sent_at,
                    returned_at=returned_at if closed else None,
                    close_reason=Cycle.CloseReason.RETURNED if closed else "",
                    data_quality_flag="" if gas_type else "NEEDS_REVIEW",
                )
                LifecycleEvent.objects.create(
                    cylinder=cylinder,
                    cycle=cycle,
                    event_type=LifecycleEvent.EventType.DISPATCHED,
                    occurred_at=sent_at,
                    source=LifecycleEvent.Source.IMPORT,
                )
                if closed:
                    LifecycleEvent.objects.create(
                        cylinder=cylinder,
                        cycle=cycle,
                        event_type=LifecycleEvent.EventType.RETURNED,
                        occurred_at=returned_at,
                        source=LifecycleEvent.Source.IMPORT,
                    )
                else:
                    active_serials.add(serial)
                    Cylinder.objects.filter(pk=cylinder.pk).update(status=Cylinder.Status.OUT)
                imported += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Impor selesai: {len(customers)} relasi, {imported} transaksi, "
                f"{skipped_duplicates} duplikat aktif dilewati, "
                f"{skipped_invalid + skipped_conflicts} baris tidak diimpor."
            )
        )
