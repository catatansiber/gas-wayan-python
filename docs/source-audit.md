# Audit Sumber (Reproduksi) - SERI TABUNG.xlsm

Status: `F0 - VERIFIKASI SELESAI`
Tanggal: 16 September 2026
Dilakukan oleh: gas-wayan-python (proyek Python), independen dari audit lama
Sumber pembanding: `../Gas Wayan/docs/workbook-audit.md` (audit 14 September 2026)

## Tujuan

Memverifikasi ulang secara independen bahwa sumber (`../SERI TABUNG.xlsm`) belum berubah sejak
audit lama, dan mereproduksi hitungan struktural (baris, kolom, missing value, duplikat, dan
masalah tanggal) tanpa bergantung pada dokumen lama sebagai satu-satunya bukti.

## Metode (read-only, tanpa VBA, tanpa Python)

Tidak ada Python di lingkungan kerja saat ini (dicek: tidak ada `python`/`py` di PATH atau lokasi
instalasi umum). Karena itu verifikasi memakai PowerShell yang sudah tersedia, dengan pendekatan:

1. Buka `.xlsm` sebagai paket ZIP/OOXML memakai `System.IO.Compression.ZipFile` dalam mode
   **read-only** (`OpenRead`). Tidak pernah membuka lewat Excel/COM, sehingga **VBA tidak pernah
   dijalankan**.
2. Parse `xl/workbook.xml` + `xl/_rels/workbook.xml.rels` untuk memetakan nama sheet ke bagian
   XML-nya (menghindari asumsi urutan sheet).
3. Parse `xl/sharedStrings.xml` dan `xl/styles.xml` (untuk mendeteksi style bertipe tanggal).
4. Streaming-parse `xl/worksheets/sheet8.xml` (sheet `Database`) per baris memakai
   `System.Xml.XmlReader` (bukan DOM penuh, supaya aman untuk file besar).
5. Hitung agregat saja (jumlah, unik, duplikat, kosong) - **tidak ada nilai Nomor Tabung atau
   Nama Relasi mentah yang dicetak ke konsol, log, atau dokumen ini**, sesuai aturan proyek.

Skrip: [`scripts/audit_workbook.ps1`](../scripts/audit_workbook.ps1). Cara menjalankan ulang:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_workbook.ps1 `
  -WorkbookPath "..\SERI TABUNG.xlsm" -OutFile "docs/reports/f0-audit-raw.json"
```

`-ExecutionPolicy Bypass` hanya berlaku untuk proses ini, tidak mengubah kebijakan sistem.
Output lengkap (agregat) tersimpan di
[`docs/reports/f0-audit-raw.json`](reports/f0-audit-raw.json) - aman untuk disimpan karena tidak
berisi data pelanggan mentah.

## Checksum sumber

```text
SHA-256: D96FC4E7366BFC9B38CBD2BEB6985CAB361BCA9E1D36CFAED5DD1FFDDFA33B81
```

Cocok persis dengan checksum di `../Gas Wayan/docs/workbook-audit.md`. Sumber **belum berubah**
sejak audit lama.

## Peta sheet (diverifikasi ulang)

| Sheet | Bagian XML | Peran |
| --- | --- | --- |
| `Database` | `xl/worksheets/sheet8.xml` | Sumber data utama, visible |
| `SearchData` | `xl/worksheets/sheet10.xml` | Cache hasil pencarian, **hidden**, 7 elemen `<row>` (header + sisa hasil pencarian terakhir) |

Dikonfirmasi: `SearchData` bersifat cache sementara, bukan sumber transaksi tambahan. Skrip
migrasi (F3) tidak boleh membaca `SearchData` sebagai baris bisnis.

## Hitungan struktural (dibandingkan dengan audit lama)

