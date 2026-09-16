# Catatan Keputusan Arsitektur - gas-wayan-python

Status: `DRAFT - BELUM DIIMPLEMENTASIKAN`
Tanggal: 16 September 2026

Dokumen ini mencatat keputusan arsitektur untuk proyek Python. Proyek TypeScript lama
(`../Gas Wayan/`) tetap ada sebagai referensi; ADR lamanya (`../Gas Wayan/docs/decisions.md`,
ADR-001..ADR-014) tidak dihapus atau diedit. ADR di bawah menggantikan sebagian ADR lama dan
mempertahankan sebagian lainnya secara setara pada stack Python.

## Register

| ADR | Keputusan | Status | Menggantikan ADR lama |
| --- | --- | --- | --- |
| ADR-P001 | Ganti stack TypeScript (Next.js/NestJS/Prisma) ke Python (Django) | Accepted | ADR-002, ADR-004 (sebagian) |
| ADR-P002 | Django modular monolith dengan Django Templates | Accepted | ADR-001, ADR-002 |
| ADR-P003 | PostgreSQL tetap sebagai source of truth | Accepted (setara) | ADR-003 |
| ADR-P004 | Django ORM + migration, SQL manual untuk constraint kompleks | Accepted | ADR-004 |
| ADR-P005 | Mekanisme antrean worker Python untuk Telegram, Redis opsional | Proposed - PENDING pilihan teknologi | ADR-005 |
| ADR-P006 | Invariant dijaga database (transaksi, lock, constraint) | Accepted (setara) | ADR-006 |
| ADR-P007 | Idempotency durable di PostgreSQL | Accepted (setara) | ADR-007 |
| ADR-P008 | Append-oriented lifecycle, reversal, audit | Accepted (setara) | ADR-008 |
| ADR-P009 | Telegram webhook melalui durable inbox/outbox | Accepted (setara) | ADR-009 |
| ADR-P010 | Django Templates server-rendered, bukan REST+SPA terpisah | Accepted | ADR-010 |
| ADR-P011 | Runtime dan versi Python dipin saat F1 | Resolved (F1) untuk inti; openpyxl/bot Telegram menyusul F3/F6 | ADR-011 |
| ADR-P012 | Satu database untuk seluruh modul monolith | Accepted (setara) | ADR-012 |
| ADR-P013 | UUID internal + sequence PostgreSQL untuk nomor dokumen | Accepted (setara) | ADR-013 |
| ADR-P014 | UTC untuk timestamp, Asia/Makassar untuk tampilan | Accepted (setara) | ADR-014 |

## ADR-P001: Penggantian stack TypeScript ke Python

**Konteks:** Fondasi TypeScript (Next.js + NestJS + Prisma) sudah di-scaffold di `../Gas Wayan/`
(ADR-001..ADR-014 lama, status Accepted). Permintaan terbaru pemilik proyek mengganti stack
implementasi menjadi Python, dengan Django sebagai web framework, Django Templates sebagai UI,
PostgreSQL tetap dipertahankan, ditambah worker Python dan Telegram Bot API. Keputusan bisnis
(requirements.md lama, `BASELINE - CONFIRMED`) tidak diminta berubah.

**Keputusan:** Proyek baru `gas-wayan-python/` dibangun dari nol dengan Django. Proyek TypeScript
lama tidak dihapus, tidak dijalankan, dan tidak menjadi dependency proyek Python. Tidak ada
periode dual-stack produksi; TypeScript lama adalah referensi arsitektur dan dokumentasi domain,
bukan basis kode yang di-porting baris-per-baris.

**Konsekuensi:** Pekerjaan scaffold TypeScript yang sudah ada (kode `apps/`, `packages/`) menjadi
tidak terpakai untuk implementasi, tetapi tetap berguna sebagai spesifikasi perilaku yang sudah
dipikirkan (domain model, alur transaksi, aturan role). Seluruh keputusan teknis yang spesifik ke
Node.js/Prisma/Next.js (ADR-002, ADR-004, ADR-011 lama) perlu padanan baru di Python; keputusan
yang independen dari bahasa (PostgreSQL sebagai source of truth, UUID, append-only lifecycle,
idempotency, audit, UTC/Asia-Makassar) dipertahankan tanpa perubahan makna.

## ADR-P002: Django modular monolith dengan Django Templates

**Konteks:** Tim dan beban awal kecil (3-5 pengguna simultan); operasi lifecycle membutuhkan
transaksi lintas tabung/siklus/audit/outbox dalam satu proses. Kebutuhan sebelumnya memisahkan
web (Next.js) dan API (NestJS) demi kontrak bersama web+Telegram.

