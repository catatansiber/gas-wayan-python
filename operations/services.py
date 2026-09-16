"""Layanan domain bersama untuk web DAN Telegram (requirements.md: "Web dan Telegram memakai
service serta aturan domain yang sama"). Setiap fungsi publik di sini:

- memeriksa role di server (bukan mengandalkan UI) - lihat `_require_role`;
- wajib `idempotency_key` non-kosong dan payload-aware (key sama + payload sama -> replay hasil
  lama; key sama + payload beda -> IdempotencyConflict);
- mengunci baris relevan (`select_for_update`) di dalam satu `transaction.atomic()` supaya
  concurrency tidak menggandakan transaksi;
- menulis AuditLog dan OutboxEvent dalam transaksi yang sama dengan mutasi domain (ADR-P007/P008).

Jangan memanggil `Cylinder.save()`/`Cycle.save()` untuk mengubah status di luar modul ini -
semua mutasi lifecycle HARUS lewat fungsi di sini supaya audit/outbox/idempotency konsisten.
"""

import hashlib
import json

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from audit.models import AuditLog, OutboxEvent
from catalog.models import Customer, Cylinder, GasType
from identity.models import Role

from .exceptions import (
    CylinderNotAvailable,
    CylinderNotFound,
    DomainError,
    IdempotencyConflict,
    InvalidTransition,
    NoActiveCycle,
    RoleNotAllowed,
)
from .models import Cycle, IdempotencyRecord, LifecycleEvent

OPERATOR_AND_ADMIN = {Role.ADMIN, Role.OPERATOR}
ADMIN_ONLY = {Role.ADMIN}


def _require_role(actor, allowed_roles):
    if actor is None or getattr(actor, "role", None) not in allowed_roles:
        raise RoleNotAllowed(
            f"Role '{getattr(actor, 'role', None)}' tidak diizinkan menjalankan command ini."
        )


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claim_idempotency(scope, key, actor, payload_hash):
    """Klaim (scope, actor, key) lewat INSERT ber-unique-constraint. Dua request bersamaan
    dengan key sama: yang kedua akan diblok Postgres sampai yang pertama commit/rollback, lalu
    IntegrityError (bila commit) atau berhasil insert (bila rollback) - tidak pernah dua-duanya
    lolos. `transaction.atomic()` di sini membuat SAVEPOINT supaya IntegrityError tidak meracuni
    transaksi luar (pola standar Django untuk menangkap IntegrityError)."""
    if not key:
        raise DomainError("idempotency_key wajib diisi.")
    try:
        with transaction.atomic():
            record = IdempotencyRecord.objects.create(
                scope=scope, key=key, actor=actor, payload_hash=payload_hash
            )
        return record, True
    except IntegrityError:
        record = IdempotencyRecord.objects.get(scope=scope, key=key, actor=actor)
        if record.payload_hash != payload_hash:
            raise IdempotencyConflict(
                f"Idempotency key '{key}' sudah dipakai dengan payload berbeda."
            ) from None
        return record, False


def _write_audit(actor, source, action, entity_type, entity_id, before, after, reason=""):
    AuditLog.objects.create(
        actor=actor,
        role_at_time=getattr(actor, "role", ""),
        source=source,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        reason=reason,
    )


def _write_outbox(event_type, payload):
    OutboxEvent.objects.create(event_type=event_type, payload=payload)


def _serialize_cycle(cycle):
    return {
        "id": str(cycle.id),
        "cylinder": cycle.cylinder.serial_number,
        "customer": str(cycle.customer_id),
        "status": cycle.status,
        "sent_at": str(cycle.sent_at),
        "returned_at": str(cycle.returned_at) if cycle.returned_at else None,
        "close_reason": cycle.close_reason,
        "data_quality_flag": cycle.data_quality_flag,
    }


def _serialize_cylinder(cylinder):
    return {
        "id": str(cylinder.id),
        "serial_number": cylinder.serial_number,
        "status": cylinder.status,
    }


def _lock_cylinder(serial_number):
    try:
        return Cylinder.objects.select_for_update().get(serial_number=serial_number)
    except Cylinder.DoesNotExist:
        raise CylinderNotFound(serial_number) from None


def _lock_open_cycle(cylinder):
    cycle = (
        Cycle.objects.select_for_update()
        .filter(cylinder=cylinder, status=Cycle.Status.OPEN)
        .first()
    )
    if cycle is None:
        raise NoActiveCycle(cylinder.serial_number)
    return cycle


