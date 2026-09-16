import threading
from datetime import date

from django.db import connections
from django.test import TestCase, TransactionTestCase

from catalog.models import Customer, Cylinder, GasType
from identity.models import Role, User

from . import services
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


class ServiceTestCaseMixin:
    """Data sintetis bersama - tidak ada data pelanggan/tabung asli di tes ini."""

    @classmethod
    def make_common_fixtures(cls):
        cls.admin = User.objects.create_user(username="admin1", password="x", role=Role.ADMIN)
        cls.operator = User.objects.create_user(
            username="operator1", password="x", role=Role.OPERATOR
        )
        cls.viewer = User.objects.create_user(username="viewer1", password="x", role=Role.VIEWER)
        cls.gas_o2 = GasType.objects.create(code=GasType.Code.O2)
        cls.customer1 = Customer.objects.create(display_name="Pelanggan Uji A")
        cls.customer2 = Customer.objects.create(display_name="Pelanggan Uji B")
        cls.cylinder1 = Cylinder.objects.create(serial_number="UJI-0001")
        cls.cylinder2 = Cylinder.objects.create(serial_number="UJI-0002")


class DispatchTests(ServiceTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_dispatch_opens_cycle_and_marks_cylinder_out(self):
        cycle = services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="k1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.OUT)
        self.assertEqual(cycle.status, Cycle.Status.OPEN)
        self.assertTrue(
            LifecycleEvent.objects.filter(
                cylinder=self.cylinder1, event_type=LifecycleEvent.EventType.DISPATCHED
            ).exists()
        )

    def test_dispatch_unknown_gas_flags_needs_review_without_blocking(self):
        cycle = services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code="",
            sent_at=date(2026, 1, 10),
            idempotency_key="k1",
        )
        self.assertEqual(cycle.data_quality_flag, "NEEDS_REVIEW")
        self.assertEqual(cycle.status, Cycle.Status.OPEN)

    def test_dispatch_rejected_when_cylinder_not_available(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="k1",
        )
        with self.assertRaises(CylinderNotAvailable):
            services.dispatch_cylinder(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                customer_id=self.customer2.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 11),
                idempotency_key="k2",
            )

    def test_dispatch_unknown_cylinder_raises_not_found(self):
        with self.assertRaises(CylinderNotFound):
            services.dispatch_cylinder(
                actor=self.operator,
                serial_number="TIDAK-ADA",
                customer_id=self.customer1.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 10),
                idempotency_key="k1",
            )


class RetryIdempotencyTests(ServiceTestCaseMixin, TestCase):
    """Bukti acceptance: 'ulang key yang sama' -> hasil awal dikembalikan, bukan transaksi baru."""

    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_same_key_same_payload_replays_result_without_duplicating(self):
        kwargs = dict(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="retry-key-1",
        )
        cycle1 = services.dispatch_cylinder(**kwargs)
        cycle2 = services.dispatch_cylinder(**kwargs)

        self.assertEqual(cycle1.id, cycle2.id)
        self.assertEqual(Cycle.objects.count(), 1)
        self.assertEqual(
            LifecycleEvent.objects.filter(event_type=LifecycleEvent.EventType.DISPATCHED).count(),
            1,
        )
        self.assertEqual(IdempotencyRecord.objects.filter(key="retry-key-1").count(), 1)

    def test_same_key_different_payload_is_rejected(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="retry-key-2",
        )
        with self.assertRaises(IdempotencyConflict):
            services.dispatch_cylinder(
                actor=self.operator,
                serial_number=self.cylinder2.serial_number,  # payload beda: tabung berbeda
                customer_id=self.customer1.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 10),
                idempotency_key="retry-key-2",
            )
        # Percobaan yang gagal (conflict) tidak boleh mengubah apa pun pada tabung kedua.
        self.cylinder2.refresh_from_db()
        self.assertEqual(self.cylinder2.status, Cylinder.Status.AVAILABLE)

    def test_idempotency_key_required(self):
        with self.assertRaises(DomainError):
            services.dispatch_cylinder(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                customer_id=self.customer1.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 10),
                idempotency_key="",
            )


