"""F7: concurrency PostgreSQL lewat layer HTTP (bukan memanggil services langsung - sudah
dibuktikan di operations/tests.py ConcurrencyTests). Mensimulasikan 3-5 pengguna (Operator)
mengklik "Konfirmasi" hampir bersamaan lewat request web sungguhan (Django test Client, thread
terpisah, TransactionTestCase supaya select_for_update() sungguhan berlaku)."""

import threading
from datetime import date

from django.db import connections
from django.test import Client, TransactionTestCase
from django.urls import reverse

from catalog.models import Customer, Cylinder, GasType
from identity.models import Role, User

from .models import Cycle

CONCURRENT_USER_COUNT = 5


class WebConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.operators = [
            User.objects.create_user(username=f"op-conc-{i}", password="x", role=Role.OPERATOR)
            for i in range(CONCURRENT_USER_COUNT)
        ]
        GasType.objects.get_or_create(code=GasType.Code.O2)
        self.customers = [
            Customer.objects.create(display_name=f"Pelanggan Konkuren {i}")
            for i in range(CONCURRENT_USER_COUNT)
        ]
        self.cylinder = Cylinder.objects.create(serial_number="WEB-CONCURRENT-0001")

    def test_n_users_dispatch_same_cylinder_only_one_succeeds(self):
        """N Operator berbeda mencoba mengirim tabung YANG SAMA hampir bersamaan lewat form
        web - hanya satu yang boleh berhasil, sisanya menerima pesan error (bukan crash, bukan
        state korup), dan tidak boleh ada Cycle ganda."""
        start_barrier = threading.Barrier(CONCURRENT_USER_COUNT)
        outcomes = [None] * CONCURRENT_USER_COUNT

        def worker(index):
            client = Client()
            client.force_login(self.operators[index])
            try:
                start_barrier.wait(timeout=5)
                response = client.post(
                    reverse("operations:dispatch"),
                    {
                        "step": "confirm",
                        "idempotency_key": f"web-concurrent-key-{index}",
                        "serial_number": self.cylinder.serial_number,
                        "customer": self.customers[index].id,
                        "gas_type_code": "O2",
                        "sent_at": date(2026, 1, 10).isoformat(),
                    },
                )
                outcomes[index] = response.status_code
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(CONCURRENT_USER_COUNT)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertNotIn(None, outcomes, "setiap thread harus selesai, tidak hang")
        redirects = [code for code in outcomes if code == 302]
        form_re_renders = [code for code in outcomes if code == 200]
        self.assertEqual(len(redirects), 1, f"harus tepat satu sukses, dapat: {outcomes}")
        self.assertEqual(len(form_re_renders), CONCURRENT_USER_COUNT - 1)
        self.assertEqual(
            Cycle.objects.filter(cylinder=self.cylinder).count(),
            1,
            "concurrency tidak boleh menggandakan Cycle",
        )

    def test_n_users_double_click_same_request_only_one_cycle(self):
        """N thread mem-POST payload+idempotency_key yang PERSIS SAMA secara bersamaan (simulasi
        double-click ekstrem/retry jaringan) - harus tetap hanya satu Cycle."""
        start_barrier = threading.Barrier(CONCURRENT_USER_COUNT)
        outcomes = [None] * CONCURRENT_USER_COUNT
        payload = {
            "step": "confirm",
            "idempotency_key": "same-key-all-threads",
            "serial_number": self.cylinder.serial_number,
            "customer": self.customers[0].id,
            "gas_type_code": "O2",
            "sent_at": date(2026, 1, 10).isoformat(),
        }

        def worker(index):
            client = Client()
            client.force_login(self.operators[0])
            try:
                start_barrier.wait(timeout=5)
                response = client.post(reverse("operations:dispatch"), payload)
                outcomes[index] = response.status_code
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(CONCURRENT_USER_COUNT)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertNotIn(None, outcomes)
        self.assertTrue(all(code == 302 for code in outcomes), f"outcomes: {outcomes}")
        self.assertEqual(Cycle.objects.filter(cylinder=self.cylinder).count(), 1)
