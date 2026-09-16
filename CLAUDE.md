# CLAUDE.md - gas-wayan-python

Aturan tetap untuk Claude Code saat bekerja di proyek ini. Proyek ini adalah penggantian stack
(TypeScript -> Python) dari sistem operasional tabung Gas Wayan. Baca file ini sebelum memulai
fase mana pun.

## Apa proyek ini

Aplikasi web + bot Telegram untuk menggantikan workflow `SERI TABUNG.xlsm`: cari tabung/relasi,
kirim, kembali, tukar, hilang, maintenance, pensiun, koreksi, histori lifecycle, impor workbook
(raw -> staging -> review -> publish), dashboard/laporan, dan audit trail. Lihat
[docs/phase-plan.md](docs/phase-plan.md) untuk urutan fase F0-F8.

**Status implementasi saat ini: F7 (cakupan web) selesai** (F1: login, role, health check; F2:
model domain `catalog`/`operations`/`audit` dan layanan kirim/kembali/tukar/hilang/maintenance/
pensiun/reversal - lihat `operations/services.py`; F3: importer raw/staging read-only dari
`SERI TABUNG.xlsm` - lihat `imports/importer.py`; F4: review+publish per kelompok tabung - lihat
`imports/publisher.py`; F5: layar operasional web - cari, kirim/kembali, fungsi Admin, riwayat,
log penggunaan - lihat `operations/views.py`/`operations/forms.py`, prefix URL `/operasi/`; F7:
UAT/keamanan/performa/backup untuk cakupan WEB - lihat `docs/reports/F7.md`, rate limiting login
`identity/throttle.py`, HSTS `config/settings/prod.py`).

**F6 (bot Telegram) BELUM DIKERJAKAN - SENGAJA DILOMPATI sementara** atas persetujuan eksplisit
pemilik proyek saat F7 dimulai ("F7 web-only dulu"). F7 karena itu HANYA mencakup web; cakupan
bot (end-to-end web/bot, load test bot) masih `BLOCKED` dan perlu disusulkan setelah F6 selesai,
sebelum F8 (deployment produksi) dimulai. Jangan berasumsi bot/F6/F8 sudah ada.

Layar F5 (`operations/views.py`) HANYA memanggil `operations.services.*` untuk mutasi - pola
form->preview->konfirmasi dengan `idempotency_key` (UUID) dibuat sekali saat preview dan
dikirim ulang sebagai hidden field, supaya double-click tombol konfirmasi otomatis aman lewat
mekanisme idempotency F2. Jangan menambah view baru yang memanggil `.save()` langsung pada
`Cycle`/`Cylinder` - selalu lewat service, dan selalu bungkus dengan `identity.permissions
.role_required` sesuai tabel role di atas.

Importer F3 HANYA menulis `imports.RawRow`/`imports.StagingRow` - tidak pernah menulis
`catalog`/`operations` (master/lifecycle). Parser tanggal resmi (`imports/parsing.py`,
`F3-PARSER-v1`) masih berstatus PROPOSAL menunggu konfirmasi pemilik proyek (MIG-P06). Laporan
detail importer (data asli per baris) hanya tersimpan lokal di `docs/reports/f3-local/`
(di-gitignore) - jangan pernah menempelkan isinya ke chat/dokumen yang masuk Git.

Publish F4 (`imports/publisher.py`) HANYA mempublish kelompok (per tabung) yang seluruh
barisnya `review_status=READY` dan tanpa konflik kronologi - kebijakan migrasi yang masih
`PENDING` (B1 gas, B2 tanggal kembali, B3 konflik siklus, lihat
`docs/migration-decisions-pending.md`) SENGAJA tetap memblokir mayoritas data sampai
dikonfirmasi. Jangan melonggarkan syarat ini tanpa keputusan pemilik proyek eksplisit. Satu-
satunya cara mengecualikan baris staging dari publish adalah `imports.publisher.exclude_staging_row`
(role ADMIN, alasan wajib, lewat Django Admin aksi "Kecualikan dari publish") - jangan pernah
mengubah `StagingRow.publish_outcome` langsung lewat `.save()`.

Cara mengubah state tabung/siklus: SELALU lewat fungsi `operations.services.*`
(`dispatch_cylinder`, `return_cylinder`, `exchange_cylinder`, `mark_lost`, `start_maintenance`,
`complete_maintenance`, `retire_cylinder`, `reverse_dispatch`). Jangan pernah mengubah
`Cylinder.status`/`Cycle.status` langsung lewat `.save()` di kode baru - itu akan melewati
audit log, outbox, idempotency, dan pengecekan role. Django Admin untuk `Cycle`/`LifecycleEvent`/
`AuditLog`/`OutboxEvent`/`IdempotencyRecord` sengaja read-only (lihat `operations/admin.py`,
`audit/admin.py`).

## Stack (versi dipin dan diverifikasi kompatibel per 16 September 2026)

