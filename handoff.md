# Handoff - gas-wayan-python

Tanggal: 16 September 2026

## Posisi terakhir

F7 (UAT, keamanan, performa, pemulihan) berstatus `READY_FOR_REVIEW` **untuk cakupan WEB saja**.
F6 (bot Telegram) belum dikerjakan - ditanyakan eksplisit ke pemilik proyek di awal sesi ini
("F6 belum dikerjakan, F7 mensyaratkan web/bot - bagaimana lanjut?"), jawabannya: **jalankan F7
web-only sekarang**, cakupan bot ditandai `BLOCKED` (tidak ditebak). F5 dianggap diterima
implisit lewat instruksi "Kerjakan F7 saja".

Satu celah keamanan ditemukan dan DIPERBAIKI sesi ini (bukan hanya diukur): **tidak ada rate
limiting login**. Ditambahkan `identity/throttle.py` (5 percobaan gagal per IP+username per 5
menit) dan HSTS di `config/settings/prod.py` (ditemukan lewat `manage.py check --deploy`).

## File relevan (baru/diperbarui sesi ini)

- `identity/throttle.py` (baru) - rate limit login lewat Django cache framework (LocMemCache
  default, proses tunggal)
- `identity/views.py` - `GasWayanLoginView` diperbarui: cek rate limit sebelum proses login,
  catat percobaan gagal, reset counter saat sukses
- `identity/tests.py` - 3 tes baru `LoginRateLimitTests` (blokir percobaan ke-6, reset saat
  sukses, scoped per username bukan seluruh IP)
- `config/settings/prod.py` - `SECURE_HSTS_SECONDS`/`SECURE_HSTS_INCLUDE_SUBDOMAINS` ditambah
  (default 1 tahun); `SECURE_HSTS_PRELOAD` SENGAJA tetap `False` (keputusan pemilik proyek, ini
  submit ireversibel ke browser)
- `operations/test_concurrency_web.py` (baru) - 2 tes: 5 Operator berbeda dispatch tabung sama
  lewat HTTP bersamaan (tepat 1 sukses), 5 thread POST payload+idempotency key identik
  bersamaan (semua sukses via replay, tetap 1 Cycle)
- `operations/management/commands/perf_benchmark.py` (baru) - bangun data sintetis (bulk_create,
  default 3.000 Cylinder/300 Customer/20.000 Cycle), ukur p50/p95/max lewat Django test Client
  untuk cari-exact, cari-per-pelanggan, log penggunaan, detail tabung, dan mutasi
  dispatch+return; auto-cleanup di akhir (`--keep-data` untuk skip)
- `.gitignore` - tambah `*.dump` (backup Postgres jangan pernah masuk Git) dan pengecualian
  `docs/reports/f7-performance.json` (aman, agregat saja)
- `docs/reports/F7.md`, `docs/demo/F7.md`, `docs/reports/f7-performance.json`
- `CLAUDE.md` - status implementasi -> F7 (web), catatan F6 dilompati sementara, command baru
- `progress.md` - F5 -> ACCEPTED (implisit), F6 -> TODO (dilompati sementara, dicatat alasan),
  F7 -> READY_FOR_REVIEW (web) 6/6, F8 next diperbarui

Tidak diubah: skema database (F7 tidak menambah/mengubah model apa pun), `imports/`, `catalog/`
(selain tidak disentuh sama sekali sesi ini), `identity/permissions.py`,
`config/settings/{base,dev,test}.py`. Tidak ada migrasi/deploy produksi.

## Keputusan yang diambil sesi ini

- **Cakupan F7 dipersempit ke web saja**, disetujui eksplisit pemilik proyek via pertanyaan di
  awal sesi (bukan diasumsikan sepihak) - konsisten prinsip proyek "jangan menebak". Cakupan
  bot dari F7 (end-to-end web/bot, load test bot) TIDAK ditutup - tetap `BLOCKED`, perlu sesi
  tambahan setelah F6.
- Rate limiting login memakai Django cache framework bawaan (LocMemCache), BUKAN Redis/tabel
  PostgreSQL khusus - cukup untuk deployment satu proses saat ini; keputusan arsitektur worker/
  cache bersama untuk multi-proses tetap `PENDING` (MIG-P01), rate limiting ini tidak
  mendahului keputusan itu (hanya memakai cache framework generik Django, bukan komitmen
  teknologi antrean).
- `SECURE_HSTS_PRELOAD` SENGAJA tidak diaktifkan meski Django menyarankannya - submit ke
  preload list browser (Chrome HSTS preload list) SULIT/TIDAK BISA dibatalkan setelah domain
  sungguhan didaftarkan, jadi ini keputusan yang harus eksplisit dari pemilik proyek saat
  domain produksi sudah pasti (F8), bukan default otomatis dari Claude Code.
- Benchmark performa memakai data BULK-CREATE murni (bypass service layer untuk pembuatan
  histori sintetis) supaya cepat membangun volume besar, TAPI pengukuran mutasi (dispatch+
  return) tetap lewat `operations.services` sungguhan (bukan bypass) - supaya angka mutasi
  representatif terhadap biaya idempotency+lock+audit+outbox yang sesungguhnya berjalan.
- Backup/restore drill dilakukan di INSTANCE POSTGRES YANG SAMA (database baru sementara), bukan
  mesin terpisah - cukup untuk membuktikan mekanisme dump/restore dan integritas data bekerja
  di tahap ini; rehearsal lintas-mesin sungguhan dicatat sebagai pekerjaan F8, bukan diklaim
  selesai di sini.
- Dump backup dan database restore sementara DIHAPUS setelah drill (dump sempat berisi data
  pelanggan asli hasil publish F4) - tidak disimpan di disk, tidak masuk Git.

## Tes terakhir

`python manage.py test --settings=config.settings.test` -> `Ran 114 tests ... OK` (109 lama + 5
baru). `ruff check .`/`ruff format --check .` bersih. `makemigrations --check --dry-run` ->
tidak ada drift. `manage.py check --deploy --settings=config.settings.prod` (dengan env
sementara) -> 1 WARNING sengaja (HSTS preload). Backup/restore drill sungguhan lewat
`docker exec` terhadap `gas-wayan-python-postgres-1` - 7 tabel kunci cocok persis antara
database asli dan hasil restore. Benchmark performa sungguhan terhadap database dev (data
sintetis 20.000 Cycle, dibersihkan otomatis, diverifikasi 0 baris tersisa setelah selesai).

## Next action (satu langkah)

Pemilik proyek: (1) jalankan `docs/demo/F7.md`, (2) review matriks UAT dan hasil keamanan/
performa/backup di `docs/reports/F7.md`, (3) konfirmasi F7 cakupan web diterima, (4) putuskan
jadwal F6 (bot Telegram) - setelah F6 selesai, cakupan bot dari F7 (end-to-end web/bot, load
test bot) perlu disusulkan sebagai sesi tambahan sebelum F8 (deployment produksi) dimulai. F8
tidak dimulai tanpa F6 dan pelengkap F7 tersebut.