| Metrik | Audit lama | Reproduksi F0 | Status |
| --- | ---: | ---: | --- |
| `dimension` sheet Database | `A1:F11138` | `A1:F11138` | Cocok |
| Record berisi data | 10.597 | 10.597 | Cocok persis |
| Baris kosong (tanpa data di enam kolom, termasuk yang tanpa elemen `<row>` sama sekali) | 540 | 540 | Cocok persis |
| `Nomor` unik | 7.036 | 7.036 | Cocok persis |
| Kelompok `Nomor` duplikat | 2.466 | 2.466 | Cocok persis |
| Record tambahan akibat `Nomor` duplikat | 3.561 | 3.561 | Cocok persis |
| Nomor tabung unik (setelah trim) | 2.450 | 2.450 | Cocok persis |
| Nomor tabung dengan >1 record | 1.827 | 1.827 | Cocok persis |
| Maksimum record untuk satu nomor tabung | 14 | 14 | Cocok persis |
| Relasi unik setelah trim saja | 1.621 | 1.621 | Cocok persis |
| Relasi unik setelah trim+uppercase+collapse spasi | 1.288 | 1.288 | Cocok persis |
| Nilai Jenis Gas unik setelah trim | 165 | 165 | Cocok persis |
| Nilai Jenis Gas unik setelah normalisasi sederhana | 153 | 153 | Cocok persis |
| Tanggal Pengiriman - native Excel date | 798 | 798 | Cocok persis |
| Tanggal Pengembalian - native Excel date | 519 | 519 | Cocok persis |
| Spasi luar - Nomor Tabung | 2.470 | 2.470 | Cocok persis |
| Spasi luar - Nama Relasi | 3.650 | 3.650 | Cocok persis |
| Spasi luar - Tanggal Pengiriman | 3.212 | 3.212 | Cocok persis |
| Spasi luar - Tanggal Pengembalian | 3.122 | 3.122 | Cocok persis |
| Spasi luar - Jenis Gas | 793 | 793 | Cocok persis |
| Baris 10.599-10.601 berisi data | ya (ketiganya) | ya (ketiganya, diverifikasi) | Cocok persis |

Kesimpulan: seluruh hitungan struktural inti tereproduksi **persis sama** dengan audit lama
memakai jalur teknis independen (parser OOXML manual di PowerShell, bukan `openpyxl`). Ini
memberi keyakinan tinggi bahwa profil data lama akurat dan sumber belum berubah.

## Perbedaan metodologi yang ditemukan (dicatat, bukan disembunyikan)

### 1. Empty count per kolom bergeser +1 secara konsisten

| Kolom | Audit lama (empty) | Reproduksi F0 (empty) |
| --- | ---: | ---: |
| Nomor | 0 | 1 |
| Nomor Tabung | 41 | 42 |
| Nama Relasi | 43 | 44 |
| Tanggal Pengiriman | 216 | 217 |
| Tanggal Pengembalian | 2.044 | 2.045 |
| Jenis Gas | 8.500 | 8.501 |

Pola +1 di **semua** kolom menunjuk ke satu baris yang sama: baris dengan elemen `<row>` di XML
tetapi keenam kolomnya benar-benar kosong (bagian dari 540 baris kosong di atas). Reproduksi F0
menghitung empty/non-empty per kolom atas **seluruh rentang fisik** (baris 2 sampai 11.138).
Audit lama kemungkinan menghitung persentase empty per kolom hanya atas **10.597 baris berisi
data**, sehingga satu baris yang sepenuhnya kosong itu tidak ikut ditambahkan ke tally kosong per
kolom. Kedua pendekatan valid untuk tujuannya masing-masing; angka 10.597/540/7.036/2.450/1.288/
165/153 (yang tidak bergantung pada pilihan ini) semuanya cocok persis seperti tabel di atas.

### 2. Split "dapat diparse" vs "tidak dapat diparse" pada tanggal berbentuk teks

| Kolom | Audit lama - tidak dapat diparse | Reproduksi F0 - tidak dapat diparse | String non-kosong (kedua metode) |
| --- | ---: | ---: | ---: |
| Tanggal Pengiriman | 38 | 181 | 9.583 |
| Tanggal Pengembalian | 105 | 204 | 8.034 |