**Keputusan:** Satu aplikasi Django dibagi menjadi modul identity, catalog (pelanggan/alias,
jenis gas, tabung), operations (dispatch/return/exchange/lost/maintenance/retired/reversal),
imports (raw/staging/review/publish), reporting, telegram (adapter + worker), dan audit/health.
UI memakai Django Templates dengan CSS responsif, dirender server-side. Web dan Telegram
memanggil lapisan layanan domain Python yang sama secara langsung (in-process), tidak melalui
hop HTTP REST terpisah seperti pada ADR-002 lama.

**Konsekuensi:** Tidak perlu menjaga kontrak REST terversi antara dua proses terpisah; lebih
sedikit moving parts untuk tim kecil. Batas modul harus tetap ditegakkan lewat struktur app
Django dan konvensi import (layanan domain sebagai satu-satunya pintu mutasi), karena tidak ada
process isolation. Django Admin dapat dipakai untuk pengelolaan awal, tetapi tidak untuk mutasi
tabel event lifecycle (harus lewat layanan domain, bukan CRUD admin bebas).

## ADR-P003: PostgreSQL tetap sebagai source of truth

**Konteks:** Sama seperti ADR-003 lama: invariant lifecycle, histori, audit, dan target 5 juta
event dalam 5 tahun membutuhkan transaksi dan constraint relational.

**Keputusan:** PostgreSQL menyimpan seluruh state bisnis, idempotency record, inbox/outbox
Telegram. Tidak ada penyimpanan state bisnis yang hanya ada di memori proses atau di Redis.
Versi PostgreSQL dipin saat F1 dan diverifikasi ulang terhadap dukungan resmi pada saat itu
(bukan diasumsikan dari dokumen lama, karena rilis dapat berubah sejak 14 September 2026).

**Konsekuensi:** Sama seperti ADR-003 lama - ketersediaan mutasi mengikuti PostgreSQL; backup,
monitoring lock, indexing, dan restore drill menjadi kewajiban operasional (lihat F7, F8 di
`docs/phase-plan.md`).

## ADR-P004: Django ORM + migration, SQL manual untuk constraint kompleks

**Konteks:** Padanan Python untuk ADR-004 lama (Prisma + SQL manual). Django punya ORM dan
sistem migration bawaan dengan dukungan matang untuk PostgreSQL.

**Keputusan:** Gunakan Django ORM dan Django migrations untuk skema dan CRUD standar. Untuk
partial unique index, expression index, check constraint kompleks, atau fitur PostgreSQL yang
tidak dapat dinyatakan stabil lewat Django model API, tulis migration data (`RunSQL`) manual yang
di-commit dan diuji.

**Konsekuensi:** Sama seperti versi Prisma-nya - Django ORM tidak dijadikan pengganti desain
relational. Drift dicegah dengan migration test, integration test constraint di PostgreSQL nyata,
dan `makemigrations --check` di CI.

## ADR-P005: Mekanisme antrean worker Python (PENDING)

**Konteks:** Import, laporan, dan Telegram inbox/outbox butuh retry dan backpressure. ADR-005
lama memilih Redis + BullMQ (ekosistem Node.js), tidak berlaku langsung di Python. Panduan
arsitektur Python (`../Gas Wayan/output/pdf/Panduan_dan_Prompt_Claude_Code.md`, bagian 03)
menyarankan antrean berbasis PostgreSQL cukup untuk tahap awal, dengan Redis sebagai opsi jika
diperlukan nanti.

**Keputusan sementara:** worker Python memproses outbox Telegram memakai tabel PostgreSQL
(polling terjadwal/`LISTEN`/`NOTIFY`) sebagai baseline, tanpa Redis. Pilihan pustaka konkret
(mis. Celery+Redis/RQ vs custom polling worker vs `django-q`) belum diputuskan.

**Status:** `PENDING` - dikunci di F1 saat fondasi dibuat. Lihat
`docs/migration-decisions-pending.md` butir antrean/worker.

**Konsekuensi sementara:** Kehilangan komponen antrean (jika Redis dipakai nanti) tidak boleh
menghilangkan transaksi bisnis; outbox PostgreSQL tetap sumber kebenaran pekerjaan tertunda,
sama seperti prinsip ADR-005 lama.

## ADR-P006 - ADR-P010: Padanan langsung dari ADR lama, tanpa perubahan prinsip

Keputusan berikut dipertahankan dengan makna yang sama seperti versi TypeScript-nya
(`../Gas Wayan/docs/decisions.md`), hanya berpindah ke idiom Django/PostgreSQL:

- **ADR-P006 (Invariant dijaga database):** transaksi (`transaction.atomic`),
  `select_for_update`, urutan lock deterministik antar tabung saat tukar, foreign key, check
  constraint, dan partial unique index untuk satu cycle aktif per tabung. Konflik jadi HTTP 409
  eksplisit. Padanan ADR-006 lama.
