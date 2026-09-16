from django.contrib import admin, messages
from django.shortcuts import render

from operations.admin import ReadOnlyAdminMixin
from operations.exceptions import DomainError

from . import publisher
from .models import ImportBatch, PublishBatch, RawRow, ReviewDecision, SourceLink, StagingRow


@admin.register(ImportBatch)
class ImportBatchAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "workbook_filename",
        "status",
        "dry_run",
        "raw_rows_created",
        "staging_rows_created",
        "started_at",
    )
    list_filter = ("status", "dry_run")


@admin.register(RawRow)
class RawRowAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Arsip raw tetap dapat dicari lewat Django Admin kapan pun, sebelum maupun sesudah
    publish - lihat search_fields (nomor baris sumber dan checksum snapshot)."""

    list_display = ("source_row_number", "workbook_sha256", "is_blank", "created_at")
    list_filter = ("is_blank",)
    search_fields = ("source_row_number", "workbook_sha256")


@admin.action(description="Kecualikan dari publish (wajib alasan) - keputusan Admin beralasan")
def exclude_with_reason(modeladmin, request, queryset):
    if "apply" in request.POST:
        reason = request.POST.get("reason", "").strip()
        if not reason:
            modeladmin.message_user(
                request, "Alasan wajib diisi - tidak ada baris yang dikecualikan.", messages.ERROR
            )
            return None
        excluded, failed = 0, 0
        for row in queryset:
            try:
                publisher.exclude_staging_row(request.user, row, reason)
                excluded += 1
            except DomainError as exc:
                failed += 1
                modeladmin.message_user(request, f"Baris {row.raw_row_id}: {exc}", messages.ERROR)
        modeladmin.message_user(
            request, f"{excluded} baris dikecualikan (alasan tercatat), {failed} gagal."
        )
        return None

    return render(
        request,
        "imports/admin_exclude_confirm.html",
        {
            "staging_rows": queryset,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
            "opts": StagingRow._meta,
        },
    )


@admin.register(StagingRow)
class StagingRowAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Layar review F4. Preview mapping (pelanggan/tabung/gas) dihitung on-the-fly lewat
    `publisher.preview_mapping` - TIDAK menulis apa pun, aman dibuka berulang kali. Satu-satunya
    aksi yang tersedia adalah `exclude_with_reason` (keputusan Admin beralasan); publish
    sesungguhnya HANYA lewat command `publish_staging` (per kelompok, atomic, resumable) supaya
    tidak ada jalur pintas yang melewati pengecekan kelompok/rollback."""

    list_display = (
        "raw_row",
        "serial_number_raw",
        "review_status",
        "publish_outcome",
        "returned_status",
        "gas_type_known",
    )
    list_filter = ("review_status", "publish_outcome", "returned_status", "gas_type_known")
    search_fields = ("serial_number_raw", "customer_name_raw", "raw_row__source_row_number")
    actions = [exclude_with_reason]
    readonly_fields = (
        "raw_row",
        "parser_version",
        "legacy_nomor_raw",
        "serial_number_raw",
        "serial_number_present",
        "customer_name_raw",
        "customer_name_normalized",
        "sent_at_raw",
        "sent_at",
        "sent_at_is_native",
        "sent_at_parseable",
        "returned_at_raw",
        "returned_at",
        "returned_at_is_native",
        "returned_status",
        "returned_date_unknown",
        "gas_code_raw",
        "gas_type_code",
        "gas_type_known",
        "dedupe_key",
        "warnings",
        "errors",
        "review_status",
        "publish_outcome",
        "import_batch",
        "created_at",
        "preview_mapping_display",
    )
    fieldsets = (
        (
            "Preview mapping (dihitung saat ini, belum ditulis)",
            {"fields": ("preview_mapping_display",)},
        ),
        (None, {"fields": readonly_fields[:-1]}),
    )

    @admin.display(description="Preview mapping pelanggan/tabung/gas")
    def preview_mapping_display(self, obj):
        if obj.pk is None:
            return "-"
        preview = publisher.preview_mapping(obj)
        if preview["customer_match"]:
            customer_text = f"cocok -> {preview['customer_match']}"
        else:
            customer_text = "BARU akan dibuat"
        if preview["cylinder_exists"]:
            cylinder_text = f"sudah ada, status {preview['cylinder_current_status']}"
        else:
            cylinder_text = "BARU akan dibuat"
        gas_text = preview["gas_type_code"] or "kosong/tidak dikenal"
        eligible_text = "YA" if preview["eligible_for_publish"] else "TIDAK"
        return (
            f"Pelanggan: {customer_text} | Tabung: {cylinder_text} | Gas: {gas_text} | "
            f"Layak publish sekarang: {eligible_text}"
        )


@admin.register(PublishBatch)
class PublishBatchAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "groups_seen",
        "groups_published",
        "groups_blocked",
        "groups_already_resolved",
        "rows_published",
        "started_at",
        "finished_at",
    )
    list_filter = ("status",)


@admin.register(SourceLink)
class SourceLinkAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("raw_row", "staging_row", "cycle", "publish_batch", "created_at")
    search_fields = ("raw_row__source_row_number",)


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only di admin CRUD biasa - satu-satunya cara MEMBUAT ReviewDecision adalah aksi
    `exclude_with_reason` di atas (lewat `publisher.exclude_staging_row`), supaya reason wajib
    dan role ADMIN selalu ditegakkan di server, bukan cuma form admin."""

    list_display = ("staging_row", "decision", "actor", "created_at")
    list_filter = ("decision",)
    search_fields = ("reason",)