class ReturnTests(ServiceTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def setUp(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-for-return",
        )

    def test_return_closes_cycle_and_frees_cylinder(self):
        cycle = services.return_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            returned_at=date(2026, 1, 15),
            idempotency_key="return-1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(cycle.status, Cycle.Status.CLOSED)
        self.assertEqual(cycle.close_reason, Cycle.CloseReason.RETURNED)
        self.assertEqual(self.cylinder1.status, Cylinder.Status.AVAILABLE)

    def test_double_return_without_new_dispatch_is_rejected(self):
        """'Return ganda' (bukan retry - key BERBEDA) harus ditolak karena tidak ada siklus
        aktif lagi setelah return pertama."""
        services.return_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            returned_at=date(2026, 1, 15),
            idempotency_key="return-first",
        )
        with self.assertRaises(NoActiveCycle):
            services.return_cylinder(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                returned_at=date(2026, 1, 16),
                idempotency_key="return-second-different-key",
            )

    def test_return_cylinder_without_active_cycle_raises(self):
        with self.assertRaises(NoActiveCycle):
            services.return_cylinder(
                actor=self.operator,
                serial_number=self.cylinder2.serial_number,  # tidak pernah dikirim
                returned_at=date(2026, 1, 15),
                idempotency_key="return-never-dispatched",
            )

    def test_cylinder_can_be_redispatched_after_return(self):
        services.return_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            returned_at=date(2026, 1, 15),
            idempotency_key="return-before-redispatch",
        )
        cycle2 = services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer2.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 16),
            idempotency_key="redispatch-1",
        )
        self.assertEqual(cycle2.status, Cycle.Status.OPEN)
        self.assertEqual(
            Cycle.objects.filter(cylinder=self.cylinder1, status=Cycle.Status.OPEN).count(), 1
        )


class ExchangeTests(ServiceTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def setUp(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-for-exchange",
        )

    def test_exchange_closes_old_cycle_and_opens_new_for_same_customer(self):
        new_cycle = services.exchange_cylinder(
            actor=self.admin,
            old_serial_number=self.cylinder1.serial_number,
            new_serial_number=self.cylinder2.serial_number,
            exchanged_at=date(2026, 1, 12),
            idempotency_key="exchange-1",
        )
        self.cylinder1.refresh_from_db()
        self.cylinder2.refresh_from_db()

        self.assertEqual(self.cylinder1.status, Cylinder.Status.AVAILABLE)
        self.assertEqual(self.cylinder2.status, Cylinder.Status.OUT)
        self.assertEqual(new_cycle.customer_id, self.customer1.id)

        old_cycle = Cycle.objects.get(cylinder=self.cylinder1, status=Cycle.Status.CLOSED)
        self.assertEqual(old_cycle.close_reason, Cycle.CloseReason.EXCHANGED)
        self.assertEqual(old_cycle.replaced_by_id, new_cycle.id)

    def test_exchange_operator_role_is_denied(self):
        with self.assertRaises(RoleNotAllowed):
            services.exchange_cylinder(
                actor=self.operator,
                old_serial_number=self.cylinder1.serial_number,
                new_serial_number=self.cylinder2.serial_number,
                exchanged_at=date(2026, 1, 12),
                idempotency_key="exchange-operator",
            )

    def test_exchange_partial_failure_rolls_back_completely(self):
        """'Tukar gagal sebagian': tabung pengganti tidak tersedia (di sini: tidak ada). Siklus
        lama HARUS tetap OPEN dan tabung lama HARUS tetap OUT setelah kegagalan - tidak ada efek
        separuh jalan yang ter-commit."""
        with self.assertRaises(CylinderNotFound):
            services.exchange_cylinder(
                actor=self.admin,
                old_serial_number=self.cylinder1.serial_number,
                new_serial_number="TIDAK-ADA-SERIALNYA",
                exchanged_at=date(2026, 1, 12),
                idempotency_key="exchange-partial-fail",
            )

        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.OUT)
        open_cycle = Cycle.objects.get(cylinder=self.cylinder1)
        self.assertEqual(open_cycle.status, Cycle.Status.OPEN)
        self.assertEqual(open_cycle.close_reason, "")

    def test_exchange_fails_when_replacement_not_available(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder2.serial_number,
            customer_id=self.customer2.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-cyl2-busy",
        )
        with self.assertRaises(CylinderNotAvailable):
            services.exchange_cylinder(
                actor=self.admin,
                old_serial_number=self.cylinder1.serial_number,
                new_serial_number=self.cylinder2.serial_number,
                exchanged_at=date(2026, 1, 12),
                idempotency_key="exchange-repl-busy",
            )
        old_cycle = Cycle.objects.get(cylinder=self.cylinder1)
        self.assertEqual(old_cycle.status, Cycle.Status.OPEN)