- Python **3.13.15** (dipilih daripada 3.14.7 yang baru rilis - lebih matang, cakupan dukungan
  pustaka pihak ketiga lebih luas; Django 5.2 mendukung keduanya)
- Django **5.2.17 LTS** (dukungan extended sampai April 2028; requires Python >=3.10 - lihat
  [docs/decisions.md](docs/decisions.md) ADR-P011)
- `psycopg[binary]` **3.3.5** (driver PostgreSQL resmi yang direkomendasikan Django saat ini)
- `django-environ` **0.14.0** (baca `.env`, parse `DATABASE_URL`)
- `gunicorn` **26.2.0** (WSGI server untuk image Linux/deployment Railway)
- `whitenoise` **6.12.0** (static files Django di deployment container)
- `ruff` **0.16.7** (lint + format, satu tool, dipakai lewat `pyproject.toml`)
- `pip-tools` **7.6.1** (compile `requirements*.in` -> `requirements*.txt` dengan hash)
- PostgreSQL **18.6-alpine** (image Docker; port host `55432`, lihat `docker-compose.yml`)
- Django Templates + CSS responsif (360px - desktop), bukan SPA terpisah
- Worker Python untuk inbox/outbox Telegram (mekanisme antrean masih `PENDING` - lihat MIG-P01 di
  [docs/migration-decisions-pending.md](docs/migration-decisions-pending.md); belum dibangun,
  menyusul F6)
- Telegram Bot API melalui webhook dengan secret header terverifikasi (F6)

Dependency dikunci di `requirements.in`/`requirements.txt` (runtime) dan
`requirements-dev.in`/`requirements-dev.txt` (lint/dev), dengan hash (`--generate-hashes
--allow-unsafe`). Jangan edit `requirements*.txt` manual - jalankan
`scripts/compile_requirements.ps1` setelah mengubah file `.in`. Jangan menambah dependency tanpa
mencatat versi persis di sini.

## Batas perubahan (JANGAN DILANGGAR)

- Jangan mengubah `apps/`, `packages/`, `.env`, atau `compose.yaml` milik proyek TypeScript lama
  (`../Gas Wayan/`). Proyek itu tetap ada sebagai referensi historis, bukan basis kode aktif.
- `../SERI TABUNG.xlsm` (relatif dari root proyek ini) selalu read-only. Jangan pernah menyimpan
  ulang, menjalankan macro, atau menulis ke file itu. Semua akses memakai pembaca read-only
  (misalnya `openpyxl` mode read-only) dan checksum SHA-256 diverifikasi sebelum dipakai:
  `D96FC4E7366BFC9B38CBD2BEB6985CAB361BCA9E1D36CFAED5DD1FFDDFA33B81`.
- Jangan menyalin `.env` lama atau menjalankan Docker Compose lama untuk proyek ini. Proyek Python
  punya environment, database, dan Compose sendiri yang terpisah dari proyek lama.
- Jangan mempublikasikan data migrasi ke tabel operasional tanpa melalui staging -> review ->
  publish. Dry-run tidak boleh menulis master/lifecycle.
- Jangan menandai fase ACCEPTED tanpa demo dan bukti tes yang dapat dibuka pemilik proyek
  (lihat `progress.md` dan `handoff.md` di root proyek ini, tautan di bagian Rujukan docs).
- Jangan menganggap keputusan berstatus `PENDING` sebagai final di kode; lihat
  [docs/migration-decisions-pending.md](docs/migration-decisions-pending.md).

## Keputusan bisnis yang dipertahankan dari fondasi lama

Sumber: `../Gas Wayan/docs/requirements.md` (status `BASELINE - CONFIRMED`, 14 September 2026).
Ini tetap berlaku kecuali ADR baru secara eksplisit menggantikannya:

- Satu organisasi, satu gudang; seluruh tabung milik Gas Wayan; tidak ada multi-cabang.
- Satu pengiriman = tepat satu pelanggan, satu tanggal, satu tabung. Satu tabung tidak boleh
  punya lebih dari satu siklus aktif pada saat yang sama.
- Role: `ADMIN` (penuh, termasuk koreksi/reversal/merge), `OPERATOR` (cari/kirim/kembali/lihat
  histori), `VIEWER` (read-only). Ditegakkan di server, bukan hanya UI.
- Status tabung: `AVAILABLE`, `OUT`, `LOST`, `MAINTENANCE`, `RETIRED`. `RETURNED`/`EXCHANGED`
  adalah event penutup siklus, bukan status permanen.
- Jenis gas resmi hanya `O2`, `AR`, `C2H2`, `N2`, `CO2`. Kode legacy lain (BBS, MR, TOB, SA, TIRA,
  UHP, ABG, SMB, TR, dll.) bukan jenis gas resmi dan tidak ditebak otomatis -> `NEEDS_REVIEW`.
