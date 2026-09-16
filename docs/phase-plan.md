# Rencana Fase - gas-wayan-python

Status dokumen: `DRAFT - BELUM DIIMPLEMENTASIKAN`
Tanggal: 16 September 2026
Sumber: `../Gas Wayan/docs/requirements.md`, `../Gas Wayan/docs/workbook-audit.md`,
`../Gas Wayan/docs/decisions.md`, dan bagian 05-08
`../Gas Wayan/output/pdf/Panduan_dan_Prompt_Claude_Code.md`.

Satu fase dikerjakan per sesi. Status `ACCEPTED` hanya diberikan setelah pemilik proyek melihat
demo dan bukti tes, bukan berdasarkan klaim selesai. Progres teknis dihitung dari checklist
lulus/total per fase (lihat `progress.md` di root), bukan estimasi waktu.

## Urutan dan dependensi

F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7 -> F8 (berurutan; setiap fase mensyaratkan fase
sebelumnya `ACCEPTED`, kecuali disebutkan lain).

## F0 - Audit dan keputusan bisnis

**Tujuan:** memverifikasi ulang sumber, menegaskan keputusan bisnis yang dipertahankan, dan
mencatat ADR penggantian stack sebelum kode ditulis.

**Kerja:** periksa workbook read-only, verifikasi requirements lokal, buat workspace Python
terpisah (`gas-wayan-python/`), tulis ADR penggantian TypeScript -> Python. Pisahkan fakta
(audit), keputusan terdahulu (requirements/decisions lama), rekomendasi baru, dan pertanyaan yang
belum terjawab.

**Hasil:** `CLAUDE.md`, `docs/phase-plan.md`, `docs/decisions.md`,
`docs/migration-decisions-pending.md`, `progress.md`, `handoff.md`.

**Demo:** tunjukkan profil 10.597 baris (10.597 record, 540 baris kosong, 2.450 nomor tabung
unik, 1.288 nama relasi setelah normalisasi), contoh anomali yang dimask, mapping enam kolom
Database, serta daftar keputusan yang memengaruhi publish nantinya.

**Exit gate:** checksum SHA-256 workbook cocok
(`D96FC4E7366BFC9B38CBD2BEB6985CAB361BCA9E1D36CFAED5DD1FFDDFA33B81`); Database dipisahkan secara
konsep dari SearchData (cache, bukan sumber); batas fitur versi awal disepakati; seluruh
keputusan kritis (DEC-001..DEC-016 lama) punya status di proyek Python. Keputusan yang belum
terjawab memblokir publish terkait di F4, tetapi tidak memblokir pembuatan fondasi di F1.

## F1 - Fondasi Python yang dapat dijalankan

**Tujuan:** environment Django yang berjalan lokal dengan auth dan role dasar, terpisah total
dari proyek TypeScript lama.

**Kerja:** siapkan environment, dependency lock (versi dipin), proyek Django, PostgreSQL lokal
terpisah (Compose baru, bukan `compose.yaml` lama), konfigurasi dev/test/prod, login, role
(ADMIN/OPERATOR/VIEWER), health check, lint/test, dan README PowerShell. Tidak memakai credential
proyek lama.

**Hasil:** satu perintah setup lokal terdokumentasi, `.env.example` tanpa secret, aplikasi
terbuka di browser, tes awal dan CI dasar. Admin dibuat lewat mekanisme aman (management command
interaktif atau seed terkontrol), bukan password hardcoded.

**Demo:** login sebagai Admin/Operator/Viewer; tunjukkan akses terlarang ditolak oleh server
(bukan hanya UI disembunyikan). Jelaskan port, nama database, dan cara menghentikan aplikasi.

**Exit gate:** setup ulang dari checkout bersih berhasil; migrasi database berjalan; role teruji
otomatis; konfigurasi produksi tidak memakai `DEBUG=True` atau secret development; port tidak
bentrok dengan proyek lama.

## F2 - Model dan layanan lifecycle

**Tujuan:** domain model dan aturan bisnis inti (kirim/kembali/tukar/hilang/maintenance/
pensiun/koreksi) dengan integritas transaksional.

**Kerja:** buat master (Customer+alias, GasType, Cylinder), `Cycle`, `LifecycleEvent`, audit log,
idempotency record; layanan kirim/kembali/tukar/hilang/maintenance/pensiun/koreksi. Tambahkan
constraint database, row lock (`select_for_update`), dan alasan wajib untuk koreksi.

**Hasil:** migrasi schema dan tes domain/integrasi (di PostgreSQL nyata, bukan hanya SQLite)
dengan data sintetis. Django Admin tidak boleh mengizinkan perubahan bebas pada tabel event.