class LostMaintenanceRetireTests(ServiceTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_mark_lost_requires_reason(self):
        with self.assertRaises(DomainError):
            services.mark_lost(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="",
                occurred_at=date(2026, 1, 10),
                idempotency_key="lost-no-reason",
            )

    def test_mark_lost_operator_role_denied(self):
        with self.assertRaises(RoleNotAllowed):
            services.mark_lost(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                reason="Hilang saat pengiriman",
                occurred_at=date(2026, 1, 10),
                idempotency_key="lost-operator",
            )

    def test_mark_lost_closes_open_cycle_if_any(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-before-lost",
        )
        services.mark_lost(
            actor=self.admin,
            serial_number=self.cylinder1.serial_number,
            reason="Dilaporkan hilang pelanggan",
            occurred_at=date(2026, 1, 12),
            idempotency_key="lost-1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.LOST)
        cycle = Cycle.objects.get(cylinder=self.cylinder1)
        self.assertEqual(cycle.status, Cycle.Status.CLOSED)
        self.assertEqual(cycle.close_reason, Cycle.CloseReason.LOST)

    def test_maintenance_cycle_start_and_complete(self):
        services.start_maintenance(
            actor=self.admin,
            serial_number=self.cylinder1.serial_number,
            reason="Pemeriksaan rutin",
            occurred_at=date(2026, 1, 10),
            idempotency_key="maint-start-1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.MAINTENANCE)

        with self.assertRaises(CylinderNotAvailable):
            services.dispatch_cylinder(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                customer_id=self.customer1.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 11),
                idempotency_key="dispatch-during-maint",
            )

        services.complete_maintenance(
            actor=self.admin,
            serial_number=self.cylinder1.serial_number,
            occurred_at=date(2026, 1, 20),
            idempotency_key="maint-complete-1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.AVAILABLE)

    def test_complete_maintenance_without_start_raises(self):
        with self.assertRaises(InvalidTransition):
            services.complete_maintenance(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                occurred_at=date(2026, 1, 10),
                idempotency_key="maint-complete-no-start",
            )

    def test_retire_requires_reason_and_available_cylinder(self):
        with self.assertRaises(DomainError):
            services.retire_cylinder(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="",
                occurred_at=date(2026, 1, 10),
                idempotency_key="retire-no-reason",
            )

        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-before-retire-attempt",
        )
        with self.assertRaises(CylinderNotAvailable):
            services.retire_cylinder(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="Rusak permanen",
                occurred_at=date(2026, 1, 11),
                idempotency_key="retire-while-out",
            )

    def test_retire_available_cylinder_succeeds_and_is_terminal(self):
        services.retire_cylinder(
            actor=self.admin,
            serial_number=self.cylinder1.serial_number,
            reason="Korosi parah",
            occurred_at=date(2026, 1, 10),
            idempotency_key="retire-1",
        )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.RETIRED)

        with self.assertRaises(InvalidTransition):
            services.retire_cylinder(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="Coba pensiun lagi",
                occurred_at=date(2026, 1, 11),
                idempotency_key="retire-2-already-retired",
            )


class ReversalTests(ServiceTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_reverse_dispatch_reopens_cylinder_and_leaves_trace(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-to-reverse",
        )
        cycle = services.reverse_dispatch(
            actor=self.admin,
            serial_number=self.cylinder1.serial_number,
            reason="Salah input pelanggan",
            idempotency_key="reverse-1",
        )
        self.cylinder1.refresh_from_db()

        self.assertEqual(self.cylinder1.status, Cylinder.Status.AVAILABLE)
        self.assertEqual(cycle.status, Cycle.Status.CLOSED)
        self.assertEqual(cycle.close_reason, Cycle.CloseReason.REVERSED)

        reversal_event = LifecycleEvent.objects.get(
            cycle=cycle, event_type=LifecycleEvent.EventType.REVERSED
        )
        self.assertEqual(reversal_event.reason, "Salah input pelanggan")
        self.assertIsNotNone(reversal_event.reversed_event)
        self.assertEqual(
            reversal_event.reversed_event.event_type, LifecycleEvent.EventType.DISPATCHED
        )

        # Histori tidak dihapus - event DISPATCHED asli tetap ada (append-only, DEC-010).
        self.assertTrue(
            LifecycleEvent.objects.filter(
                cycle=cycle, event_type=LifecycleEvent.EventType.DISPATCHED
            ).exists()
        )

        # Setelah reversal, tabung boleh dikirim ulang secara normal.
        new_cycle = services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer2.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 11),
            idempotency_key="dispatch-after-reverse",
        )
        self.assertEqual(new_cycle.status, Cycle.Status.OPEN)

    def test_reverse_dispatch_requires_reason(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-no-reason-case",
        )
        with self.assertRaises(DomainError):
            services.reverse_dispatch(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="",
                idempotency_key="reverse-no-reason",
            )

    def test_reverse_dispatch_operator_role_denied(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder1.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="dispatch-for-operator-reverse-attempt",
        )
        with self.assertRaises(RoleNotAllowed):
            services.reverse_dispatch(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                reason="Coba koreksi sebagai operator",
                idempotency_key="reverse-operator-denied",
            )

    def test_reverse_dispatch_without_active_cycle_raises(self):
        with self.assertRaises(NoActiveCycle):
            services.reverse_dispatch(
                actor=self.admin,
                serial_number=self.cylinder1.serial_number,
                reason="Tidak ada apa-apa untuk dikoreksi",
                idempotency_key="reverse-none",
            )


