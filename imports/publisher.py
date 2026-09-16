"""Orkestrasi F4: review + publish per kelompok (satu kelompok = satu `serial_number_raw`).

Aturan wajib:
- Kebijakan migrasi yang masih PENDING (B1 gas, B2 tanggal kembali tanpa tanggal, B3 konflik
  siklus) TIDAK PERNAH ditebak di sini - hanya StagingRow ber-`review_status=READY` (gas
  dikenal, tanggal kirim+kembali sama-sama terparse) yang bisa dipublish. Baris/kelompok lain
  tetap `PENDING_REVIEW` sampai kebijakan dikonfirmasi (lihat docs/migration-decisions-pending.md).
- Satu kelompok = SATU transaksi atomic: publish semua baris di kelompok itu, atau tidak sama
  sekali (docs/phase-plan.md F4: "penerbitan per kelompok tervalidasi"). Kelompok lain yang
  independen tidak terpengaruh bila satu kelompok gagal/di-rollback.
- Re-run aman: baris yang sudah `PUBLISHED`/`EXCLUDED_APPROVED` tidak diproses ulang - crash di
  tengah `run_publish` hanya membatalkan kelompok yang sedang berjalan (resume otomatis di
  panggilan berikutnya, lihat `PublishBatch`).
- Satu-satunya jalan mutasi Cycle/Cylinder tetap `operations.services` (audit/idempotency/outbox
  konsisten dengan F2) - modul ini tidak pernah memanggil `.save()` langsung pada Cycle/Cylinder.
"""

from django.db import transaction
from django.utils import timezone

from catalog.models import Customer, CustomerAlias, Cylinder
from imports.models import PublishBatch, ReviewDecision, SourceLink, StagingRow
from operations import services
from operations.exceptions import DomainError

PublishOutcome = StagingRow.PublishOutcome


class GroupConflict(Exception):
    """Ditemukan tumpang tindih kronologi (termasuk duplikat bisnis) di satu kelompok - lihat
    docs/migration-policy.md B3. Seluruh kelompok tetap PENDING_REVIEW, tidak ada yang dipublish."""


def _resolve_customer(actor, raw_name: str, normalized_name: str) -> Customer:
    """Match exact-normalized ke alias yang sudah ada (FR-03); bila tidak ada, buat Customer +
    alias baru. Ejaan mirip (bukan exact) TIDAK di-merge di sini - tetap Customer terpisah,
    kandidat merge manual tetap tanggung jawab Admin di luar scope F4 otomatis ini."""
    alias = (
        CustomerAlias.objects.filter(normalized_value=normalized_name)
        .select_related("customer")
        .first()
    )
    if alias is not None:
        return alias.customer

    customer = Customer.objects.create(display_name=raw_name)
    CustomerAlias.objects.create(
        customer=customer, raw_value=raw_name, normalized_value=normalized_name
    )
    return customer


def _resolve_cylinder(serial_number: str) -> Cylinder:
    cylinder, _ = Cylinder.objects.get_or_create(serial_number=serial_number)
    return cylinder


def _distinct_serials(limit_serials=None):
    # Sengaja TIDAK memfilter publish_outcome di sini - kelompok yang sudah selesai (semua baris
    # PUBLISHED/EXCLUDED_APPROVED) tetap ikut dilihat supaya `_process_group` bisa melaporkan
    # 'already_resolved' secara eksplisit (dipakai laporan resume, lihat PublishBatch).
    qs = (
        StagingRow.objects.order_by("serial_number_raw")
        .values_list("serial_number_raw", flat=True)
        .distinct()
    )
    if limit_serials is not None:
        qs = qs.filter(serial_number_raw__in=limit_serials)
    return list(qs)


def _group_rows(serial_number: str):
    return list(
        StagingRow.objects.select_for_update()
        .filter(serial_number_raw=serial_number)
        .exclude(publish_outcome=PublishOutcome.EXCLUDED_APPROVED)
        .order_by("sent_at", "raw_row__source_row_number")
        .select_related("raw_row")
    )


def _check_no_overlap(rows_in_order):
    previous = None
    for row in rows_in_order:
        if previous is not None and row.sent_at < previous.returned_at:
            raise GroupConflict(
                f"Tumpang tindih kronologi tabung {row.serial_number_raw}: baris sumber "
                f"{row.raw_row.source_row_number} (kirim {row.sent_at}) sebelum baris "
                f"{previous.raw_row.source_row_number} kembali ({previous.returned_at})."
            )
        previous = row


