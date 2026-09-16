"""Layar operasional F5. Django Templates server-rendered (ADR-P010) - setiap mutasi di sini
memanggil `operations.services` (satu-satunya jalur, sama seperti yang akan dipakai bot
Telegram di F6). View TIDAK PERNAH memanggil `.save()` langsung pada Cycle/Cylinder."""

import datetime
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from catalog.models import Cylinder
from identity.models import Role
from identity.permissions import role_required

from . import forms as op_forms
from . import services
from .exceptions import DomainError
from .models import Cycle

OPERATOR_AND_ADMIN = (Role.ADMIN, Role.OPERATOR)
ADMIN_ONLY = (Role.ADMIN,)


# --------------------------------------------------------------------------------------
# Pencarian dan riwayat (semua role bisa baca)
# --------------------------------------------------------------------------------------


@login_required
def search_cylinders(request):
    form = op_forms.SearchForm(request.GET or None)
    results = Cylinder.objects.none()
    searched = False
    not_found_serial = False

    if request.GET and form.is_valid():
        serial = form.cleaned_data.get("serial_number", "").strip()
        customer_q = form.cleaned_data.get("customer", "").strip()
        if serial or customer_q:
            searched = True
            qs = Cylinder.objects.all().order_by("serial_number")
            if serial:
                qs = qs.filter(serial_number=serial)
            if customer_q:
                qs = qs.filter(cycles__customer__display_name__icontains=customer_q).distinct()
            results = qs
            if serial and not customer_q and not qs.exists():
                not_found_serial = True

    page_obj = Paginator(results, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "operations/search.html",
        {
            "form": form,
            "page_obj": page_obj,
            "searched": searched,
            "not_found_serial": not_found_serial,
        },
    )


@login_required
def cylinder_detail(request, serial_number):
    cylinder = get_object_or_404(Cylinder, serial_number=serial_number)
    active_cycle = (
        cylinder.cycles.filter(status=Cycle.Status.OPEN)
        .select_related("customer", "gas_type_at_dispatch")
        .first()
    )

    cycles_qs = cylinder.cycles.select_related("customer", "gas_type_at_dispatch").order_by(
        "-sent_at", "-created_at"
    )
    cycles_page = Paginator(cycles_qs, 10).get_page(request.GET.get("cycles_page"))

    events_qs = cylinder.lifecycle_events.select_related("actor").order_by("-created_at")
    events_page = Paginator(events_qs, 20).get_page(request.GET.get("events_page"))

    return render(
        request,
        "operations/cylinder_detail.html",
        {
            "cylinder": cylinder,
            "active_cycle": active_cycle,
            "cycles_page": cycles_page,
            "events_page": events_page,
        },
    )


@login_required
def usage_log(request):
    cycles = Cycle.objects.select_related("cylinder", "customer", "gas_type_at_dispatch").order_by(
        "-sent_at", "-created_at"
    )
    serial = request.GET.get("serial_number", "").strip()
    customer = request.GET.get("customer", "").strip()
    status = request.GET.get("status", "").strip()
    if serial:
        cycles = cycles.filter(cylinder__serial_number=serial)
    if customer:
        cycles = cycles.filter(customer__display_name__icontains=customer)
    if status == "DIKIRIM":
        cycles = cycles.filter(status=Cycle.Status.OPEN)
    elif status == "KEMBALI":
        cycles = cycles.filter(status=Cycle.Status.CLOSED, close_reason=Cycle.CloseReason.RETURNED)
    # Retensi tampilan: riwayat yang selesai kembali lebih dari satu tahun diarsipkan dari
    # daftar harian, tetapi tidak dihapus sehingga audit dan relasi FK tetap utuh.
    include_archive = request.GET.get("include_archive") == "1"
    if not include_archive:
        cutoff = datetime.date.today() - datetime.timedelta(days=365)
        cycles = cycles.exclude(
            status=Cycle.Status.CLOSED,
            close_reason=Cycle.CloseReason.RETURNED,
            returned_at__lt=cutoff,
        )
    page_obj = Paginator(cycles, 30).get_page(request.GET.get("page"))
    today = datetime.date.today()
    for cycle in page_obj:
        cycle.days_out = ((cycle.returned_at or today) - cycle.sent_at).days
    return render(
        request,
        "operations/usage_log.html",
        {
            "page_obj": page_obj,
            "serial_query": serial,
            "customer_query": customer,
            "status_query": status,
            "include_archive": include_archive,
        },
    )


# --------------------------------------------------------------------------------------
# Pola generik: form -> preview -> konfirmasi. Idempotency key dibuat SATU KALI saat preview
# dirender dan dikirim ulang sebagai hidden field - double-click tombol "Konfirmasi" mengirim
# key+payload identik, sehingga operations.services mengembalikan hasil yang sama tanpa
# menggandakan transaksi (lihat operations/services.py `_claim_idempotency`).
# --------------------------------------------------------------------------------------