- **ADR-P007 (Idempotency durable):** idempotency record di PostgreSQL berdasarkan scope + key +
  hash payload; Telegram `update_id` unik; setiap handler worker idempotent. Padanan ADR-007
  lama.
- **ADR-P008 (Histori tidak dihapus):** dokumen committed tidak dihapus fisik; koreksi memakai
  void/reversal dengan alasan dan referensi; lifecycle event append-oriented. Padanan ADR-008
  lama.
- **ADR-P009 (Telegram durable inbox/outbox):** webhook memverifikasi secret header, menyimpan
  update unik dan outbox di PostgreSQL sebelum membalas cepat; worker memproses dan mengirim
  balasan dengan retry; hanya private chat dan numeric Telegram user ID yang disetujui. Padanan
  ADR-009 lama.
- **ADR-P010 (Server-rendered, bukan REST+SPA):** karena web dan Telegram sama-sama memanggil
  layanan domain Python langsung (ADR-P002), tidak ada kebutuhan kontrak REST bersama seperti
  `packages/contracts` di proyek lama. Jika kebutuhan API eksternal muncul nanti, itu jadi ADR
  baru, bukan default arsitektur ini. Menggantikan premis ADR-010 lama (REST + shared contracts)
  karena penyebabnya (dua proses terpisah) tidak lagi berlaku pada modular monolith Django.

## ADR-P011: Runtime dan versi (RESOLVED di F1 untuk inti; openpyxl/bot Telegram menyusul)

**Konteks:** ADR-011 lama memin Node.js/pnpm/Next.js/NestJS/Prisma/PostgreSQL/Redis dengan versi
persis per 14 September 2026. Proyek Python butuh padanan: versi Python, Django, driver
PostgreSQL (`psycopg`), `openpyxl`, pustaka HTTP/bot Telegram, dan PostgreSQL itu sendiri.

**Keputusan:** versi persis diverifikasi ulang dari registry resmi (PyPI, djangoproject.com,
postgresql.org) pada 16 September 2026 saat F1 dikerjakan, bukan diasumsikan dari tanggal dokumen
ini. Dependency dikunci lewat `pip-tools` (`requirements.in`/`requirements-dev.in` ->
`requirements*.txt` dengan `--generate-hashes --allow-unsafe`). Image PostgreSQL Compose baru
memakai tag minor/patch eksplisit (`postgres:18.6-alpine`), bukan `latest`.

**Versi terkunci di F1:**

| Komponen | Versi | Alasan |
| --- | --- | --- |
| Python | 3.13.15 | Django 5.2 mendukung 3.10-3.14; 3.13 dipilih daripada 3.14.7 (baru rilis) untuk kematangan ekosistem pustaka pihak ketiga |
| Django | 5.2.17 (LTS) | Extended support sampai April 2028 (djangoproject.com/download); requires Python >=3.10 |
| psycopg | 3.3.5 (`[binary]`) | Driver PostgreSQL resmi yang direkomendasikan Django saat ini; extra `binary` cukup untuk dev/F1, evaluasi `[c]` untuk produksi di F8 |
| django-environ | 0.14.0 | Parsing `.env`/`DATABASE_URL` |
| ruff | 0.16.7 | Lint + format satu tool |
| pip-tools | 7.6.1 | Compile lock file |
| PostgreSQL | 18.6-alpine (image Docker) | Rilis stabil terbaru per Agustus 2026; PostgreSQL 19 masih beta, tidak dipakai |

`openpyxl` (pembaca XLSM) dan pustaka HTTP/bot Telegram belum dipin - baru relevan di F3 dan F6;
akan diverifikasi ulang versi resminya saat fase itu dimulai, bukan diasumsikan sekarang.

**Status:** `RESOLVED (F1)` untuk baris di atas. Sisanya (openpyxl, pustaka Telegram) dicatat
sebagai item terbuka baru di `docs/migration-decisions-pending.md` untuk F3/F6.

## ADR-P012 - ADR-P014: Padanan langsung, tanpa perubahan prinsip

- **ADR-P012 (Satu database untuk monolith):** semua modul Django memakai satu database dan
  schema PostgreSQL; ownership tabel tetap logical lewat app boundary dan layanan domain. Padanan
  ADR-012 lama.
- **ADR-P013 (Strategi identifier):** UUID sebagai primary key internal, unique text untuk nomor
  tabung, PostgreSQL sequence untuk nomor dokumen. `Nomor` Excel tetap traceability non-unik.
  Padanan ADR-013 lama.
- **ADR-P014 (Waktu dan tanggal):** timestamp teknis UTC (`timestamptz`), tanggal bisnis
  PostgreSQL `date`, tampilan `DD/MM/YYYY` di `Asia/Makassar`. Parser import tidak menebak nilai
  ambigu. Padanan ADR-014 lama.