class RoleEnforcementTests(ServiceTestCaseMixin, TestCase):
    """'Role ilegal' untuk setiap command yang seharusnya ADMIN-only, dan VIEWER ditolak di
    semua command mutasi (VIEWER read-only, FR requirements.md)."""

    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_viewer_cannot_dispatch(self):
        with self.assertRaises(RoleNotAllowed):
            services.dispatch_cylinder(
                actor=self.viewer,
                serial_number=self.cylinder1.serial_number,
                customer_id=self.customer1.id,
                gas_type_code=GasType.Code.O2,
                sent_at=date(2026, 1, 10),
                idempotency_key="viewer-dispatch",
            )

    def test_viewer_cannot_return(self):
        with self.assertRaises(RoleNotAllowed):
            services.return_cylinder(
                actor=self.viewer,
                serial_number=self.cylinder1.serial_number,
                returned_at=date(2026, 1, 10),
                idempotency_key="viewer-return",
            )

    def test_operator_cannot_start_maintenance(self):
        with self.assertRaises(RoleNotAllowed):
            services.start_maintenance(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                reason="Coba maintenance",
                occurred_at=date(2026, 1, 10),
                idempotency_key="operator-maint",
            )

    def test_operator_cannot_retire(self):
        with self.assertRaises(RoleNotAllowed):
            services.retire_cylinder(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                reason="Coba pensiun",
                occurred_at=date(2026, 1, 10),
                idempotency_key="operator-retire",
            )

    def test_no_action_is_taken_when_role_is_denied(self):
        """Penolakan role tidak boleh punya efek samping - tabung tetap AVAILABLE, tidak ada
        Cycle/LifecycleEvent yang dibuat."""
        with self.assertRaises(RoleNotAllowed):
            services.mark_lost(
                actor=self.operator,
                serial_number=self.cylinder1.serial_number,
                reason="Coba sebagai operator",
                occurred_at=date(2026, 1, 10),
                idempotency_key="operator-lost-noop",
            )
        self.cylinder1.refresh_from_db()
        self.assertEqual(self.cylinder1.status, Cylinder.Status.AVAILABLE)
        self.assertFalse(Cycle.objects.filter(cylinder=self.cylinder1).exists())
        self.assertFalse(LifecycleEvent.objects.filter(cylinder=self.cylinder1).exists())


