"""F7: benchmark performa lokal dengan data sintetis - HANYA mengukur, TIDAK mengklaim
kapasitas (5 juta event/5 tahun dari requirements lama) hanya dari volume kecil di sini. Angka
adalah timing in-process (Django test Client dalam proses yang sama, bukan request jaringan
sungguhan) - dicatat sebagai batas pengukuran, bukan angka produksi. Target p95 (cari <=1s,
command <=2s) BELUM disahkan - dicatat sebagai target, bukan lulus/gagal, sampai pemilik
memverifikasi di lingkungan mendekati produksi (lihat requirements.md lama MIG-N01/N02)."""

import json
import random
import time
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import reverse

from catalog.models import Customer, Cylinder, GasType
from identity.models import Role
from operations import services
from operations.models import Cycle, LifecycleEvent

RESULT_PATH = Path(settings.BASE_DIR) / "docs" / "reports" / "f7-performance.json"
PREFIX = "PERF-"

User = get_user_model()


def _percentile(samples, pct):
    ordered = sorted(samples)
    if not ordered:
        return None
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


class Command(BaseCommand):
    help = (
        "Bangun data sintetis lalu ukur latency pencarian/daftar/mutasi - lihat "
        "docs/reports/F7.md untuk interpretasi. Data sintetis dibersihkan otomatis di akhir "
        "kecuali --keep-data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--cylinders", type=int, default=3000)
        parser.add_argument("--customers", type=int, default=300)
        parser.add_argument("--cycles", type=int, default=20000)
        parser.add_argument("--samples", type=int, default=30)
        parser.add_argument("--keep-data", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("Membangun data sintetis...")
        cylinders, customers = self._build_synthetic_data(
            options["cylinders"], options["customers"], options["cycles"]
        )

        actor = User.objects.filter(role=Role.OPERATOR).first() or User.objects.create_user(
            username=f"{PREFIX}bench-operator", password="x", role=Role.OPERATOR
        )
        client = Client()
        client.force_login(actor)

        results = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "synthetic_volume": {
                "cylinders": options["cylinders"],
                "customers": options["customers"],
                "cycles": options["cycles"],
                "lifecycle_events": options["cycles"] * 2,
            },
            "samples_per_measurement": options["samples"],
            "note": (
                "Timing in-process (Django test Client, satu proses) - BUKAN latency jaringan "
                "produksi. Target p95 (cari<=1s, command<=2s) belum disahkan, dicatat sebagai "
                "referensi, bukan kelulusan."
            ),
            "measurements": {},
        }

        results["measurements"]["search_exact_serial"] = self._measure(
            options["samples"],
            lambda: client.get(
                reverse("operations:search"), {"serial_number": random.choice(cylinders)}
            ),
        )
        results["measurements"]["search_by_customer_listing"] = self._measure(
            options["samples"],
            lambda: client.get(
                reverse("operations:search"), {"customer": random.choice(customers)}
            ),
        )
        results["measurements"]["usage_log_listing"] = self._measure(
            options["samples"], lambda: client.get(reverse("operations:usage-log"))
        )
        cylinder_detail_serial = cylinders[0]
        results["measurements"]["cylinder_detail"] = self._measure(
            options["samples"],
            lambda: client.get(
                reverse("operations:cylinder-detail", args=[cylinder_detail_serial])
            ),
        )
        results["measurements"]["mutation_dispatch_and_return"] = self._measure_mutation(
            options["samples"], actor
        )

        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        for name, stats in results["measurements"].items():
            self.stdout.write(
                f"{name}: p50={stats['p50_ms']}ms p95={stats['p95_ms']}ms max={stats['max_ms']}ms"
            )
        self.stdout.write(self.style.SUCCESS(f"Hasil -> {RESULT_PATH}"))

        if not options["keep_data"]:
            self.stdout.write("Membersihkan data sintetis...")
            self._cleanup()
            self.stdout.write(self.style.SUCCESS("Data sintetis dibersihkan."))
        else:
            self.stdout.write(self.style.WARNING("--keep-data: data sintetis TIDAK dihapus."))

    def _measure(self, samples, fn):
        durations = []
        for _ in range(samples):
            start = time.perf_counter()
            fn()
            durations.append((time.perf_counter() - start) * 1000)
        return {
            "p50_ms": round(_percentile(durations, 50), 1),
            "p95_ms": round(_percentile(durations, 95), 1),
            "max_ms": round(max(durations), 1),
            "min_ms": round(min(durations), 1),
        }

    def _measure_mutation(self, samples, actor):
        customer = Customer.objects.filter(display_name__startswith=PREFIX).first()
        gas = GasType.objects.get(code=GasType.Code.O2)
        durations = []
        for i in range(samples):
            suffix = f"{i}-{random.randint(0, 999999)}"
            cylinder = Cylinder.objects.create(serial_number=f"{PREFIX}MUT-{suffix}")
            start = time.perf_counter()
            services.dispatch_cylinder(
                actor=actor,
                serial_number=cylinder.serial_number,
                customer_id=customer.id,
                gas_type_code=gas.code,
                sent_at=date.today(),
                idempotency_key=f"{PREFIX}bench-dispatch-{i}-{random.randint(0, 999999)}",
            )
            services.return_cylinder(
                actor=actor,
                serial_number=cylinder.serial_number,
                returned_at=date.today(),
                idempotency_key=f"{PREFIX}bench-return-{i}-{random.randint(0, 999999)}",
            )
            durations.append((time.perf_counter() - start) * 1000)
        return {
            "p50_ms": round(_percentile(durations, 50), 1),
            "p95_ms": round(_percentile(durations, 95), 1),
            "max_ms": round(max(durations), 1),
            "min_ms": round(min(durations), 1),
            "note": "dispatch+return berpasangan (2 mutasi) per sampel",
        }

    def _build_synthetic_data(self, n_cylinders, n_customers, n_cycles):
        gas = GasType.objects.get_or_create(code=GasType.Code.O2)[0]

        existing = Cylinder.objects.filter(serial_number__startswith=PREFIX).count()
        if existing >= n_cylinders:
            cylinder_serials = list(
                Cylinder.objects.filter(serial_number__startswith=PREFIX).values_list(
                    "serial_number", flat=True
                )[:n_cylinders]
            )
            customer_names = list(
                Customer.objects.filter(display_name__startswith=PREFIX).values_list(
                    "display_name", flat=True
                )[:n_customers]
            )
            return cylinder_serials, customer_names

        cylinders = Cylinder.objects.bulk_create(
            [Cylinder(serial_number=f"{PREFIX}{i:07d}") for i in range(n_cylinders)],
            batch_size=1000,
        )
        customers = Customer.objects.bulk_create(
            [Customer(display_name=f"{PREFIX}Pelanggan {i:05d}") for i in range(n_customers)],
            batch_size=1000,
        )

        today = date.today()
        cycles = []
        for _i in range(n_cycles):
            sent = today - timedelta(days=random.randint(1, 1800))
            returned = sent + timedelta(days=random.randint(1, 30))
            cycles.append(
                Cycle(
                    cylinder=random.choice(cylinders),
                    customer=random.choice(customers),
                    gas_type_at_dispatch=gas,
                    status=Cycle.Status.CLOSED,
                    sent_at=sent,
                    returned_at=returned,
                    close_reason=Cycle.CloseReason.RETURNED,
                )
            )
        created_cycles = Cycle.objects.bulk_create(cycles, batch_size=1000)

        events = []
        for cycle in created_cycles:
            events.append(
                LifecycleEvent(
                    cylinder=cycle.cylinder,
                    cycle=cycle,
                    event_type=LifecycleEvent.EventType.DISPATCHED,
                    occurred_at=cycle.sent_at,
                    source=LifecycleEvent.Source.SYSTEM,
                )
            )
            events.append(
                LifecycleEvent(
                    cylinder=cycle.cylinder,
                    cycle=cycle,
                    event_type=LifecycleEvent.EventType.RETURNED,
                    occurred_at=cycle.returned_at,
                    source=LifecycleEvent.Source.SYSTEM,
                )
            )
        LifecycleEvent.objects.bulk_create(events, batch_size=2000)

        return [c.serial_number for c in cylinders], [c.display_name for c in customers]

    def _cleanup(self):
        # User pembuat benchmark TIDAK dihapus - dilindungi FK PROTECT dari AuditLog/
        # IdempotencyRecord hasil mutasi dispatch/return sungguhan selama benchmark (konsisten
        # prinsip append-only F2), sama seperti data smoke-test F5.
        LifecycleEvent.objects.filter(cylinder__serial_number__startswith=PREFIX).delete()
        Cycle.objects.filter(cylinder__serial_number__startswith=PREFIX).delete()
        Cylinder.objects.filter(serial_number__startswith=PREFIX).delete()
        Customer.objects.filter(display_name__startswith=PREFIX).delete()