- `K`, `KEMBALI`, `SDH KEMBALI` dipetakan ke event `RETURNED`; nilai asli tetap disimpan.
- Tidak ada hard-delete transaksi. Koreksi memakai reversal/void + alasan + actor + audit log.
- Idempotency key wajib pada command mutasi (web dan Telegram); retry harus aman.
- UUID sebagai primary key internal; `Nomor` Excel adalah legacy reference non-unik, bukan PK.
- Timestamp teknis UTC; tanggal bisnis tampil `DD/MM/YYYY` di zona `Asia/Makassar`.
- Audit log wajib untuk seluruh mutasi penting; retensi 1 tahun; tidak menghapus histori bisnis
  yang masih wajib dipertahankan.
- Di luar ruang lingkup versi awal: invoicing/harga/pajak/akuntansi, GPS/rute/kendaraan, portal
  pelanggan eksternal, aplikasi native, mode offline, multi-tenant, integrasi ERP/marketplace/IoT.

Detail lengkap dan register keputusan (DEC-001..DEC-016) ada di
`../Gas Wayan/docs/requirements.md`.

## Perintah verifikasi

Diuji dari checkout bersih pada 16 September 2026 (F1) - lihat `docs/reports/F1.md` untuk bukti.
Jalankan dari root `gas-wayan-python/` dengan venv aktif (`.\.venv\Scripts\Activate.ps1`) kecuali
disebutkan lain. Setup lengkap dari nol: lihat `README.md`.

| Kebutuhan | Perintah |
| --- | --- |
| Infrastruktur (PostgreSQL) | `docker compose up -d postgres` |
| Instal dependency (hash-verified) | `pip install --require-hashes -r requirements.txt -r requirements-dev.txt` |
| Migrasi | `python manage.py migrate` |
| Buat Admin (interaktif, aman) | `python manage.py createsuperuser` |
| Jalankan aplikasi | `python manage.py runserver` (buka `http://127.0.0.1:8000/`) |
| Lint | `ruff check .` |
| Format (cek) | `ruff format --check .` |
| Test (PostgreSQL nyata) | `python manage.py test --settings=config.settings.test` |
| System check | `python manage.py check` |
| Cek migrasi hilang | `python manage.py makemigrations --check --dry-run` |
| Import workbook (raw+staging, dry-run) | `python manage.py import_workbook --dry-run` |
| Import workbook (tersimpan, idempotent) | `python manage.py import_workbook` |
| Laporan F3 (agregat aman + detail lokal) | `python manage.py import_report` |
| Publish staging per kelompok (F4, resumable) | `python manage.py publish_staging --actor-username <user>` |
| Rekonsiliasi F4 (raw=published+pending+excluded) | `python manage.py reconcile_report` |
| Checklist keamanan deploy (butuh env sementara) | `python manage.py check --deploy --settings=config.settings.prod` |
| Benchmark performa (data sintetis, auto-cleanup) | `python manage.py perf_benchmark --settings=config.settings.test` |
| CI (belum pernah jalan di GitHub - belum ada remote) | `.github/workflows/ci.yml`, langkahnya sudah diverifikasi identik secara lokal |

Health check publik (tanpa auth): `GET /health/` -> `{"status": "ok", "database": "ok"}`.
Halaman butuh login: `/` (dashboard), `/admin-only/` (contoh khusus role `ADMIN`, demo penolakan
403 server-side), `/admin/` (Django Admin).

## Rujukan docs

Proyek lama (`../Gas Wayan/`), read-only, referensi historis:

- `../Gas Wayan/README.md`
- `../Gas Wayan/docs/requirements.md`
- `../Gas Wayan/docs/workbook-audit.md`
- `../Gas Wayan/docs/decisions.md` (ADR-001..ADR-014, stack TypeScript, disuperseded sebagian
  oleh [docs/decisions.md](docs/decisions.md) di proyek ini)
- `../Gas Wayan/docs/architecture.md`, `../Gas Wayan/docs/glossary.md`
- `../Gas Wayan/output/pdf/Panduan_dan_Prompt_Claude_Code.md` (bagian 05-08: rencana fase,
  cara melihat progres)

Proyek ini (`gas-wayan-python/`):

- [docs/phase-plan.md](docs/phase-plan.md) - F0-F8, exit gate per fase
- [docs/decisions.md](docs/decisions.md) - ADR penggantian stack dan ADR baru proyek Python
- [docs/migration-decisions-pending.md](docs/migration-decisions-pending.md) - keputusan migrasi
  yang masih terbuka
- `progress.md` (root) - status tiap fase
- `handoff.md` (root) - posisi kerja terakhir dan next action

## Cara kerja per fase

Satu fase per sesi kerja. Minta checkpoint di setiap sublangkah yang menghasilkan artefak/tes
bermakna. Jangan mulai fase berikutnya sebelum pemilik proyek menerima demo fase saat ini
(status `ACCEPTED` di `progress.md`). Status yang valid: `TODO -> IN_PROGRESS ->
READY_FOR_REVIEW -> ACCEPTED`, atau `BLOCKED` dengan alasan, dampak, dan siapa yang perlu
memutuskan.
