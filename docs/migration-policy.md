# Kebijakan Migrasi

Status: `F0 - SEBAGIAN CONFIRMED (lama), SEBAGIAN USULAN BARU (menunggu konfirmasi pemilik)`
Tanggal: 16 September 2026

Dokumen ini memisahkan dengan jelas: (A) aturan yang **sudah `CONFIRMED`** di proyek lama dan
tetap berlaku tanpa perubahan makna, dari (B) **usulan kebijakan teknis baru** yang dibutuhkan
proyek Python tapi belum pernah diputuskan pemilik secara eksplisit. Tidak ada jawaban yang
ditebak untuk kategori (B) - semuanya butuh persetujuan sebelum dipakai di F3/F4.

## A. Kebijakan yang sudah CONFIRMED (dipertahankan dari proyek lama)

### A1. Raw immutable dan SourceLink wajib

**Sumber:** requirements.md prinsip wajib #2, ADR-008 lama / ADR-P008.
**Aturan:** seluruh 10.597 baris sumber masuk arsip raw yang tidak pernah diubah. Setiap hasil
migrasi (published, pending_review, atau excluded) harus bisa ditelusuri kembali ke `RawRow` dan
nomor baris sumbernya lewat `SourceLink`. Nol baris boleh hilang diam-diam.
**Status:** `CONFIRMED`, tidak berubah.

### A2. SearchData bukan transaksi tambahan

**Sumber:** `../Gas Wayan/docs/workbook-audit.md`, diverifikasi ulang di `docs/source-audit.md`.
**Aturan:** sheet `SearchData` (hidden, 7 elemen baris termasuk header) adalah cache hasil
pencarian VBA, bukan sumber data bisnis. Importer F3 **tidak boleh** membaca `SearchData` sebagai
baris transaksi tambahan; hanya sheet `Database` yang menjadi sumber raw.
**Status:** `CONFIRMED`, diverifikasi ulang pada 16 September 2026 (checksum sumber cocok,
struktur sheet tidak berubah).

### A3. Jenis gas resmi dan larangan menebak kode tambahan

**Sumber:** requirements.md DEC-003/DEC-004 (`CONFIRMED`).
**Aturan:** hanya O2, AR, C2H2, N2, CO2 yang menjadi `GasType` resmi. Kode tambahan (BBS, MR,
TOB, SA, TIRA, ABG, SMB, TR, UHP, dan variasi lain) tidak pernah ditebak/dipecah menjadi gas
resmi oleh sistem secara otomatis.
**Status:** `CONFIRMED`, tidak berubah.

### A4. Nilai legacy `K`/`KEMBALI`/`SDH KEMBALI`

**Sumber:** requirements.md 5.5 (`CONFIRMED`).
**Aturan:** ketiga nilai ini punya makna sama (tabung telah kembali) dan dipetakan ke event
`RETURNED`; nilai asli tetap disimpan di raw.
**Status:** `CONFIRMED`, tidak berubah. (`SDH BALIK` TIDAK termasuk dalam daftar ini - lihat B3.)

### A5. Tidak ada hard-delete, tidak ada tebakan tanggal

**Sumber:** requirements.md prinsip wajib, bagian 9.
**Aturan:** tidak ada histori operasional yang dihapus fisik; koreksi memakai reversal/void
beralasan. Tanggal ambigu/mustahil (mis. `29/2/25`) tidak diperbaiki otomatis - masuk staging
sebagai tidak terparse.
**Status:** `CONFIRMED`, tidak berubah.

## B. Usulan kebijakan baru (BELUM dikonfirmasi pemilik - jangan diimplementasikan sebagai final)

Setiap butir di bawah adalah **proposal teknis** untuk menutup celah yang requirements.md lama
belum spesifikkan sampai level implementasi. Ditandai jelas sebagai usulan, bukan keputusan.
Status finalnya dicatat sebagai `PENDING` juga di `docs/migration-decisions-pending.md`.

### B1. Kebijakan Jenis Gas kosong/tidak dikenal (80,2% baris kosong, 165 nilai kode tambahan)

**Masalah:** requirements.md bilang kode di luar 5 resmi jadi `NEEDS_REVIEW` (A3), tapi tidak
menjawab: apakah baris dengan gas `NEEDS_REVIEW` boleh tetap dipublish ke `Cycle`/lifecycle
operasional, atau harus ditahan penuh di staging sampai gas dikonfirmasi?

**Usulan (belum dikonfirmasi):** gas bukan bagian dari invariant satu-siklus-aktif (invariant itu
berbasis `Cylinder`, bukan `GasType`). Maka publish kirim/kembali/dsb. tetap boleh jalan dengan
`Cycle.gas_type = NULL` dan `data_quality_flag = NEEDS_REVIEW`, TIDAK memblokir transaksi lain
pada tabung yang sama. Laporan (FR-12) wajib menampilkan status kualitas data ini terpisah dari
status tabung (sudah tercatat di Panduan bagian 02).

**Alternatif yang juga perlu dipertimbangkan pemilik:** menahan penuh baris bergas
`NEEDS_REVIEW` di staging sampai direview manual, dengan konsekuensi histori tabung jadi tidak
lengkap sampai review selesai.

**Status:** `PENDING` - dikunci sebelum F4 (lihat MIG-P06 di `docs/migration-decisions-pending.md`).

