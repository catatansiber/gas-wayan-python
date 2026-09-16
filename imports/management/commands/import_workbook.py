from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from imports import importer
from imports.exceptions import ChecksumMismatch, SheetNotFound


class Command(BaseCommand):
    help = (
        "Import sheet Database dari SERI TABUNG.xlsm ke arsip raw immutable + staging. "
        "Tidak pernah menulis catalog/operations (master/lifecycle) - lihat docs/phase-plan.md F3."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--workbook",
            default=str(Path(settings.BASE_DIR).parent / "SERI TABUNG.xlsm"),
            help="Path ke workbook .xlsm (default: ../SERI TABUNG.xlsm dari root proyek).",
        )
        parser.add_argument(
            "--expected-sha256",
            default=importer.EXPECTED_WORKBOOK_SHA256,
            help="Checksum SHA-256 yang diharapkan (default: checksum terverifikasi F0).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Hitung dan tampilkan laporan tanpa menyimpan RawRow/StagingRow (rollback).",
        )

    def handle(self, *args, **options):
        workbook_path = Path(options["workbook"])
        if not workbook_path.exists():
            raise CommandError(f"Workbook tidak ditemukan: {workbook_path}")

        try:
            batch = importer.run_import(
                workbook_path=workbook_path,
                expected_sha256=options["expected_sha256"],
                dry_run=options["dry_run"],
            )
        except ChecksumMismatch as exc:
            raise CommandError(str(exc)) from exc
        except SheetNotFound as exc:
            raise CommandError(str(exc)) from exc

        dry_run = options["dry_run"]
        mode = "DRY-RUN (tidak disimpan)" if dry_run else "TERSIMPAN"
        batch_id = "(rollback)" if dry_run else batch.id
        self.stdout.write(self.style.SUCCESS(f"Import selesai [{mode}]"))
        self.stdout.write(f"  Batch id            : {batch_id}")
        self.stdout.write(f"  Checksum            : {batch.workbook_sha256}")
        self.stdout.write(f"  Parser version      : {batch.parser_version}")
        self.stdout.write(f"  Baris fisik dibaca  : {batch.raw_rows_seen}")
        self.stdout.write(f"  Baris kosong        : {batch.blank_rows_seen}")
        self.stdout.write(f"  RawRow baru         : {batch.raw_rows_created}")
        self.stdout.write(f"  RawRow sudah ada    : {batch.raw_rows_already_existing}")
        self.stdout.write(f"  StagingRow baru     : {batch.staging_rows_created}")
        self.stdout.write(f"  StagingRow sudah ada: {batch.staging_rows_already_existing}")

        if not dry_run:
            self.stdout.write(
                "\nJalankan 'python manage.py import_report' untuk laporan per kategori."
            )
