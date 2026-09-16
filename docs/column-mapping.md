# Mapping Kolom - Database (legacy) ke Model Domain (Python)

Status: `F0 - DRAFT UNTUK REVIEW`
Tanggal: 16 September 2026
Sumber: `docs/source-audit.md`, `../Gas Wayan/docs/requirements.md` (bagian 5, FR-01..FR-13),
`../Gas Wayan/output/pdf/Panduan_dan_Prompt_Claude_Code.md` (bagian 03).

Enam kolom `Database!A1:F1` tidak dipetakan satu-ke-satu ke field model baru. Setiap raw value
tetap tersimpan utuh (prinsip wajib requirements.md #2) dan dihubungkan lewat `SourceLink`, tidak
langsung menimpa field operasional.

| # | Kolom Excel | Header legacy | Makna legacy (audit) | Field/entity model baru (rencana F2) | Kebijakan migrasi |
| - | --- | --- | --- | --- | --- |
| A | A | `Nomor` | Nomor urut/transaksi legacy buatan macro; 2.466 kelompok duplikat; **tidak terbukti unik** | `RawRow.legacy_nomor` (disimpan sebagai referensi non-unik, bukan primary key) | DEC-001 (`CONFIRMED`): tidak pernah dipakai sebagai PK atau kunci lookup edit/hapus, berbeda dari VBA lama |
| B | B | `Nomor Tabung` | Identitas tabung, teks, 41-42 baris kosong (raw) | `Cylinder.serial_number` (unique text, trim tanpa hilangkan nol depan) | Baris dengan serial kosong ditahan di staging sebagai error (tidak bisa membentuk lifecycle) |
| C | C | `Nama Relasi` | Nama pelanggan/relasi; 1.621 unik (trim saja) vs 1.288 unik (trim+upper+collapse) | `Customer.display_name` + `CustomerAlias.raw_value` (satu alias per varian ejaan/spasi mentah) | Merge lintas alias **tidak otomatis**; exact-normalized match jadi kandidat, ejaan mirip perlu review Admin (FR-03) |
| D | D | `Tanggal Pengiriman` | Tanggal kirim; campuran native Excel date (798) dan teks (9.583, dengan 181 tidak terparse oleh parser F0 - lihat `docs/source-audit.md`) | `Cycle.sent_at` + `LifecycleEvent` bertipe `DISPATCHED`.`occurred_at` | Baris dengan tanggal kosong/tidak terparse ditahan staging; parser resmi dan fixture-nya didesain di F3 |
| E | E | `Tanggal Pengembalian` | Tanggal kembali **atau** status/catatan bebas (`K`, `KEMBALI`, `SDH KEMBALI`, `SDH BALIK`, `GANTI TABUNG`, dll.) | `Cycle.returned_at` (nullable) + `LifecycleEvent` bertipe `RETURNED`/`EXCHANGED`/`LOST` + `Cycle.close_reason`/`note` terpisah | `K`/`KEMBALI`/`SDH KEMBALI` -> event `RETURNED` dengan `occurred_at = NULL` dan flag `date_unknown = true` (bukan tanggal impor). `SDH BALIK` dan kode lain: `NEEDS_REVIEW` (MIG-B05, `PENDING`) |
| F | F | `Jenis Gas` | Jenis gas resmi + kode tambahan campur; 165 nilai unik (trim), 80,2% kosong | `GasType` (5 resmi: O2, AR, C2H2, N2, CO2) via FK, atau `NULL` + `data_quality_flag = NEEDS_REVIEW` | Kode di luar 5 resmi (BBS, MR, TOB, SA, TIRA, ABG, SMB, TR, UHP, dst.) **tidak** dipetakan otomatis ke gas resmi (DEC-003/DEC-004, `CONFIRMED`); tetap `NEEDS_REVIEW` sampai MIG-B07/B08 dijawab |

## Field tambahan yang tidak berasal dari kolom manapun (wajib ada di model baru)

| Field baru | Alasan |
| --- | --- |
| `RawRow.id` (UUID), `RawRow.source_row_number`, `RawRow.raw_json` (enam nilai asli + tipe sel) | Traceability wajib (prinsip wajib requirements.md #2); kunci unik = file hash + sheet + source row |
| `ImportBatch.id`, `ImportBatch.workbook_sha256` | Mengikat setiap raw row ke snapshot workbook tertentu (checksum di `docs/source-audit.md`) |
| `SourceLink` (raw_row_id -> event_id, many-to-many) | Satu raw row bisa menghasilkan >1 event (kirim + kembali); beberapa raw row bisa dipetakan ke satu hasil yang disetujui (F4) |
| `StagingRow.parser_rule`, `.parser_version`, `.confidence`, `.warning`, `.error` | Wajib per Panduan bagian 04; parser tanggal sudah terbukti perlu versi eksplisit (lihat perbedaan hasil parse di `docs/source-audit.md`) |
| `ReviewDecision` (siapa, kapan, alasan, nilai sebelum/sesudah) | FR-08, FR-11: audit koreksi wajib beralasan |
| `Cylinder.id` (UUID, internal PK) | DEC-001/ADR-P013: `Nomor` Excel tidak aman jadi PK |
| `Cycle.status`, `Cycle.data_quality_flag` | Memisahkan status siklus (AVAILABLE/OUT/...) dari kualitas data migrasi (NEEDS_REVIEW), sesuai Panduan bagian 02 |

## Yang eksplisit TIDAK dipetakan otomatis

- Kode tambahan Jenis Gas (BBS, MR, TOB, SA, TIRA, ABG, SMB, TR, UHP, dll.) tidak ditebak sebagai
  gas resmi, ukuran, tekanan, pemasok, atau lokasi - masih `PENDING` (MIG-B07, MIG-B08).
- `SDH BALIK` dan status bebas lain di luar `K`/`KEMBALI`/`SDH KEMBALI` tidak dipetakan ke
  `RETURNED` secara otomatis - `PENDING` (MIG-B05).
- Nama relasi yang mirip tapi tidak identik setelah normalisasi tidak digabung otomatis - selalu
  kandidat review (FR-03, DEC-002).

Dokumen ini adalah draft mapping untuk direview sebelum F2 (skema) dan F3 (importer) dibangun;
belum ada migrasi yang dijalankan.