@dataclass
class OperationSpec:
    form_class: type
    service_fn: Callable
    title: str
    build_service_kwargs: Callable[[dict], dict]
    build_preview_rows: Callable[[dict], list]
    success_redirect: Callable[[dict], str]


def _serialize_for_repost(form) -> dict[str, str]:
    data: dict[str, Any] = {}
    for name, field in form.fields.items():
        value = form.cleaned_data.get(name)
        if isinstance(field, forms.ModelChoiceField):
            data[name] = str(value.pk) if value is not None else ""
        elif isinstance(value, datetime.date):
            data[name] = value.isoformat()
        elif value is None:
            data[name] = ""
        else:
            data[name] = value
    return data


def _operation_view(request, spec: OperationSpec):
    if request.method == "POST" and request.POST.get("step") == "confirm":
        form = spec.form_class(request.POST)
        idempotency_key = request.POST.get("idempotency_key", "").strip()
        if form.is_valid() and idempotency_key:
            kwargs = spec.build_service_kwargs(form.cleaned_data)
            try:
                spec.service_fn(actor=request.user, idempotency_key=idempotency_key, **kwargs)
                messages.success(request, f"{spec.title} berhasil disimpan.")
                return redirect(spec.success_redirect(form.cleaned_data))
            except DomainError as exc:
                messages.error(request, str(exc))
                return render(
                    request, "operations/operation_form.html", {"form": form, "title": spec.title}
                )
        messages.error(request, "Form tidak valid atau sesi kedaluwarsa - silakan ulangi.")
        return render(
            request, "operations/operation_form.html", {"form": form, "title": spec.title}
        )

    if request.method == "POST":
        form = spec.form_class(request.POST)
        if form.is_valid():
            return render(
                request,
                "operations/operation_preview.html",
                {
                    "title": spec.title,
                    "preview_rows": spec.build_preview_rows(form.cleaned_data),
                    "hidden_fields": _serialize_for_repost(form),
                    "idempotency_key": str(uuid.uuid4()),
                },
            )
        return render(
            request, "operations/operation_form.html", {"form": form, "title": spec.title}
        )

    form = spec.form_class()
    return render(request, "operations/operation_form.html", {"form": form, "title": spec.title})


def _gas_label(code):
    return code or "-"


@role_required(*OPERATOR_AND_ADMIN)
def dispatch_view(request):
    spec = OperationSpec(
        form_class=op_forms.DispatchForm,
        service_fn=services.dispatch_cylinder,
        title="Kirim tabung",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "customer_id": d["customer"].id,
            "gas_type_code": d["gas_type_code"],
            "sent_at": d["sent_at"],
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Pelanggan", d["customer"].display_name),
            ("Jenis gas", _gas_label(d["gas_type_code"])),
            ("Tanggal kirim", d["sent_at"].strftime("%d/%m/%Y")),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*OPERATOR_AND_ADMIN)