**Demo:** kirim satu tabung; kembalikan; kirim lagi. Coba dua request kirim bersamaan, ulang
idempotency key yang sama, dan tukar ke tabung yang tidak tersedia.

**Exit gate:** hanya satu siklus aktif per tabung (constraint database, bukan hanya validasi
aplikasi); concurrency tidak menggandakan transaksi; tukar bersifat atomic; koreksi meninggalkan
jejak audit; server memeriksa role pada tiap command. Dokumentasi state transition sesuai kode
dan tes. Tes kegagalan (bukan hanya alur sukses) adalah bagian penerimaan.

## F3 - Importer raw dan staging

**Tujuan:** membaca seluruh isi workbook ke arsip raw immutable tanpa memengaruhi data
operasional.

**Kerja:** bangun management command untuk dry-run XLSM, parser terkontrol, deteksi anomali,
raw/staging immutable, dan laporan JSON/CSV. Pakai fixture sintetis yang mewakili tanggal
campuran dan status legacy (`K`, `KEMBALI`, dll). Lindungi ekspor CSV dari formula injection pada
nilai yang berawalan karakter formula.

**Hasil:** raw archive, staging, statistik per kategori, laporan kandidat duplikat, dan daftar
masalah berdasarkan nomor baris sumber. Laporan berisi data asli tetap lokal, tidak masuk Git.

**Demo:** jalankan dry-run pada salinan workbook, lalu jalankan ulang. Tampilkan tiga baris
terakhir (10.599-10.601) dan contoh tanggal/status bermasalah yang dimask.

**Exit gate:** persis 10.597 raw row untuk snapshot ini; 540 baris kosong terhitung eksplisit;
checksum sumber tetap; re-run tidak menambah raw duplikat; master/lifecycle belum berubah; isi
`SearchData` tidak dihitung sebagai transaksi baru.

## F4 - Review, publish, dan rekonsiliasi

**Tujuan:** memindahkan data staging yang tervalidasi ke master/lifecycle operasional secara
terkontrol dan dapat direkonsiliasi.

**Kerja:** buat layar review Admin, mapping pelanggan/gas/status, penerbitan per kelompok
tervalidasi, `SourceLink` (raw row <-> event), resume job, dan pembatalan batch. Terapkan
keputusan yang sudah `CONFIRMED` di `docs/migration-decisions-pending.md`; keputusan yang masih
`PENDING` tetap menahan data terkait di staging.

**Hasil:** laporan sebelum/sesudah per batch, daftar pending review dengan alasan, jejak
perubahan mapping, dan rencana pemulihan (restore/rollback). Riwayat legacy yang belum
diterbitkan tetap dapat dicari.

**Demo:** selesaikan satu anomali, publish, hentikan job secara terkendali lalu resume, dan
re-run tanpa duplikasi. Uji raw row yang dipetakan ke dua event serta kandidat duplikat yang
diputuskan Admin.

**Exit gate:** seluruh source row terpetakan ke kategori hasil (published / pending_review /
excluded_approved), jumlahnya = 10.597, tanpa event yatim atau selisih tanpa alasan. Review
blocker status tabung aktif selesai sebelum tabung itu dipakai operasional. Rehearsal
restore/pembatalan batch berhasil di database staging terpisah.

## F5 - Layar operasional web dan laporan

**Tujuan:** UI Django Templates untuk operator sehari-hari, menggantikan `Formulir_Gas` Excel.

**Kerja:** buat form kirim/kembali dengan preview, pencarian exact nomor tabung, filter
pelanggan, detail siklus, fungsi khusus Admin, dashboard ringkas, dan log penggunaan tabung.
Tampilkan status kualitas data (`NEEDS_REVIEW`, dsb.) terpisah dari status tabung.

**Hasil:** aplikasi responsif dari layar 360px sampai desktop, validasi berbahasa Indonesia,
pagination server-side, ekspor bila formatnya sudah disetujui.

**Demo:** satu alur nyata dengan data uji: cari pelanggan, kirim, kembali, lihat riwayat. Coba
nomor tidak ditemukan, hasil pencarian kosong, role terlarang, dan tanggal tidak sah.

**Exit gate:** hasil kosong tidak menampilkan hasil pencarian lama; double-click tidak
menggandakan transaksi; Viewer tidak dapat menulis; tanggal Asia/Makassar konsisten; seluruh
mutasi melewati layanan domain F2 (tidak ada jalur pintas dari view). Laporan memisahkan tanggal
diketahui dan tidak diketahui.

## F6 - Input Telegram yang andal

**Tujuan:** jalur input paralel via bot Telegram dengan role dan idempotency yang sama dengan web.

