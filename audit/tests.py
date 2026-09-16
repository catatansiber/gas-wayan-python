from datetime import date

from django.test import TestCase

from audit.models import AuditLog, OutboxEvent
from catalog.models import Customer, Cylinder, GasType
from identity.models import Role, User
from operations import services


class AuditAndOutboxWrittenBySameTransactionTests(TestCase):
    """AuditLog dan OutboxEvent harus terisi sebagai bagian dari transaksi mutasi domain yang
    sama (ADR-P007/P008), bukan langkah terpisah yang bisa gagal sendiri-sendiri."""

    def setUp(self):
        self.operator = User.objects.create_user(
            username="operator1", password="x", role=Role.OPERATOR
        )
        GasType.objects.create(code=GasType.Code.O2)
        self.customer = Customer.objects.create(display_name="Pelanggan Uji")
        self.cylinder = Cylinder.objects.create(serial_number="AUDIT-001")

    def test_dispatch_writes_audit_log_and_outbox_event(self):
        cycle = services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder.serial_number,
            customer_id=self.customer.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="audit-dispatch-1",
        )

        audit_entry = AuditLog.objects.get(action="cylinder.dispatch", entity_id=str(cycle.id))
        self.assertEqual(audit_entry.actor, self.operator)
        self.assertEqual(audit_entry.role_at_time, Role.OPERATOR)
        self.assertIsNone(audit_entry.before)
        self.assertEqual(audit_entry.after["status"], "OPEN")

        outbox_entry = OutboxEvent.objects.get(event_type="cycle.dispatched")
        self.assertEqual(outbox_entry.payload["cylinder"], self.cylinder.serial_number)
        self.assertIsNone(outbox_entry.processed_at)

    def test_audit_log_reason_recorded_for_correction(self):
        services.dispatch_cylinder(
            actor=self.operator,
            serial_number=self.cylinder.serial_number,
            customer_id=self.customer.id,
            gas_type_code=GasType.Code.O2,
            sent_at=date(2026, 1, 10),
            idempotency_key="audit-dispatch-2",
        )
        admin = User.objects.create_user(username="admin1", password="x", role=Role.ADMIN)
        services.reverse_dispatch(
            actor=admin,
            serial_number=self.cylinder.serial_number,
            reason="Salah pelanggan",
            idempotency_key="audit-reverse-1",
        )
        audit_entry = AuditLog.objects.get(action="cylinder.reverse_dispatch")
        self.assertEqual(audit_entry.reason, "Salah pelanggan")