# --------------------------------------------------------------------------------------
# Kirim (dispatch)
# --------------------------------------------------------------------------------------


def dispatch_cylinder(
    *, actor, serial_number, customer_id, gas_type_code, sent_at, idempotency_key, source="WEB"
):
    _require_role(actor, OPERATOR_AND_ADMIN)
    payload = {
        "op": "dispatch",
        "serial_number": serial_number,
        "customer_id": str(customer_id),
        "gas_type_code": gas_type_code,
        "sent_at": str(sent_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency("dispatch", idempotency_key, actor, payload_hash)
        if not created:
            return record.result_cycle

        cylinder = _lock_cylinder(serial_number)
        if cylinder.status != Cylinder.Status.AVAILABLE:
            raise CylinderNotAvailable(
                f"Tabung {serial_number} berstatus {cylinder.status}, tidak dapat dikirim."
            )

        try:
            customer = Customer.objects.get(pk=customer_id, is_active=True)
        except Customer.DoesNotExist:
            raise DomainError("Pelanggan tidak ditemukan atau tidak aktif.") from None

        gas_type = None
        data_quality_flag = ""
        if gas_type_code:
            gas_type = GasType.objects.filter(pk=gas_type_code).first()
            if gas_type is None:
                data_quality_flag = "NEEDS_REVIEW"
        else:
            data_quality_flag = "NEEDS_REVIEW"

        cycle = Cycle.objects.create(
            cylinder=cylinder,
            customer=customer,
            gas_type_at_dispatch=gas_type,
            status=Cycle.Status.OPEN,
            sent_at=sent_at,
            data_quality_flag=data_quality_flag,
        )
        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=cycle,
            event_type=LifecycleEvent.EventType.DISPATCHED,
            occurred_at=sent_at,
            actor=actor,
            source=source,
        )
        cylinder.status = Cylinder.Status.OUT
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor, source, "cylinder.dispatch", "Cycle", cycle.id, None, _serialize_cycle(cycle)
        )
        _write_outbox("cycle.dispatched", {"cycle_id": str(cycle.id), "cylinder": serial_number})

        record.result_cycle = cycle
        record.result_cylinder = cylinder
        record.save(update_fields=["result_cycle", "result_cylinder"])
        return cycle


# --------------------------------------------------------------------------------------
# Kembali (return)
# --------------------------------------------------------------------------------------


def return_cylinder(
    *, actor, serial_number, returned_at, idempotency_key, source="WEB", date_unknown=False
):
    _require_role(actor, OPERATOR_AND_ADMIN)
    payload = {
        "op": "return",
        "serial_number": serial_number,
        "returned_at": str(returned_at) if returned_at else None,
        "date_unknown": date_unknown,
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency("return", idempotency_key, actor, payload_hash)
        if not created:
            return record.result_cycle

        cylinder = _lock_cylinder(serial_number)
        cycle = _lock_open_cycle(cylinder)
        before = _serialize_cycle(cycle)

        cycle.status = Cycle.Status.CLOSED
        cycle.returned_at = returned_at
        cycle.close_reason = Cycle.CloseReason.RETURNED
        cycle.date_unknown = date_unknown
        cycle.version += 1
        cycle.save(
            update_fields=[
                "status",
                "returned_at",
                "close_reason",
                "date_unknown",
                "version",
                "updated_at",
            ]
        )
        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=cycle,
            event_type=LifecycleEvent.EventType.RETURNED,
            occurred_at=None if date_unknown else returned_at,
            date_unknown=date_unknown,
            actor=actor,
            source=source,
        )
        cylinder.status = Cylinder.Status.AVAILABLE
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor, source, "cylinder.return", "Cycle", cycle.id, before, _serialize_cycle(cycle)
        )
        _write_outbox("cycle.returned", {"cycle_id": str(cycle.id), "cylinder": serial_number})

        record.result_cycle = cycle
        record.result_cylinder = cylinder
        record.save(update_fields=["result_cycle", "result_cylinder"])
        return cycle


# --------------------------------------------------------------------------------------
# Tukar (exchange) - ADMIN only
# --------------------------------------------------------------------------------------