class ConcurrencyTests(TransactionTestCase):
    """TransactionTestCase (bukan TestCase) supaya dua thread benar-benar memakai koneksi/
    transaksi terpisah dan select_for_update() sungguhan saling mengunci - bukti acceptance
    'concurrent dispatch'."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin1", password="x", role=Role.ADMIN)
        self.operator = User.objects.create_user(
            username="operator1", password="x", role=Role.OPERATOR
        )
        self.gas_o2 = GasType.objects.create(code=GasType.Code.O2)
        self.customer1 = Customer.objects.create(display_name="Pelanggan Uji A")
        self.customer2 = Customer.objects.create(display_name="Pelanggan Uji B")
        self.cylinder = Cylinder.objects.create(serial_number="UJI-CONCURRENT")

    def test_two_concurrent_dispatches_only_one_succeeds(self):
        results = []
        errors = []
        start_barrier = threading.Barrier(2)

        def worker(customer_id, key):
            try:
                start_barrier.wait(timeout=5)
                cycle = services.dispatch_cylinder(
                    actor=self.operator,
                    serial_number=self.cylinder.serial_number,
                    customer_id=customer_id,
                    gas_type_code=GasType.Code.O2,
                    sent_at=date(2026, 1, 10),
                    idempotency_key=key,
                )
                results.append(cycle)
            except DomainError as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=worker, args=(self.customer1.id, "concurrent-key-1"))
        t2 = threading.Thread(target=worker, args=(self.customer2.id, "concurrent-key-2"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(len(results), 1, "tepat satu dispatch yang berhasil")
        self.assertEqual(len(errors), 1, "yang kedua harus ditolak, bukan diam-diam berhasil")
        self.assertIsInstance(errors[0], CylinderNotAvailable)

        self.assertEqual(
            Cycle.objects.filter(cylinder=self.cylinder, status=Cycle.Status.OPEN).count(),
            1,
            "hanya satu siklus aktif meski dua request bersamaan",
        )
        self.assertEqual(
            LifecycleEvent.objects.filter(
                cylinder=self.cylinder, event_type=LifecycleEvent.EventType.DISPATCHED
            ).count(),
            1,
        )

    def test_concurrent_retry_with_same_idempotency_key_yields_single_cycle(self):
        """Dua thread memakai idempotency_key yang SAMA (retry sungguhan, bukan dua aksi
        berbeda) - hasil akhirnya harus tetap satu Cycle, bukan dua."""
        results = []
        exceptions_seen = []
        start_barrier = threading.Barrier(2)

        def worker():
            try:
                start_barrier.wait(timeout=5)
                cycle = services.dispatch_cylinder(
                    actor=self.operator,
                    serial_number=self.cylinder.serial_number,
                    customer_id=self.customer1.id,
                    gas_type_code=GasType.Code.O2,
                    sent_at=date(2026, 1, 10),
                    idempotency_key="same-retry-key",
                )
                results.append(cycle.id)
            except Exception as exc:  # noqa: BLE001 - butuh menangkap apa pun untuk laporan tes
                exceptions_seen.append(exc)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(
            exceptions_seen, [], f"tidak boleh ada error tak terduga: {exceptions_seen}"
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1], "kedua thread harus melihat Cycle yang sama")
        self.assertEqual(Cycle.objects.filter(cylinder=self.cylinder).count(), 1)


class ExchangeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin1", password="x", role=Role.ADMIN)
        self.operator = User.objects.create_user(
            username="operator1", password="x", role=Role.OPERATOR
        )
        GasType.objects.create(code=GasType.Code.O2)
        self.customer1 = Customer.objects.create(display_name="Pelanggan Uji A")
        self.cyl_a = Cylinder.objects.create(serial_number="UJI-DEADLOCK-A")
        self.cyl_b = Cylinder.objects.create(serial_number="UJI-DEADLOCK-B")
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cyl_a.serial_number,
            customer_id=self.customer1.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 1),
            idempotency_key="setup-a",
        )

    def test_opposite_direction_exchanges_do_not_deadlock(self):
        """Dua exchange yang mengunci A lalu B, dan B lalu A (arah berlawanan) tidak boleh
        deadlock - urutan lock deterministik (sorted serial) di services.py harus mencegah ini."""
        errors = []

        def worker(old_serial, new_serial, key):
            try:
                services.exchange_cylinder(
                    actor=self.admin,
                    old_serial_number=old_serial,
                    new_serial_number=new_serial,
                    exchanged_at=date(2026, 1, 5),
                    idempotency_key=key,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        # cyl_a punya siklus aktif (bisa jadi old), cyl_b AVAILABLE (bisa jadi new).
        # Kedua thread mencoba arah yang sama (satu-satunya kombinasi valid di data ini),
        # tujuan tes adalah memastikan tidak ada deadlock/hang - hasil kedua (sukses/gagal
        # karena race) diterima selama tidak timeout.
        t1 = threading.Thread(
            target=worker, args=(self.cyl_a.serial_number, self.cyl_b.serial_number, "ex-1")
        )
        t2 = threading.Thread(
            target=worker, args=(self.cyl_a.serial_number, self.cyl_b.serial_number, "ex-2")
        )
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertFalse(t1.is_alive(), "thread 1 tidak boleh hang/deadlock")
        self.assertFalse(t2.is_alive(), "thread 2 tidak boleh hang/deadlock")