### B2. Kebijakan kembali tanpa tanggal (E kosong atau berisi status tanpa tanggal)

**Masalah:** requirements.md 5.4/9 menyebut tanggal kembali kosong "tidak otomatis membuktikan
tabung masih di pelanggan" (MIG-B04 di daftar pending), tapi tidak memberi aturan default untuk
staging.

**Usulan (belum dikonfirmasi):**
- Jika E kosong dan D (tanggal kirim) diketahui -> kandidat siklus tetap dianggap **OPEN**
  (status `OUT`) menunggu rekonsiliasi, TIDAK otomatis `AVAILABLE`.
- Jika E berisi kata kunci status dikenal (`K`/`KEMBALI`/`SDH KEMBALI`, lihat A4) tanpa tanggal
  yang bisa diparse -> kandidat event `RETURNED` dengan `occurred_at = NULL` dan
  `date_unknown = true`. **Tanggal impor/publish tidak pernah dipakai sebagai `returned_at`**
  (larangan eksplisit di Panduan bagian 04).
- Jika E berisi teks lain yang tidak dikenal (termasuk `SDH BALIK`, nama orang, dll.) ->
  `NEEDS_REVIEW`, ditahan staging.

**Status:** `PENDING` - bergantung pada jawaban MIG-B04 dan MIG-B05 dari pemilik.

### B3. Kebijakan konflik siklus pada data historis

**Masalah:** constraint database (A5/ADR-P006) hanya izinkan satu siklus aktif per tabung untuk
transaksi BARU. Tapi 1.827 nomor tabung punya >1 record historis (maksimum 14), dan histori lama
tidak dibuat dengan invariant ini - berpotensi menunjukkan siklus yang "tumpang tindih" secara
naif (kirim baru tercatat sebelum kembali tercatat untuk tabung yang sama).

**Usulan (belum dikonfirmasi):** saat staging (F3), urutkan raw row per `Nomor Tabung`
berdasarkan tanggal kirim (fallback: `source_row_number` bila tanggal sama/tidak diketahui) untuk
membentuk kandidat urutan siklus. Jika algoritma penyusunan menemukan indikasi tumpang tindih
(dua kirim tanpa kembali di antaranya untuk tabung yang sama), **seluruh kelompok baris terkait**
ditandai `NEEDS_REVIEW` dan diserahkan ke Admin di layar review F4 - sistem tidak memilih sendiri
mana yang "benar".

**Status:** `PENDING` - berkaitan dengan MIG-B06 (bagaimana histori tukar dicatat) dan MIG-B15
(cakupan workbook). **Update F4:** usulan ini sudah diimplementasikan literal di
`imports/publisher.py` sebagai perilaku kerja (bukan opsional) - ketika kronologi tumpang
tindih terdeteksi pada satu tabung, SELURUH kelompok baris tabung itu tetap `PENDING_REVIEW`,
tidak ada yang dipublish. Ini termasuk mendeteksi duplikat bisnis (baris identik ignoring
`Nomor`) karena secara matematis selalu muncul sebagai tumpang tindih tanggal. Status kebijakan
tetap `PENDING` secara formal - pemilik proyek belum diminta memilih di antara opsi lain, F4
hanya mengimplementasikan opsi yang paling konservatif (tahan penuh) sebagai default aman.

### B4. Kebijakan rekonsiliasi status aktual tabung pasca-migrasi

**Masalah:** requirements.md menegaskan status tabung ditentukan dari lifecycle event terakhir,
tapi tidak menjawab apa status default untuk tabung yang riwayat migrasinya berakhir ambigu
(`NEEDS_REVIEW` pada langkah terakhir).

**Usulan (belum dikonfirmasi):** status awal pasca-migrasi setiap `Cylinder` = hasil event
terpublish (bukan pending) terakhir menurut tanggal untuk `Nomor Tabung` tersebut. Tabung yang
event terakhirnya masih `NEEDS_REVIEW`/ambigu **tidak** diberi status default `AVAILABLE` -
tabung itu diblokir dari pengiriman baru sampai Admin menyelesaikan review (konsisten dengan
requirements.md 5.5 "kebijakan tabung tanpa jenis gas terkonfirmasi tetap PENDING" dan prinsip
wajib #10 "keputusan PENDING tidak boleh diam-diam dianggap final").

**Status:** `PENDING` - final reconciliation juga bergantung pada MIG-B15 (apakah workbook
mencakup semua tabung aktif).

## Cara memakai dokumen ini

- Kategori A dipakai langsung sebagai aturan wajib mulai F1.
- Kategori B **tidak boleh** dikodekan sebagai perilaku final sebelum pemilik proyek memilih di
  antara opsi yang diajukan (atau opsi lain). F3 boleh mengimplementasikan mekanisme staging yang
  mendukung kategori B sebagai *opsi yang dapat dikonfigurasi/direview*, tapi publish otomatis
  berdasarkan asumsi B1-B4 tidak boleh terjadi sebelum `CONFIRMED`.
- Setiap butir B yang disetujui pemilik dipindah ke bagian A dokumen ini dengan status
  `CONFIRMED` dan tanggal persetujuan, lalu baris terkait di
  `docs/migration-decisions-pending.md` ditutup.