def exchange_cylinder(
    *,
    actor,
    old_serial_number,
    new_serial_number,
    exchanged_at,
    idempotency_key,
    customer_id=None,
    source="WEB",
):
    _require_role(actor, ADMIN_ONLY)
    if old_serial_number == new_serial_number:
        raise DomainError("Tabung lama dan tabung pengganti tidak boleh sama.")

    payload = {
        "op": "exchange",
        "old_serial_number": old_serial_number,
        "new_serial_number": new_serial_number,
        "customer_id": str(customer_id) if customer_id else None,
        "exchanged_at": str(exchanged_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency("exchange", idempotency_key, actor, payload_hash)
        if not created:
            return record.result_cycle

        # Kunci dua tabung dalam urutan deterministik (berdasarkan serial_number) untuk
        # mengurangi risiko deadlock saat dua pertukaran bersamaan menyentuh tabung yang
        # sama dari arah berbeda (ADR-P006).
        ordered_serials = sorted([old_serial_number, new_serial_number])
        locked = {s: _lock_cylinder(s) for s in ordered_serials}
        old_cylinder = locked[old_serial_number]
        new_cylinder = locked[new_serial_number]

        old_cycle = _lock_open_cycle(old_cylinder)
        if customer_id and str(old_cycle.customer_id) != str(customer_id):
            raise DomainError("Pelanggan/relasi harus sama dengan relasi pada tabung lama.")
        if new_cylinder.status != Cylinder.Status.AVAILABLE:
            raise CylinderNotAvailable(
                f"Tabung pengganti {new_serial_number} berstatus {new_cylinder.status}, "
                "tidak tersedia untuk pertukaran."
            )

        customer = old_cycle.customer
        before_old = _serialize_cycle(old_cycle)

        old_cycle.status = Cycle.Status.CLOSED
        old_cycle.returned_at = exchanged_at
        old_cycle.close_reason = Cycle.CloseReason.EXCHANGED
        old_cycle.version += 1
        old_cycle.save(
            update_fields=["status", "returned_at", "close_reason", "version", "updated_at"]
        )
        LifecycleEvent.objects.create(
            cylinder=old_cylinder,
            cycle=old_cycle,
            event_type=LifecycleEvent.EventType.EXCHANGED_OUT,
            occurred_at=exchanged_at,
            actor=actor,
            source=source,
        )
        old_cylinder.status = Cylinder.Status.AVAILABLE
        old_cylinder.save(update_fields=["status", "updated_at"])

        new_cycle = Cycle.objects.create(
            cylinder=new_cylinder,
            customer=customer,
            gas_type_at_dispatch=old_cycle.gas_type_at_dispatch,
            status=Cycle.Status.OPEN,
            sent_at=exchanged_at,
        )
        LifecycleEvent.objects.create(
            cylinder=new_cylinder,
            cycle=new_cycle,
            event_type=LifecycleEvent.EventType.EXCHANGED_IN,
            occurred_at=exchanged_at,
            actor=actor,
            source=source,
        )
        new_cylinder.status = Cylinder.Status.OUT
        new_cylinder.save(update_fields=["status", "updated_at"])

        old_cycle.replaced_by = new_cycle
        old_cycle.save(update_fields=["replaced_by"])

        _write_audit(
            actor,
            source,
            "cylinder.exchange",
            "Cycle",
            old_cycle.id,
            before_old,
            _serialize_cycle(old_cycle),
        )
        _write_outbox(
            "cycle.exchanged",
            {
                "old_cycle_id": str(old_cycle.id),
                "new_cycle_id": str(new_cycle.id),
                "old_cylinder": old_serial_number,
                "new_cylinder": new_serial_number,
            },
        )

        record.result_cycle = new_cycle
        record.save(update_fields=["result_cycle"])
        return new_cycle


# --------------------------------------------------------------------------------------
# Hilang (lost) - ADMIN only
# --------------------------------------------------------------------------------------


def mark_lost(*, actor, serial_number, reason, occurred_at, idempotency_key, source="WEB"):
    _require_role(actor, ADMIN_ONLY)
    if not reason:
        raise DomainError("Alasan wajib diisi untuk melaporkan tabung hilang.")

    payload = {
        "op": "lost",
        "serial_number": serial_number,
        "reason": reason,
        "occurred_at": str(occurred_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency("lost", idempotency_key, actor, payload_hash)
        if not created:
            return record.result_cylinder

        cylinder = _lock_cylinder(serial_number)
        if cylinder.status == Cylinder.Status.RETIRED:
            raise InvalidTransition(f"Tabung {serial_number} sudah RETIRED, tidak bisa hilang.")
        before = _serialize_cylinder(cylinder)

        cycle = (
            Cycle.objects.select_for_update()
            .filter(cylinder=cylinder, status=Cycle.Status.OPEN)
            .first()
        )
        if cycle is not None:
            cycle.status = Cycle.Status.CLOSED
            cycle.returned_at = occurred_at
            cycle.close_reason = Cycle.CloseReason.LOST
            cycle.version += 1
            cycle.save(
                update_fields=["status", "returned_at", "close_reason", "version", "updated_at"]
            )

        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=cycle,
            event_type=LifecycleEvent.EventType.LOST,
            occurred_at=occurred_at,
            actor=actor,
            source=source,
            reason=reason,
        )
        cylinder.status = Cylinder.Status.LOST
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor,
            source,
            "cylinder.lost",
            "Cylinder",
            cylinder.id,
            before,
            _serialize_cylinder(cylinder),
            reason=reason,
        )
        _write_outbox("cylinder.lost", {"cylinder": serial_number, "reason": reason})

        record.result_cylinder = cylinder
        record.save(update_fields=["result_cylinder"])
        return cylinder


# --------------------------------------------------------------------------------------
# Koreksi riwayat siklus - ADMIN only. Nilai Cycle diperbarui melalui service ini, sedangkan
# event lama tidak pernah ditulis ulang; event CORRECTED dan AuditLog menjelaskan perubahan.
# --------------------------------------------------------------------------------------


def correct_cycle(
    *,
    actor,
    cycle_id,
    customer_id,
    gas_type_code,
    sent_at,
    returned_at,
    reason,
    idempotency_key,
    source="WEB",
):
    _require_role(actor, ADMIN_ONLY)
    if not reason:
        raise DomainError("Alasan perubahan riwayat wajib diisi.")
    payload = {
        "op": "correct_cycle",
        "cycle_id": str(cycle_id),
        "customer_id": str(customer_id),
        "gas_type_code": gas_type_code or "",
        "sent_at": str(sent_at),
        "returned_at": str(returned_at) if returned_at else None,
        "reason": reason,
    }
    with transaction.atomic():
        record, created = _claim_idempotency(
            "correct_cycle", idempotency_key, actor, _payload_hash(payload)
        )
        if not created:
            return record.result_cycle
        try:
            cycle = Cycle.objects.select_for_update().select_related("cylinder").get(pk=cycle_id)
            customer = Customer.objects.get(pk=customer_id, is_active=True)
        except (Cycle.DoesNotExist, Customer.DoesNotExist):
            raise DomainError("Siklus atau pelanggan tidak ditemukan/tidak aktif.") from None
        if cycle.status == Cycle.Status.OPEN and returned_at:
            raise DomainError(
                "Siklus yang belum kembali tidak boleh diberi tanggal kembali lewat koreksi."
            )
        if (
            cycle.status == Cycle.Status.CLOSED
            and cycle.close_reason == Cycle.CloseReason.RETURNED
            and not returned_at
        ):
            raise DomainError("Siklus kembali harus memiliki tanggal kembali.")
        gas_type = GasType.objects.filter(pk=gas_type_code).first() if gas_type_code else None
        before = _serialize_cycle(cycle)
        cycle.customer = customer
        cycle.gas_type_at_dispatch = gas_type
        cycle.sent_at = sent_at
        if cycle.status == Cycle.Status.CLOSED:
            cycle.returned_at = returned_at
        cycle.version += 1
        cycle.save(
            update_fields=[
                "customer",
                "gas_type_at_dispatch",
                "sent_at",
                "returned_at",
                "version",
                "updated_at",
            ]
        )
        LifecycleEvent.objects.create(
            cylinder=cycle.cylinder,
            cycle=cycle,
            event_type=LifecycleEvent.EventType.CORRECTED,
            occurred_at=sent_at,
            actor=actor,
            source=source,
            reason=reason,
        )
        _write_audit(
            actor,
            source,
            "cycle.correct",
            "Cycle",
            cycle.id,
            before,
            _serialize_cycle(cycle),
            reason,
        )
        _write_outbox(
            "cycle.corrected", {"cycle_id": str(cycle.id), "cylinder": cycle.cylinder.serial_number}
        )
        record.result_cycle = cycle
        record.result_cylinder = cycle.cylinder
        record.save(update_fields=["result_cycle", "result_cylinder"])
        return cycle


def delete_cycle_history(*, actor, cycle_id, idempotency_key, source="WEB"):
    """Hapus satu riwayat siklus beserta event-nya melalui jalur terkontrol Admin.

    Riwayat yang masih memiliki SourceLink atau rujukan reversal dilindungi agar jejak impor
    dan audit tidak terputus diam-diam.
    """
    _require_role(actor, ADMIN_ONLY)
    payload = {"op": "delete_cycle_history", "cycle_id": str(cycle_id)}
    with transaction.atomic():
        record, created = _claim_idempotency(
            "delete_cycle_history", idempotency_key, actor, _payload_hash(payload)
        )
        if not created:
            return record.result_cylinder
        try:
            cycle = Cycle.objects.select_for_update().select_related("cylinder").get(pk=cycle_id)
        except Cycle.DoesNotExist:
            raise DomainError("Riwayat siklus tidak ditemukan.") from None
        if cycle.source_links.exists():
            raise DomainError("Riwayat hasil publish impor lama tidak dapat dihapus langsung.")
        cylinder = Cylinder.objects.select_for_update().get(pk=cycle.cylinder_id)
        before = _serialize_cycle(cycle)
        try:
            LifecycleEvent.objects.filter(cycle=cycle).delete()
            cycle.delete()
        except (IntegrityError, ProtectedError):
            raise DomainError(
                "Riwayat ini memiliki rujukan koreksi dan tidak dapat dihapus."
            ) from None
        if cylinder.status == Cylinder.Status.OUT:
            cylinder.status = Cylinder.Status.AVAILABLE
            cylinder.save(update_fields=["status", "updated_at"])
        _write_audit(actor, source, "cycle.delete_history", "Cycle", cycle_id, before, None)
        _write_outbox(
            "cycle.history_deleted", {"cycle_id": str(cycle_id), "cylinder": cylinder.serial_number}
        )
        record.result_cylinder = cylinder
        record.save(update_fields=["result_cylinder"])
        return cylinder


# --------------------------------------------------------------------------------------
# Maintenance - ADMIN only
# --------------------------------------------------------------------------------------


def start_maintenance(*, actor, serial_number, reason, occurred_at, idempotency_key, source="WEB"):
    _require_role(actor, ADMIN_ONLY)
    payload = {
        "op": "maintenance_start",
        "serial_number": serial_number,
        "reason": reason,
        "occurred_at": str(occurred_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency(
            "maintenance_start", idempotency_key, actor, payload_hash
        )
        if not created:
            return record.result_cylinder

        cylinder = _lock_cylinder(serial_number)
        if cylinder.status != Cylinder.Status.AVAILABLE:
            raise CylinderNotAvailable(
                f"Tabung {serial_number} berstatus {cylinder.status}; hanya tabung AVAILABLE "
                "yang bisa masuk maintenance (kembalikan dulu bila sedang OUT)."
            )
        before = _serialize_cylinder(cylinder)

        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=None,
            event_type=LifecycleEvent.EventType.MAINTENANCE_STARTED,
            occurred_at=occurred_at,
            actor=actor,
            source=source,
            reason=reason,
        )
        cylinder.status = Cylinder.Status.MAINTENANCE
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor,
            source,
            "cylinder.maintenance_start",
            "Cylinder",
            cylinder.id,
            before,
            _serialize_cylinder(cylinder),
            reason=reason,
        )
        _write_outbox("cylinder.maintenance_started", {"cylinder": serial_number})

        record.result_cylinder = cylinder
        record.save(update_fields=["result_cylinder"])
        return cylinder


def complete_maintenance(*, actor, serial_number, occurred_at, idempotency_key, source="WEB"):
    _require_role(actor, ADMIN_ONLY)
    payload = {
        "op": "maintenance_complete",
        "serial_number": serial_number,
        "occurred_at": str(occurred_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency(
            "maintenance_complete", idempotency_key, actor, payload_hash
        )
        if not created:
            return record.result_cylinder

        cylinder = _lock_cylinder(serial_number)
        if cylinder.status != Cylinder.Status.MAINTENANCE:
            raise InvalidTransition(
                f"Tabung {serial_number} berstatus {cylinder.status}, bukan MAINTENANCE."
            )
        before = _serialize_cylinder(cylinder)

        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=None,
            event_type=LifecycleEvent.EventType.MAINTENANCE_COMPLETED,
            occurred_at=occurred_at,
            actor=actor,
            source=source,
        )
        cylinder.status = Cylinder.Status.AVAILABLE
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor,
            source,
            "cylinder.maintenance_complete",
            "Cylinder",
            cylinder.id,
            before,
            _serialize_cylinder(cylinder),
        )
        _write_outbox("cylinder.maintenance_completed", {"cylinder": serial_number})

        record.result_cylinder = cylinder
        record.save(update_fields=["result_cylinder"])
        return cylinder


# --------------------------------------------------------------------------------------
# Pensiun (retire) - ADMIN only
# --------------------------------------------------------------------------------------


def retire_cylinder(*, actor, serial_number, reason, occurred_at, idempotency_key, source="WEB"):
    _require_role(actor, ADMIN_ONLY)
    if not reason:
        raise DomainError("Alasan wajib diisi untuk memensiunkan tabung.")

    payload = {
        "op": "retire",
        "serial_number": serial_number,
        "reason": reason,
        "occurred_at": str(occurred_at),
    }
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency("retire", idempotency_key, actor, payload_hash)
        if not created:
            return record.result_cylinder

        cylinder = _lock_cylinder(serial_number)
        if cylinder.status == Cylinder.Status.RETIRED:
            raise InvalidTransition(f"Tabung {serial_number} sudah RETIRED.")
        if cylinder.status == Cylinder.Status.OUT:
            raise CylinderNotAvailable(
                f"Tabung {serial_number} masih OUT; kembalikan dulu sebelum dipensiunkan."
            )
        before = _serialize_cylinder(cylinder)

        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=None,
            event_type=LifecycleEvent.EventType.RETIRED,
            occurred_at=occurred_at,
            actor=actor,
            source=source,
            reason=reason,
        )
        cylinder.status = Cylinder.Status.RETIRED
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor,
            source,
            "cylinder.retire",
            "Cylinder",
            cylinder.id,
            before,
            _serialize_cylinder(cylinder),
            reason=reason,
        )
        _write_outbox("cylinder.retired", {"cylinder": serial_number, "reason": reason})

        record.result_cylinder = cylinder
        record.save(update_fields=["result_cylinder"])
        return cylinder