Jumlah string non-kosong (9.583 dan 8.034) **cocok persis**, jadi ekstraksi nilai kolom sudah
benar. Yang berbeda adalah kelonggaran parser tanggal: parser F0 memakai satu pola regex
`d[/.-]m[/.-]y` (day-first, tanpa menebak) dan menolak apa pun di luar itu (termasuk kombinasi
tanggal+waktu, atau varian yang tidak dijelaskan di audit lama). Audit lama memakai parser
`openpyxl`/Python yang tidak dipublikasikan sumbernya di sini, sehingga kemungkinan menerima
sedikit lebih banyak variasi format sambil tetap konservatif (day-first, tanpa perbaikan
otomatis). **Tidak ada satu pun tanggal yang "ditebak"** oleh parser F0 - beda hasil murni soal
cakupan pola yang diterima, bukan soal menebak nilai.

Implikasi untuk F3: parser staging resmi harus didesain ulang dan diuji dengan fixture eksplisit
(bukan mewarisi regex sederhana ini apa adanya), dan harus mencatat *parser rule/version* per
baris sesuai `../Gas Wayan/output/pdf/Panduan_dan_Prompt_Claude_Code.md` bagian 04. Item ini
ditambahkan ke `docs/migration-decisions-pending.md` (MIG-P06).

### 3. Kandidat kronologi terbalik (kembali sebelum kirim)

Audit lama: 417 kandidat. Reproduksi F0: 418 kandidat (dari 8.059 baris yang kedua tanggalnya
berhasil diresolusi, native atau string-parseable). Selisih 1 record konsisten dengan cakupan
parser tanggal yang sedikit berbeda (poin 2 di atas: parser F0 meresolusi 8.059 pasangan tanggal
lengkap vs kemungkinan jumlah berbeda pada audit lama). Sinyal ini tetap berstatus sinyal review,
bukan bukti kesalahan data (sama seperti kesimpulan audit lama).

### 4. Kandidat duplikat bisnis (mengabaikan kolom Nomor)

Audit lama: 26 kelompok, 61 record tambahan. Reproduksi F0: 23 kelompok, 58 record tambahan.
Selisih kecil ini konsisten dengan kunci komposit yang dipakai: F0 membandingkan Tanggal
Pengiriman dan Tanggal Pengembalian sebagai **nilai mentah** (native serial atau teks asli),
sedangkan audit lama kemungkinan membandingkan nilai yang **sudah dinormalisasi ke tanggal**
sebelum dibandingkan (dua representasi tanggal mentah yang berbeda teks tapi sama makna akan
dianggap sama oleh audit lama, tapi beda oleh F0). Tidak mengubah kesimpulan: ini kandidat review
manual, bukan penghapusan otomatis.

## Requirements dan keputusan lama - diverifikasi masih berlaku

Dibaca ulang: `../Gas Wayan/docs/requirements.md` (status `BASELINE - CONFIRMED`),
`../Gas Wayan/docs/decisions.md` (ADR-001..014), `../Gas Wayan/README.md`. Tidak ada perubahan
terhadap dokumen-dokumen itu sejak proyek Python dimulai. Keputusan bisnis DEC-001..DEC-016 tetap
`CONFIRMED` dan dipertahankan (lihat ringkasan di `CLAUDE.md` dan detail lengkap di dokumen
lama). Tidak ada keputusan bisnis yang diam-diam diganti oleh reproduksi audit ini.

## Batas verifikasi F0 ini

- Tidak menjalankan macro/VBA apa pun (dikonfirmasi: hanya baca ZIP, tidak ada proses Excel yang
  dibuka).
- Tidak menulis ke `SERI TABUNG.xlsm` (dikonfirmasi: hanya `ZipFile.OpenRead`, checksum tetap
  sama sebelum dan sesudah setiap run skrip).
- Tidak mempublikasikan atau menulis data apa pun ke tabel operasional - proyek ini belum punya
  database atau kode aplikasi (itu domain F1-F4).
- Tidak menebak jawaban atas pertanyaan bisnis yang masih terbuka (lihat
  `docs/migration-decisions-pending.md`).
