# Keputusan Migrasi yang Tertunda

Status dokumen: `DRAFT - BELUM DIIMPLEMENTASIKAN`
Tanggal: 16 September 2026
Sumber: `../Gas Wayan/docs/workbook-audit.md` (bagian "Pertanyaan bisnis yang belum dapat
dipastikan"), `../Gas Wayan/docs/requirements.md` (butir berstatus `PENDING`),
`docs/decisions.md` di proyek ini (ADR-P005, ADR-P011), `docs/source-audit.md` (reproduksi audit
16 September 2026), dan `docs/migration-policy.md` bagian B (usulan kebijakan belum dikonfirmasi).

Aturan: keputusan `PENDING` tidak boleh diam-diam dianggap final dalam kode. Data yang bergantung
pada keputusan `PENDING` ditahan di staging (F3/F4), bukan dipublikasikan dengan asumsi.

## A. Keputusan arsitektur Python (baru, muncul karena penggantian stack)

| ID | Keputusan | Status | Kapan dikunci | Dampak jika ditunda |
| --- | --- | --- | --- | --- |
| MIG-P01 | Mekanisme antrean worker Telegram: polling PostgreSQL sederhana vs Celery/RQ vs `django-q`, dengan/tanpa Redis | `PENDING` - belum dibutuhkan sampai F6 | F6 | F6 (Telegram) tidak bisa dimulai tanpa ini |
| MIG-P02 | Tool dependency management | `RESOLVED (F1)` - `pip-tools` 7.6.1, `requirements.in`/`requirements-dev.in` -> `requirements*.txt` dengan `--generate-hashes --allow-unsafe`. Lihat CLAUDE.md dan `scripts/compile_requirements.ps1` | F1 | - |
| MIG-P03 | Versi persis Python, Django, PostgreSQL, `psycopg`, pustaka dev | `RESOLVED (F1)` - Python 3.13.15, Django 5.2.17 LTS, psycopg 3.3.5, django-environ 0.14.0, ruff 0.16.7, PostgreSQL 18.6-alpine. Diverifikasi via PyPI/djangoproject.com/postgresql.org 16 September 2026, lihat `docs/reports/F1.md`. `openpyxl` dan pustaka bot Telegram belum dipin - baru dibutuhkan F3/F6 | F1 (inti) / F3, F6 (sisanya) | - |
| MIG-P04 | Target deployment F8: VPS Linux mandiri vs layanan terkelola (mis. platform PaaS) | `PENDING` | Selambatnya sebelum F8, sebaiknya diputuskan lebih awal untuk perencanaan biaya | F8 tidak bisa mulai; estimasi biaya/waktu rilis tidak pasti |
| MIG-P05 | Strategi test | `RESOLVED (F1)` - PostgreSQL nyata via Docker Compose (`docker-compose.yml`), `config.settings.test` menunjuk ke database yang sama (Django membuat `test_<nama>` otomatis). Diverifikasi: 11 tes lulus melawan Postgres nyata di checkout bersih | F1-F2 | - |
| MIG-P07 | Versi persis `openpyxl` (pembaca XLSM) | `RESOLVED (F3)` - openpyxl 3.1.5 (terbaru stabil per PyPI 16 September 2026), lihat requirements.in | F3 | - |
| MIG-P08 | Versi persis pustaka HTTP/bot Telegram (mis. `httpx` mentah vs `python-telegram-bot`) - bergantung pada keputusan MIG-P01 | `PENDING` | F6 | F6 tidak bisa dimulai tanpa ini |
| MIG-P06 | Spesifikasi parser tanggal legacy resmi (pola/format yang diterima, kebijakan tahun 2 digit, penanganan kombinasi tanggal+waktu) | `PENDING - PROPOSAL diajukan F3` - `F3-PARSER-v1` (`imports/parsing.py`): day-first ketat `d[/.-]m[/.-]y`, tahun 2 digit 00-68->20xx/69-99->19xx, fixture-tested (25 tes). Hanya dipakai untuk staging, BELUM untuk publish. Pemilik proyek perlu konfirmasi sebelum F4 - lihat docs/reports/F3.md | F4 (sebelum publish) | Publish F4 tidak boleh memakai parser ini sebagai final tanpa konfirmasi eksplisit |
| MIG-P09 | Cakupan reversal/koreksi di luar DISPATCH: bagaimana membatalkan RETURNED, EXCHANGED, atau LOST yang salah? F2 hanya mengimplementasikan `reverse_dispatch` (kasus paling umum). Reversal RETURNED perlu membuka kembali siklus (apakah cylinder harus AVAILABLE saat itu?); reversal EXCHANGED menyentuh dua tabung sekaligus; reversal LOST mengembalikan ke status sebelumnya yang mungkin ambigu | `PENDING` | F4 (impor mungkin butuh membatalkan batch publish) atau F5 (Admin butuh koreksi umum di UI) | Koreksi selain "batalkan kirim yang salah" tidak tersedia sampai diputuskan |

## A.1 Usulan kebijakan migrasi yang menunggu konfirmasi (detail di `docs/migration-policy.md` bagian B)

| ID | Ringkasan | Rujukan detail |
| --- | --- | --- |
| MIG-B21 (alias B1) | Kebijakan Jenis Gas kosong/`NEEDS_REVIEW`: publish tetap jalan dengan flag, atau tahan penuh di staging? | `docs/migration-policy.md` B1 |
| MIG-B22 (alias B2) | Kebijakan kembali tanpa tanggal: default OPEN vs RETURNED-tanpa-tanggal vs NEEDS_REVIEW | `docs/migration-policy.md` B2 |
| MIG-B23 (alias B3) | Kebijakan konflik siklus pada data historis (tumpang tindih naif) | `docs/migration-policy.md` B3 |
| MIG-B24 (alias B4) | Kebijakan rekonsiliasi status aktual tabung pasca-migrasi | `docs/migration-policy.md` B4 |

## B. Keputusan bisnis warisan yang masih terbuka (dari workbook-audit.md)

Pertanyaan berikut belum terjawab pada audit 14 September 2026 dan memblokir publish data terkait
di F4, bukan pembuatan fondasi:

| ID | Pertanyaan | Blocker untuk |
| --- | --- | --- |
| MIG-B01 | Apa arti resmi kolom `Nomor`: nomor transaksi, urut, dokumen, atau per tabung? | Mapping legacy reference di F3/F4 |
| MIG-B02 | Apakah beberapa tabung dalam satu pengiriman seharusnya berbagi satu nomor dokumen? | Skema dokumen pengiriman (di luar scope versi awal per DEC-006, tetap dicatat) |
| MIG-B03 | Apakah `Nomor Tabung` unik secara global, per pemilik, atau per jenis gas? | Constraint unique di F2 |
| MIG-B04 | Apakah tanggal pengembalian kosong selalu berarti tabung masih di relasi? | Status siklus saat publish (F4) |
| MIG-B05 | Apa perbedaan makna `K`, `KEMBALI`, `SDH KEMBALI`, `SDH BALIK`? | Mapping event `RETURNED` (`K`/`KEMBALI`/`SDH KEMBALI` sudah `CONFIRMED`; `SDH BALIK` belum) |
| MIG-B06 | Bagaimana penukaran tabung historis dicatat di sumber: tutup+buka siklus, atau hanya ganti catatan? | Rekonstruksi histori tukar saat migrasi (F4) |
| MIG-B07 | Apa arti kode tambahan BBS, MR, TOB, SA, TIRA, ABG, SMB, TR, UHP, dll. pada Jenis Gas? | Mapping `NEEDS_REVIEW` -> gas resmi (F4); tanpa keputusan ini kode tetap `NEEDS_REVIEW` permanen |
| MIG-B08 | Apakah kode tambahan menunjukkan jenis gas, ukuran, tekanan, pemasok, pemilik, kondisi, atau lokasi? | Desain atribut tambahan tabung/master (jika diperlukan) |
| MIG-B09 | Apakah jenis gas melekat pada tabung secara permanen atau bisa berubah per siklus? | Model data `GasType` pada `Cylinder` vs `Cycle` (F2) |
| MIG-B10 | Apakah satu nama relasi bisa mewakili beberapa orang/lokasi berbeda? | Kebijakan merge relasi (FR-03), auto-alias vs manual review |
| MIG-B11 | Siapa yang berhak melakukan koreksi, pembatalan, tandai hilang, dan merge relasi di luar role baku ADMIN? | Sudah `CONFIRMED` ke ADMIN di requirements.md; dicatat ulang untuk verifikasi tidak berubah |
| MIG-B12 | Apakah histori yang pernah terhapus di Excel (sebelum snapshot ini) perlu direkonstruksi dari backup lain? | Kelengkapan arsip; jika ya, perlu sumber tambahan di luar `SERI TABUNG.xlsm` |
| MIG-B13 | Aturan tanggal ambigu (mis. `8.9.25`): day-first selalu, atau ikut locale pengguna? | Parser tanggal F3 (baseline: day-first konservatif, tanpa tebakan) |
| MIG-B14 | Apakah tanggal kembali boleh sah lebih awal dari tanggal kirim karena baris merepresentasikan tukar/koreksi? | 417 kandidat kronologi mencurigakan; keputusan menentukan apakah baris ini publish langsung atau wajib review |
| MIG-B15 | Apakah workbook mencakup semua tabung aktif, atau hanya transaksi sejak periode tertentu? | Rekonsiliasi stok awal (F4), penentuan status `AVAILABLE` default |
| MIG-B16 | Apakah ada cabang/gudang/pemasok/kepemilikan tabung yang perlu dipisahkan di masa depan? | Sudah `CONFIRMED` di luar scope versi awal (satu gudang, DEC-007); dicatat sebagai potensi perubahan scope |
| MIG-B17 | Apakah pengiriman membutuhkan surat jalan, pengemudi, kendaraan, kuantitas, harga, tanda terima? | Sudah `CONFIRMED` di luar scope versi awal; dicatat sebagai potensi perubahan scope |
| MIG-B18 | Apa definisi tabung overdue dan tindak lanjutnya? | FR-12 dashboard tambahan (`PENDING` di requirements.md) |
| MIG-B19 | Data mana yang wajib tetap dapat dicari dengan nomor legacy setelah migrasi? | Desain pencarian F5/F9 (index nomor legacy) |
| MIG-B20 | Apakah tiga record pada baris 10.599-10.601 sudah pernah terlihat/dipakai operator? | Prioritas review manual F4 untuk baris tersebut |

## C. Non-functional requirements berstatus PENDING (dari requirements.md)

| ID | Item | Baseline sementara | Blocker untuk |
| --- | --- | --- | --- |
| MIG-N01 | Latency pencarian p95 | Target belum disahkan: <=1 detik | F7 (pengesahan target performa) |
| MIG-N02 | Latency command p95 | Target belum disahkan: <=2 detik di luar API Telegram | F7 |
| MIG-N03 | Availability | Belum ditetapkan | F7/F8 (SLA operasional) |
| MIG-N04 | Kebutuhan dashboard tambahan, definisi overdue, format export, jadwal laporan, penerima laporan | Belum ditetapkan | F5 (scope dashboard/laporan lanjutan) |

## Cara menutup item PENDING

1. Pemilik proyek memutuskan (bukan Claude Code secara sepihak) untuk item kategori B dan C.
2. Untuk kategori A, Claude Code mengusulkan opsi dengan trade-off saat fase terkait dimulai;
   pemilik proyek memilih.
3. Setiap keputusan yang ditutup dipindah dari dokumen ini ke `docs/decisions.md` (jika arsitektur)
   atau dicatat sebagai `CONFIRMED` baru di dokumen requirements proyek Python dengan referensi ID
   di atas, lalu baris terkait di dokumen ini dihapus atau ditandai selesai dengan tautan ke
   keputusan barunya.
