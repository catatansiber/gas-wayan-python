"""Tes layar operasional F5 (view+template, lewat Django test Client - bukan tes service
lagi, sudah dites lengkap di operations/tests.py). Data sintetis saja."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Customer, Cylinder, GasType
from identity.models import Role, User

from .models import Cycle, LifecycleEvent


class WebTestCaseMixin:
    @classmethod
    def make_common_fixtures(cls):
        cls.admin = User.objects.create_user(username="w-admin", password="x", role=Role.ADMIN)
        cls.operator = User.objects.create_user(
            username="w-operator", password="x", role=Role.OPERATOR
        )
        cls.viewer = User.objects.create_user(username="w-viewer", password="x", role=Role.VIEWER)
        GasType.objects.get_or_create(code=GasType.Code.O2)
        cls.customer = Customer.objects.create(display_name="Pelanggan Web Uji")
        cls.cylinder = Cylinder.objects.create(serial_number="WEB-0001")


class RoleEnforcementTests(WebTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_viewer_can_read_search_detail_log(self):
        self.client.force_login(self.viewer)
        for url in [
            reverse("operations:search"),
            reverse("operations:usage-log"),
            reverse("operations:cylinder-detail", args=["WEB-0001"]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_viewer_cannot_open_dispatch_form(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("operations:dispatch"))
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_submit_dispatch(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-01",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Cycle.objects.exists())

    def test_operator_cannot_open_admin_only_forms(self):
        self.client.force_login(self.operator)
        for url in [
            reverse("operations:exchange"),
            reverse("operations:lost"),
            reverse("operations:maintenance-start"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_operator_can_open_dispatch_and_return(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("operations:dispatch")).status_code, 200)
        self.assertEqual(self.client.get(reverse("operations:return")).status_code, 200)

    def test_admin_can_open_all_forms(self):
        self.client.force_login(self.admin)
        for url in [
            reverse("operations:dispatch"),
            reverse("operations:return"),
            reverse("operations:exchange"),
            reverse("operations:lost"),
            reverse("operations:maintenance-start"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("operations:dispatch"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class NormalFlowTests(WebTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def _preview_then_confirm(self, url, payload):
        preview = self.client.post(url, payload)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Konfirmasi")
        idempotency_key = preview.context["idempotency_key"]
        hidden_fields = dict(preview.context["hidden_fields"])
        confirm_payload = {**hidden_fields, "step": "confirm", "idempotency_key": idempotency_key}
        return self.client.post(url, confirm_payload)

    def test_full_dispatch_then_return_flow(self):
        self.client.force_login(self.operator)

        response = self._preview_then_confirm(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-01",
            },
        )
        self.assertRedirects(response, reverse("operations:cylinder-detail", args=["WEB-0001"]))
        self.cylinder.refresh_from_db()
        self.assertEqual(self.cylinder.status, Cylinder.Status.OUT)

        detail = self.client.get(response.url)
        self.assertContains(detail, "OUT")
        self.assertContains(detail, "Pelanggan Web Uji")

        response2 = self._preview_then_confirm(
            reverse("operations:return"),
            {"serial_number": "WEB-0001", "returned_at": "2025-01-05"},
        )
        self.assertRedirects(response2, reverse("operations:cylinder-detail", args=["WEB-0001"]))
        self.cylinder.refresh_from_db()
        self.assertEqual(self.cylinder.status, Cylinder.Status.AVAILABLE)

        detail2 = self.client.get(response2.url)
        self.assertContains(detail2, "AVAILABLE")
        self.assertContains(detail2, "RETURNED")

    def test_search_then_dispatch_via_ui(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("operations:search"), {"serial_number": "WEB-0001"})
        self.assertContains(response, "WEB-0001")
        self.assertContains(response, "AVAILABLE")

    def test_double_click_confirm_does_not_duplicate(self):
        self.client.force_login(self.operator)
        preview = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-01",
            },
        )
        idempotency_key = preview.context["idempotency_key"]
        hidden_fields = dict(preview.context["hidden_fields"])
        confirm_payload = {**hidden_fields, "step": "confirm", "idempotency_key": idempotency_key}

        response1 = self.client.post(reverse("operations:dispatch"), confirm_payload)
        response2 = self.client.post(reverse("operations:dispatch"), confirm_payload)

        self.assertEqual(response1.status_code, 302)
        self.assertEqual(response2.status_code, 302)
        self.assertEqual(Cycle.objects.filter(cylinder=self.cylinder).count(), 1)

    def test_admin_only_reason_required_operation(self):
        self.client.force_login(self.admin)
        response = self._preview_then_confirm(
            reverse("operations:lost"),
            {
                "serial_number": "WEB-0001",
                "occurred_at": "2025-01-01",
                "reason": "Hilang saat pengiriman - demo",
            },
        )
        self.assertRedirects(response, reverse("operations:cylinder-detail", args=["WEB-0001"]))
        self.cylinder.refresh_from_db()
        self.assertEqual(self.cylinder.status, Cylinder.Status.LOST)


class InvalidInputTests(WebTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_future_date_rejected_with_indonesian_message(self):
        self.client.force_login(self.operator)
        future = (date.today() + timedelta(days=5)).isoformat()
        response = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": future,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak boleh di masa depan")
        self.assertFalse(Cycle.objects.exists())

    def test_missing_required_field_shows_indonesian_error(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse("operations:dispatch"),
            {"serial_number": "", "customer": "", "gas_type_code": "", "sent_at": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wajib diisi.")

    def test_reason_required_for_admin_action(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:lost"),
            {"serial_number": "WEB-0001", "occurred_at": "2025-01-01", "reason": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wajib diisi.")

    def test_exchange_same_serial_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:exchange"),
            {
                "old_serial_number": "WEB-0001",
                "new_serial_number": "WEB-0001",
                "exchanged_at": "2025-01-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak boleh sama")

    def test_dispatch_unavailable_cylinder_shows_domain_error(self):
        self.client.force_login(self.operator)
        # Kirim tabung yang sama dua kali (tanpa dikembalikan dulu) - domain error dari F2.
        preview = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-01",
            },
        )
        confirm_payload = {
            **dict(preview.context["hidden_fields"]),
            "step": "confirm",
            "idempotency_key": preview.context["idempotency_key"],
        }
        self.client.post(reverse("operations:dispatch"), confirm_payload)

        preview2 = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-02",
            },
        )
        confirm_payload2 = {
            **dict(preview2.context["hidden_fields"]),
            "step": "confirm",
            "idempotency_key": preview2.context["idempotency_key"],
        }
        response = self.client.post(reverse("operations:dispatch"), confirm_payload2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak dapat dikirim")


class SearchAndPaginationTests(WebTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_unknown_serial_shows_not_found_message(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("operations:search"), {"serial_number": "TIDAK-ADA-0000"}
        )
        self.assertContains(response, "tidak ditemukan")

    def test_empty_query_shows_no_results_without_stale_listing(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("operations:search"))
        self.assertNotContains(response, "WEB-0001")

    def test_customer_filter_with_no_match_shows_empty_message(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("operations:search"), {"customer": "Nama Yang Tidak Ada Sama Sekali"}
        )
        self.assertContains(response, "Tidak ada hasil untuk pencarian ini.")

    def test_server_side_pagination_second_page(self):
        customer = Customer.objects.create(display_name="Pelanggan Paginasi")
        cylinders = [Cylinder.objects.create(serial_number=f"PAG-{i:04d}") for i in range(25)]
        for cylinder in cylinders:
            Cycle.objects.create(
                cylinder=cylinder, customer=customer, status=Cycle.Status.OPEN, sent_at=date.today()
            )

        self.client.force_login(self.viewer)
        page1 = self.client.get(reverse("operations:search"), {"customer": "Pelanggan Paginasi"})
        self.assertEqual(len(page1.context["page_obj"]), 20)

        page2 = self.client.get(
            reverse("operations:search"), {"customer": "Pelanggan Paginasi", "page": 2}
        )
        self.assertEqual(len(page2.context["page_obj"]), 5)
        page1_serials = {c.serial_number for c in page1.context["page_obj"]}
        page2_serials = {c.serial_number for c in page2.context["page_obj"]}
        self.assertEqual(page1_serials.isdisjoint(page2_serials), True)


class TimezoneTests(WebTestCaseMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_common_fixtures()

    def test_lifecycle_event_time_rendered_in_makassar_timezone(self):
        self.client.force_login(self.operator)
        preview = self.client.post(
            reverse("operations:dispatch"),
            {
                "serial_number": "WEB-0001",
                "customer": self.customer.id,
                "gas_type_code": "O2",
                "sent_at": "2025-01-01",
            },
        )
        confirm_payload = {
            **dict(preview.context["hidden_fields"]),
            "step": "confirm",
            "idempotency_key": preview.context["idempotency_key"],
        }
        self.client.post(reverse("operations:dispatch"), confirm_payload)

        event = LifecycleEvent.objects.get(cylinder=self.cylinder)
        self.assertTrue(timezone.is_aware(event.created_at))
        local = timezone.localtime(event.created_at)
        self.assertEqual(local.utcoffset(), timedelta(hours=8), "Asia/Makassar = UTC+8 (WITA)")

        response = self.client.get(reverse("operations:cylinder-detail", args=["WEB-0001"]))
        self.assertContains(response, local.strftime("%d/%m/%Y %H:%M"))