**Kerja:** daftarkan bot lewat BotFather; token disimpan sebagai secret environment. Admin
memasangkan numeric Telegram user ID ke pengguna internal (username bukan identitas otorisasi).
Private chat saja. Untuk tes lokal gunakan polling atau webhook tes, jangan jalankan keduanya
bersamaan untuk bot yang sama.

Alur `/kirim`: pilih tabung, pelanggan, gas, tanggal; tampilkan ringkasan; Konfirmasi/Batal;
receipt berisi nomor transaksi. `/kembali` mencari siklus aktif dan menampilkan pelanggan serta
tanggal kirim sebelum konfirmasi. `/cari`, `/status`, `/menu`, `/bantuan` untuk navigasi.
`/tukar`, `/hilang`, `/pensiun` khusus Admin.

**Hasil:** session tersimpan dengan TTL dan cancel, inbox unik (bot_id, update_id), outbox retry,
dan halaman kegagalan untuk Admin. Callback terikat ke user, chat, session, dan nonce; tombol
lama/sesi kedaluwarsa ditolak. Role dicek ulang saat commit.

**Exit gate:** webhook HTTPS memverifikasi `X-Telegram-Bot-Api-Secret-Token`; update disimpan
durably sebelum respons sukses. Duplicate update dan klik berulang tidak menggandakan transaksi.
Retry balasan tidak mengulang kirim/kembali. Kegagalan balasan tampil sebagai gagal kirim
notifikasi, bukan gagal transaksi.

## F7 - UAT, keamanan, performa, dan pemulihan

**Tujuan:** validasi end-to-end oleh pemilik proyek, plus pemeriksaan keamanan/performa/backup
sebelum rilis.

**Kerja:** pemilik proyek mencoba skenario UAT; Claude Code memperbaiki kegagalan dan melampirkan
bukti tes. Simulasikan 3-5 pengguna bersamaan. Ukur pencarian, daftar, dan mutasi; target lokal
p95 cari <=1 detik dan command <=2 detik dicatat sebagai target belum disahkan sampai diverifikasi.
Gunakan data sintetis untuk uji beban menuju kebutuhan 5 juta event/5 tahun dari requirements
lama; jangan mengklaim mampu skala tersebut hanya dari uji ~10 ribu baris. Tambah index sesuai
query plan; ukur sebelum menambah cache atau partisi.

**Hasil:** laporan UAT, laporan performa dengan angka terukur, hasil pengecekan keamanan.

**Exit gate:** tes integrasi PostgreSQL, end-to-end web/bot, pemulihan backup, dan pengecekan
akses lulus. `DEBUG=False`, HTTPS, cookie aman, CSRF web, rate limiting, dan log tanpa
token/data sensitif telah diperiksa.

## F8 - Migrasi final dan operasional

**Tujuan:** cutover produksi dengan persetujuan eksplisit pemilik proyek.

**Kerja:** sediakan deployment (Linux/VPS atau layanan terkelola yang disepakati), proses web dan
worker terpisah, database privat, HTTPS, secret produksi, health check, backup. Bekukan input
Excel, ambil snapshot final, ulang staging/review/publish dan rekonsiliasi. Jangan membuat akun
berbayar atau deploy produksi tanpa persetujuan pemilik.

**Hasil:** sistem live, runbook insiden, penanggung jawab operasional, laporan migrasi final.

**Exit gate:** pemilik menyetujui hasil migrasi dan UAT; tabung berkonflik tetap diblokir;
bot/web diuji pascarilis; backup berhasil dipulihkan di lingkungan terpisah. Excel menjadi arsip
read-only permanen. Runbook insiden dan penanggung jawab tersimpan. Laporan final mencatat data
tertunda secara eksplisit, bukan menyebut impor sempurna bila masih ada pengecualian.

## Empat file kendali (wajib tetap terbaru)

| File | Isi minimum |
| --- | --- |
| `CLAUDE.md` | Aturan tetap, stack, batas perubahan, perintah verifikasi, rujukan docs. |
| `docs/phase-plan.md` | F0-F8, checklist penerimaan tetap, dependensi, exit gate (dokumen ini). |
| `progress.md` | Status tiap fase, checklist lulus/total, bukti, blocker, langkah berikut. |
| `handoff.md` | Posisi terakhir, file relevan, keputusan, tes terakhir, satu next action. |

`docs/reports/Fn.md` menyimpan laporan rinci per fase; `docs/demo/Fn.md` berisi langkah demo dan
expected result (dibuat saat fase terkait dimulai). Bukti tangkapan layar memakai data uji, bukan
data pelanggan asli. Commit hanya file fase yang selesai; periksa staged diff agar raw pelanggan,
secret, dan file sumber tidak ikut.
