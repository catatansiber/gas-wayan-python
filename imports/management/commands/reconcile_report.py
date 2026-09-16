import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count

from imports.models import RawRow, SourceLink, StagingRow
from operations.models import LifecycleEvent

SUMMARY_PATH = Path(settings.BASE_DIR) / "docs" / "reports" / "f4-publish-summary.json"


class Command(BaseCommand):
    help = (
        "Rekonsiliasi F4: raw (non-blank) = PUBLISHED + PENDING_REVIEW + EXCLUDED_APPROVED, "
        "dilaporkan terpisah dari pengecekan event yatim (IMPORT event tanpa SourceLink). "
        "Menulis docs/reports/f4-publish-summary.json (agregat, aman untuk Git)."
    )

    def handle(self, *args, **options):
        staging_total = StagingRow.objects.count()
        by_outcome = dict(
            StagingRow.objects.values_list("publish_outcome")
            .annotate(n=Count("id"))
            .values_list("publish_outcome", "n")
        )
        published = by_outcome.get(StagingRow.PublishOutcome.PUBLISHED, 0)
        pending = by_outcome.get(StagingRow.PublishOutcome.PENDING_REVIEW, 0)
        excluded = by_outcome.get(StagingRow.PublishOutcome.EXCLUDED_APPROVED, 0)
        reconciled_sum = published + pending + excluded
        reconciliation_ok = reconciled_sum == staging_total

        raw_total = RawRow.objects.count()
        blank_total = RawRow.objects.filter(is_blank=True).count()

        import_events = LifecycleEvent.objects.filter(source=LifecycleEvent.Source.IMPORT)
        linked_cycle_ids = set(SourceLink.objects.values_list("cycle_id", flat=True).distinct())
        orphan_events = [
            {
                "event_id": str(e.id),
                "event_type": e.event_type,
                "cylinder": e.cylinder.serial_number,
                "cycle_id": str(e.cycle_id) if e.cycle_id else None,
            }
            for e in import_events.select_related("cylinder")
            if e.cycle_id is None or e.cycle_id not in linked_cycle_ids
        ]

        summary = {
            "raw_rows_total": raw_total,
            "blank_rows_total": blank_total,
            "staging_rows_total": staging_total,
            "staging_by_publish_outcome": {
                "PUBLISHED": published,
                "PENDING_REVIEW": pending,
                "EXCLUDED_APPROVED": excluded,
            },
            "reconciliation_sum": reconciled_sum,
            "reconciliation_ok": reconciliation_ok,
            "source_links_total": SourceLink.objects.count(),
            "import_lifecycle_events_total": import_events.count(),
            "orphan_import_events_count": len(orphan_events),
            "orphan_import_events": orphan_events,
        }

        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        style = self.style.SUCCESS if reconciliation_ok else self.style.ERROR
        self.stdout.write(style(f"Rekonsiliasi: {reconciled_sum} == raw staging {staging_total}"))
        self.stdout.write(f"  PUBLISHED         : {published}")
        self.stdout.write(f"  PENDING_REVIEW    : {pending}")
        self.stdout.write(f"  EXCLUDED_APPROVED : {excluded}")
        if orphan_events:
            self.stdout.write(
                self.style.ERROR(f"  Event IMPORT yatim (tanpa SourceLink): {len(orphan_events)}")
            )
        else:
            self.stdout.write("  Event IMPORT yatim: 0 (semua event IMPORT tertelusuri)")
        self.stdout.write(f"Ringkasan -> {SUMMARY_PATH}")
