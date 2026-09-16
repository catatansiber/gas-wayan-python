import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count

from imports.models import RawRow, StagingRow
from imports.parsing import sanitize_csv_cell

SUMMARY_PATH = Path(settings.BASE_DIR) / "docs" / "reports" / "f3-import-summary.json"
LOCAL_DIR = Path(settings.BASE_DIR) / "docs" / "reports" / "f3-local"


class Command(BaseCommand):
    help = (
        "Buat laporan F3 dari RawRow/StagingRow yang sudah diimpor: ringkasan agregat "
        "(aman, tanpa data mentah, tersimpan di docs/reports/f3-import-summary.json) dan "
        "laporan detail (data asli, tetap lokal, TIDAK masuk Git - docs/reports/f3-local/)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--workbook-sha256", default=None, help="Filter satu snapshot saja.")

    def handle(self, *args, **options):
        raw_qs = RawRow.objects.all()
        staging_qs = StagingRow.objects.all()
        sha = options["workbook_sha256"]
        if sha:
            raw_qs = raw_qs.filter(workbook_sha256=sha)
            staging_qs = staging_qs.filter(raw_row__workbook_sha256=sha)

        summary = self._build_summary(raw_qs, staging_qs)
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Ringkasan agregat -> {SUMMARY_PATH}"))

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        problem_count = self._write_problem_rows(staging_qs)
        dup_groups = self._write_duplicate_candidates(staging_qs)
        alias_groups = self._write_alias_candidates(staging_qs)
        self.stdout.write(
            self.style.WARNING(
                f"Laporan detail (data asli, LOKAL SAJA) -> {LOCAL_DIR}\n"
                f"  problem_rows.csv         : {problem_count} baris\n"
                f"  duplicate_candidates.csv : {dup_groups} kelompok\n"
                f"  alias_candidates.csv     : {alias_groups} kelompok"
            )
        )

    def _build_summary(self, raw_qs, staging_qs):
        raw_total = raw_qs.count()
        blank_total = raw_qs.filter(is_blank=True).count()
        staging_total = staging_qs.count()

        by_review = dict(
            staging_qs.values_list("review_status")
            .annotate(n=Count("id"))
            .values_list("review_status", "n")
        )
        by_return_status = dict(
            staging_qs.values_list("returned_status")
            .annotate(n=Count("id"))
            .values_list("returned_status", "n")
        )
        gas_known = staging_qs.filter(gas_type_known=True).count()
        gas_unknown_nonempty = (
            staging_qs.filter(gas_type_known=False).exclude(gas_code_raw="").count()
        )
        gas_empty = staging_qs.filter(gas_code_raw="").count()

        sent_native = staging_qs.filter(sent_at_is_native=True).count()
        sent_text_parsed = staging_qs.filter(
            sent_at_is_native=False, sent_at_parseable=True
        ).count()
        sent_unparseable = staging_qs.filter(
            sent_at_is_native=False, sent_at_parseable=False, sent_at_raw__gt=""
        ).count()

        dup_group_count, dup_extra_rows = self._duplicate_stats(staging_qs)
        alias_group_count, alias_variant_rows = self._alias_stats(staging_qs)

        last_rows = list(
            raw_qs.order_by("-source_row_number").values("source_row_number", "is_blank")[:3]
        )

        return {
            "raw_rows_total": raw_total,
            "blank_rows_total": blank_total,
            "staging_rows_total": staging_total,
            "staging_by_review_status": by_review,
            "staging_by_returned_status": by_return_status,
            "gas_type_known": gas_known,
            "gas_type_unknown_nonempty": gas_unknown_nonempty,
            "gas_type_empty": gas_empty,
            "sent_at_native": sent_native,
            "sent_at_text_parsed": sent_text_parsed,
            "sent_at_unparseable": sent_unparseable,
            "duplicate_candidate_groups": dup_group_count,
            "duplicate_candidate_extra_rows": dup_extra_rows,
            "alias_candidate_groups": alias_group_count,
            "alias_candidate_variant_rows": alias_variant_rows,
            "last_source_rows": last_rows,
        }

    def _duplicate_stats(self, staging_qs):
        counts = (
            staging_qs.exclude(dedupe_key="")
            .values("dedupe_key")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        groups = list(counts)
        extra = sum(g["n"] - 1 for g in groups)
        return len(groups), extra

    def _alias_stats(self, staging_qs):
        rows = staging_qs.exclude(customer_name_normalized="").values(
            "customer_name_normalized", "customer_name_raw"
        )
        variants_by_group = defaultdict(set)
        for row in rows:
            variants_by_group[row["customer_name_normalized"]].add(row["customer_name_raw"])
        groups_with_variants = {k: v for k, v in variants_by_group.items() if len(v) > 1}
        variant_rows = sum(len(v) for v in groups_with_variants.values())
        return len(groups_with_variants), variant_rows

    def _write_problem_rows(self, staging_qs):
        rows = staging_qs.exclude(review_status=StagingRow.ReviewStatus.READY).select_related(
            "raw_row"
        )
        path = LOCAL_DIR / "problem_rows.csv"
        count = 0
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "source_row_number",
                    "review_status",
                    "warnings",
                    "errors",
                    "serial_number_raw",
                    "customer_name_raw",
                    "sent_at_raw",
                    "returned_at_raw",
                    "gas_code_raw",
                ]
            )
            for row in rows.iterator():
                writer.writerow(
                    [
                        row.raw_row.source_row_number,
                        row.review_status,
                        ";".join(row.warnings),
                        ";".join(row.errors),
                        sanitize_csv_cell(row.serial_number_raw),
                        sanitize_csv_cell(row.customer_name_raw),
                        sanitize_csv_cell(row.sent_at_raw),
                        sanitize_csv_cell(row.returned_at_raw),
                        sanitize_csv_cell(row.gas_code_raw),
                    ]
                )
                count += 1
        return count

    def _write_duplicate_candidates(self, staging_qs):
        groups = (
            staging_qs.exclude(dedupe_key="")
            .values("dedupe_key")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("-n")
        )
        path = LOCAL_DIR / "duplicate_candidates.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["dedupe_key", "jumlah_baris", "source_row_numbers"])
            group_count = 0
            for group in groups:
                rows = staging_qs.filter(dedupe_key=group["dedupe_key"]).select_related("raw_row")
                row_numbers = sorted(r.raw_row.source_row_number for r in rows)
                writer.writerow(
                    [
                        sanitize_csv_cell(group["dedupe_key"]),
                        group["n"],
                        ";".join(str(n) for n in row_numbers),
                    ]
                )
                group_count += 1
        return group_count

    def _write_alias_candidates(self, staging_qs):
        rows = staging_qs.exclude(customer_name_normalized="").select_related("raw_row")
        by_group = defaultdict(list)
        for row in rows.iterator():
            by_group[row.customer_name_normalized].append(row)

        path = LOCAL_DIR / "alias_candidates.csv"
        group_count = 0
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["customer_name_normalized", "raw_variants", "source_row_numbers"])
            for normalized, group_rows in by_group.items():
                variant_counter = Counter(r.customer_name_raw for r in group_rows)
                if len(variant_counter) <= 1:
                    continue
                row_numbers = sorted(r.raw_row.source_row_number for r in group_rows)
                variants = "|".join(f"{v}({c})" for v, c in variant_counter.items())
                writer.writerow(
                    [
                        sanitize_csv_cell(normalized),
                        sanitize_csv_cell(variants),
                        ";".join(str(n) for n in row_numbers),
                    ]
                )
                group_count += 1
        return group_count