def return_view(request):
    spec = OperationSpec(
        form_class=op_forms.ReturnForm,
        service_fn=services.return_cylinder,
        title="Kembalikan tabung",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "returned_at": d["returned_at"],
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Tanggal kembali", d["returned_at"].strftime("%d/%m/%Y")),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def exchange_view(request):
    spec = OperationSpec(
        form_class=op_forms.ExchangeForm,
        service_fn=services.exchange_cylinder,
        title="Tukar tabung",
        build_service_kwargs=lambda d: {
            "old_serial_number": d["old_serial_number"].strip(),
            "new_serial_number": d["new_serial_number"].strip(),
            "customer_id": d["customer"].id,
            "exchanged_at": d["exchanged_at"],
        },
        build_preview_rows=lambda d: [
            ("Tabung lama", d["old_serial_number"].strip()),
            ("Tabung pengganti", d["new_serial_number"].strip()),
            ("Pelanggan/relasi", d["customer"].display_name),
            ("Tanggal tukar", d["exchanged_at"].strftime("%d/%m/%Y")),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["new_serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def lost_view(request):
    serial = request.POST.get("serial_number") or request.GET.get("serial_number", "")
    initial = {}
    if serial:
        cycle = (
            Cycle.objects.filter(cylinder__serial_number=serial.strip(), status=Cycle.Status.OPEN)
            .select_related("customer")
            .first()
        )
        if cycle:
            initial["last_customer"] = cycle.customer.display_name
    spec = OperationSpec(
        form_class=op_forms.LostForm,
        service_fn=services.mark_lost,
        title="Laporkan tabung hilang",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "occurred_at": d["occurred_at"],
            "reason": d["reason"].strip(),
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Tanggal kejadian", d["occurred_at"].strftime("%d/%m/%Y")),
            ("Alasan", d["reason"].strip()),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    if request.method == "GET":
        return render(
            request,
            "operations/operation_form.html",
            {"form": op_forms.LostForm(initial=initial), "title": spec.title},
        )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def correct_cycle_view(request, cycle_id):
    cycle = get_object_or_404(
        Cycle.objects.select_related("cylinder", "customer", "gas_type_at_dispatch"), pk=cycle_id
    )
    if request.method == "POST":
        form = op_forms.CycleCorrectionForm(request.POST)
        if form.is_valid():
            try:
                idempotency_key = request.POST.get("idempotency_key", "").strip()
                if not idempotency_key:
                    raise DomainError("Sesi koreksi kedaluwarsa. Silakan buka ulang formulir.")
                services.correct_cycle(
                    actor=request.user,
                    cycle_id=cycle.id,
                    customer_id=form.cleaned_data["customer"].id,
                    gas_type_code=form.cleaned_data["gas_type_code"],
                    sent_at=form.cleaned_data["sent_at"],
                    returned_at=form.cleaned_data["returned_at"],
                    reason=form.cleaned_data["reason"].strip(),
                    idempotency_key=idempotency_key,
                )
                messages.success(request, "Riwayat siklus diperbarui dan dicatat sebagai koreksi.")
                return redirect(
                    "operations:cylinder-detail", serial_number=cycle.cylinder.serial_number
                )
            except DomainError as exc:
                form.add_error(None, str(exc))
    else:
        form = op_forms.CycleCorrectionForm(
            initial={
                "customer": cycle.customer_id,
                "gas_type_code": cycle.gas_type_at_dispatch_id or "",
                "sent_at": cycle.sent_at,
                "returned_at": cycle.returned_at,
            }
        )
    return render(
        request,
        "operations/cycle_correction_form.html",
        {
            "form": form,
            "cycle": cycle,
            "idempotency_key": request.POST.get("idempotency_key", "") or str(uuid.uuid4()),
        },
    )


@role_required(*ADMIN_ONLY)
def delete_cycle_history_view(request, cycle_id):
    cycle = get_object_or_404(Cycle.objects.select_related("cylinder", "customer"), pk=cycle_id)
    if request.method == "POST":
        try:
            services.delete_cycle_history(
                actor=request.user,
                cycle_id=cycle.id,
                idempotency_key=request.POST.get("idempotency_key", "").strip(),
            )
        except DomainError as exc:
            messages.error(request, str(exc))
            return redirect("operations:usage-log")
        messages.success(request, "Riwayat penggunaan tabung dihapus.")
        return redirect("operations:usage-log")
    return render(
        request,
        "operations/cycle_confirm_delete.html",
        {"cycle": cycle, "idempotency_key": str(uuid.uuid4())},
    )


@role_required(*ADMIN_ONLY)
def maintenance_start_view(request):
    spec = OperationSpec(
        form_class=op_forms.MaintenanceStartForm,
        service_fn=services.start_maintenance,
        title="Mulai maintenance",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "occurred_at": d["occurred_at"],
            "reason": d["reason"].strip(),
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Tanggal mulai", d["occurred_at"].strftime("%d/%m/%Y")),
            ("Alasan", d["reason"].strip()),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def maintenance_complete_view(request):
    spec = OperationSpec(
        form_class=op_forms.MaintenanceCompleteForm,
        service_fn=services.complete_maintenance,
        title="Selesaikan maintenance",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "occurred_at": d["occurred_at"],
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Tanggal selesai", d["occurred_at"].strftime("%d/%m/%Y")),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def retire_view(request):
    spec = OperationSpec(
        form_class=op_forms.RetireForm,
        service_fn=services.retire_cylinder,
        title="Pensiunkan tabung",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "occurred_at": d["occurred_at"],
            "reason": d["reason"].strip(),
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Tanggal pensiun", d["occurred_at"].strftime("%d/%m/%Y")),
            ("Alasan", d["reason"].strip()),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)


@role_required(*ADMIN_ONLY)
def reverse_dispatch_view(request):
    spec = OperationSpec(
        form_class=op_forms.ReverseDispatchForm,
        service_fn=services.reverse_dispatch,
        title="Koreksi/batalkan kirim",
        build_service_kwargs=lambda d: {
            "serial_number": d["serial_number"].strip(),
            "reason": d["reason"].strip(),
        },
        build_preview_rows=lambda d: [
            ("Nomor tabung", d["serial_number"].strip()),
            ("Alasan", d["reason"].strip()),
        ],
        success_redirect=lambda d: reverse(
            "operations:cylinder-detail", args=[d["serial_number"].strip()]
        ),
    )
    return _operation_view(request, spec)
