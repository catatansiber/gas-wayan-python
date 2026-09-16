from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from imports import publisher
from operations.exceptions import DomainError

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Review otomatis + publish StagingRow per kelompok (satu kelompok = satu tabung). "
        "Hanya kelompok yang seluruh barisnya review_status=READY dan tanpa konflik kronologi "
        "yang dipublish - lainnya tetap PENDING_REVIEW. Lihat docs/reports/F4.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--actor-username", required=True, help="Username ADMIN/OPERATOR yang menjalankan."
        )
        parser.add_argument(
            "--limit-serial",
            action="append",
            default=None,
            help="Batasi ke satu/lebih serial_number_raw tertentu (bisa diulang). Default: semua.",
        )

    def handle(self, *args, **options):
        try:
            actor = User.objects.get(username=options["actor_username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{options['actor_username']}' tidak ditemukan.") from exc

        try:
            batch = publisher.run_publish(actor, limit_serials=options["limit_serial"])
        except DomainError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Publish batch selesai [{batch.status}]"))
        self.stdout.write(f"  Batch id                : {batch.id}")
        self.stdout.write(f"  Kelompok dilihat         : {batch.groups_seen}")
        self.stdout.write(f"  Kelompok sudah selesai   : {batch.groups_already_resolved}")
        self.stdout.write(f"  Kelompok dipublish       : {batch.groups_published}")
        self.stdout.write(f"  Kelompok diblokir        : {batch.groups_blocked}")
        self.stdout.write(f"  Baris dipublish          : {batch.rows_published}")
        if batch.error_message:
            msg = f"  Error (bisa di-resume): {batch.error_message}"
            self.stdout.write(self.style.WARNING(msg))