# --------------------------------------------------------------------------------------
# Koreksi/reversal - ADMIN only. F2 hanya mendukung membatalkan DISPATCH yang salah (kasus
# koreksi paling umum: siklus baru saja dibuka keliru). Reversal untuk event lain (return,
# exchange, dsb.) belum diimplementasikan - dicatat sebagai pekerjaan lanjutan, bukan ditebak.
# --------------------------------------------------------------------------------------


def reverse_dispatch(*, actor, serial_number, reason, idempotency_key, source="WEB"):
    _require_role(actor, ADMIN_ONLY)
    if not reason:
        raise DomainError("Alasan wajib diisi untuk koreksi/reversal.")

    payload = {"op": "reverse_dispatch", "serial_number": serial_number, "reason": reason}
    payload_hash = _payload_hash(payload)

    with transaction.atomic():
        record, created = _claim_idempotency(
            "reverse_dispatch", idempotency_key, actor, payload_hash
        )
        if not created:
            return record.result_cycle

        cylinder = _lock_cylinder(serial_number)
        cycle = _lock_open_cycle(cylinder)
        original_event = (
            cycle.events.filter(event_type=LifecycleEvent.EventType.DISPATCHED)
            .order_by("-created_at")
            .first()
        )
        before = _serialize_cycle(cycle)

        cycle.status = Cycle.Status.CLOSED
        cycle.close_reason = Cycle.CloseReason.REVERSED
        cycle.version += 1
        cycle.save(update_fields=["status", "close_reason", "version", "updated_at"])

        LifecycleEvent.objects.create(
            cylinder=cylinder,
            cycle=cycle,
            event_type=LifecycleEvent.EventType.REVERSED,
            actor=actor,
            source=source,
            reason=reason,
            reversed_event=original_event,
        )
        cylinder.status = Cylinder.Status.AVAILABLE
        cylinder.save(update_fields=["status", "updated_at"])

        _write_audit(
            actor,
            source,
            "cylinder.reverse_dispatch",
            "Cycle",
            cycle.id,
            before,
            _serialize_cycle(cycle),
            reason=reason,
        )
        _write_outbox(
            "cycle.reversed",
            {"cycle_id": str(cycle.id), "cylinder": serial_number, "reason": reason},
        )

        record.result_cycle = cycle
        record.save(update_fields=["result_cycle"])
        return cycle