def _publish_row(actor, batch, row: StagingRow):
    customer = _resolve_customer(actor, row.customer_name_raw, row.customer_name_normalized)
    _resolve_cylinder(row.serial_number_raw)

    cycle = services.dispatch_cylinder(
        actor=actor,
        serial_number=row.serial_number_raw,
        customer_id=customer.id,
        gas_type_code=row.gas_type_code,
        sent_at=row.sent_at,
        idempotency_key=f"f4-dispatch-{row.id}",
        source="IMPORT",
    )
    cycle = services.return_cylinder(
        actor=actor,
        serial_number=row.serial_number_raw,
        returned_at=row.returned_at,
        idempotency_key=f"f4-return-{row.id}",
        source="IMPORT",
    )

    SourceLink.objects.create(
        staging_row=row, raw_row=row.raw_row, cycle=cycle, publish_batch=batch
    )
    row.publish_outcome = PublishOutcome.PUBLISHED
    row.save(update_fields=["publish_outcome"])


def _process_group(actor, batch: PublishBatch, serial_number: str) -> str:
    """Mengembalikan salah satu: 'already_resolved', 'blocked', 'published'."""
    with transaction.atomic():
        rows = _group_rows(serial_number)
        to_evaluate = [r for r in rows if r.publish_outcome == PublishOutcome.PENDING_REVIEW]
        if not to_evaluate:
            return "already_resolved"

        if any(r.review_status != StagingRow.ReviewStatus.READY for r in to_evaluate):
            return "blocked"

        try:
            _check_no_overlap(rows)
        except GroupConflict:
            return "blocked"

        for row in to_evaluate:
            _publish_row(actor, batch, row)
            batch.rows_published += 1

        return "published"


def run_publish(actor, limit_serials=None, _fail_after_groups=None) -> PublishBatch:
    """`_fail_after_groups`: parameter internal, HANYA untuk tes crash/resume - melempar error
    tepat setelah N kelompok selesai diproses, mensimulasikan proses mati di tengah jalan tanpa
    merusak kelompok yang sudah commit (masing-masing kelompok = transaksi terpisah)."""
    if getattr(actor, "role", None) not in services.OPERATOR_AND_ADMIN:
        raise DomainError("Hanya ADMIN/OPERATOR yang boleh menjalankan publish staging.")

    batch = PublishBatch.objects.create(actor=actor)
    serials = _distinct_serials(limit_serials)

    try:
        for i, serial in enumerate(serials):
            outcome = _process_group(actor, batch, serial)
            batch.groups_seen += 1
            if outcome == "already_resolved":
                batch.groups_already_resolved += 1
            elif outcome == "blocked":
                batch.groups_blocked += 1
            elif outcome == "published":
                batch.groups_published += 1

            if _fail_after_groups is not None and (i + 1) == _fail_after_groups:
                raise RuntimeError(
                    f"Simulasi crash setelah {_fail_after_groups} kelompok (hanya untuk tes)."
                )
        batch.status = PublishBatch.Status.COMPLETED
    except Exception as exc:
        batch.status = PublishBatch.Status.FAILED
        batch.error_message = str(exc)
        batch.finished_at = timezone.now()
        batch.save()
        raise

    batch.finished_at = timezone.now()
    batch.save()
    return batch


def exclude_staging_row(actor, staging_row: StagingRow, reason: str) -> ReviewDecision:
    """Keputusan Admin beralasan: kecualikan satu baris staging dari publish (bukan menebak
    kebijakan PENDING, hanya menandai baris ini tidak dipakai). Wajib alasan (FR-08/FR-11)."""
    if getattr(actor, "role", None) not in services.ADMIN_ONLY:
        raise DomainError("Hanya ADMIN yang boleh mengecualikan baris staging.")
    if not reason or not reason.strip():
        raise DomainError("Alasan wajib diisi untuk mengecualikan baris staging.")
    if staging_row.publish_outcome == PublishOutcome.PUBLISHED:
        raise DomainError("Baris ini sudah dipublish - tidak bisa dikecualikan retroaktif.")

    with transaction.atomic():
        decision = ReviewDecision.objects.create(
            staging_row=staging_row,
            decision=ReviewDecision.Decision.EXCLUDE,
            reason=reason.strip(),
            actor=actor,
        )
        staging_row.publish_outcome = PublishOutcome.EXCLUDED_APPROVED
        staging_row.save(update_fields=["publish_outcome"])
    return decision


def preview_mapping(staging_row: StagingRow) -> dict:
    """Pratinjau hasil mapping TANPA menulis apa pun - dipakai layar review Admin. Jangan
    dipanggil dari jalur publish (publish selalu lewat _resolve_customer/_resolve_cylinder)."""
    normalized = staging_row.customer_name_normalized
    alias = (
        CustomerAlias.objects.filter(normalized_value=normalized).select_related("customer").first()
    )
    existing_cylinder = Cylinder.objects.filter(serial_number=staging_row.serial_number_raw).first()
    return {
        "customer_match": alias.customer.display_name if alias else None,
        "customer_will_be_created": alias is None,
        "cylinder_exists": existing_cylinder is not None,
        "cylinder_current_status": existing_cylinder.status if existing_cylinder else None,
        "gas_type_code": staging_row.gas_type_code or None,
        "eligible_for_publish": staging_row.review_status == StagingRow.ReviewStatus.READY,
    }
