# Progress - gas-wayan-python

Status per fase memakai `TODO -> IN_PROGRESS -> READY_FOR_REVIEW -> ACCEPTED`, atau `BLOCKED`
dengan alasan, dampak, dan siapa yang perlu memutuskan. `ACCEPTED` hanya diberikan pemilik
proyek setelah demo dan bukti tes, bukan keputusan sepihak Claude Code.

```text
F0 | ACCEPTED (via instruksi eksplisit "Kerjakan F1 saja" - pemilik proyek tidak mengirim
      kalimat "Saya menerima F0" secara harfiah, tapi instruksi lanjut ke F1 dianggap
      persetujuan implisit) | 5/5 checks
Artefak: CLAUDE.md, docs/phase-plan.md, docs/decisions.md, docs/source-audit.md,
         docs/column-mapping.md, docs/migration-policy.md,
         docs/migration-decisions-pending.md, scripts/audit_workbook.ps1,
         docs/reports/f0-audit-raw.json, docs/reports/F0.md, docs/demo/F0.md
Tes: scripts/audit_workbook.ps1 (checksum match, idempotency, deteksi perubahan file) -
     lihat docs/reports/F0.md bagian "Tes yang dijalankan" untuk hasil dan exit criteria
Data: raw=10597; kosong=540; nomor_unik=7036; tabung_unik=2450; relasi_unik=1288;
      checksum cocok = D96FC4E7366BFC9B38CBD2BEB6985CAB361BCA9E1D36CFAED5DD1FFDDFA33B81
Bukti: docs/reports/F0.md, docs/reports/f0-audit-raw.json, docs/demo/F0.md
Risiko: 20 pertanyaan bisnis warisan + 4 NFR masih PENDING; 3 keputusan arsitektur
        Python (MIG-P01/P02/P03) + 4 usulan kebijakan migrasi (B1-B4 di
        migration-policy.md) belum dikonfirmasi pemilik; parser tanggal skrip audit
        lebih ketat dari audit lama (MIG-P06, hanya relevan untuk F3)
Next: pemilik proyek jalankan docs/demo/F0.md, review dokumen, lalu kirim "Saya
      menerima F0" atau minta revisi sebelum F1 dimulai

F1 | ACCEPTED (via instruksi eksplisit "Kerjakan F2 saja") | 7/7 checks
Artefak: config/settings/{base,dev,test,prod}.py, docker-compose.yml, .env.example,
         requirements(.in|.txt)/requirements-dev(.in|.txt), scripts/compile_requirements.ps1,
         identity/ (User+Role, permissions, views, templates, 9 tes),
         health/ (view + 1 tes), pyproject.toml (ruff), .github/workflows/ci.yml,
         README.md, docs/demo/F1.md, docs/reports/F1.md
Tes: 11/11 lulus (manage.py test --settings=config.settings.test, PostgreSQL nyata);
     ruff check + ruff format --check bersih; migrate 19 migrasi OK; checkout bersih
     diverifikasi ulang di direktori terpisah (hash-verified install, migrate, lint,
     test semua lulus) - lihat docs/reports/F1.md bagian "Tes yang dijalankan"
Data: Python 3.13.15; Django 5.2.17 LTS; psycopg 3.3.5; PostgreSQL 18.6-alpine;
      port Postgres host 55432 (proyek lama pakai 5432, tidak bentrok)
Bukti: docs/reports/F1.md, docs/demo/F1.md
Risiko: MIG-P01 (antrean Telegram) dan MIG-P04 (target deployment) masih PENDING,
        tidak memblokir F2; CI belum pernah jalan di GitHub sungguhan (belum ada
        remote) - langkahnya sudah diverifikasi identik secara lokal
Next: pemilik proyek jalankan docs/demo/F1.md, review docs/reports/F1.md, lalu
      konfirmasi F1 diterima sebelum F2 dimulai

F2 | ACCEPTED (via instruksi eksplisit "Kerjakan F3 saja") | 7/7 checks
Artefak: catalog/ (Customer, CustomerAlias, GasType, Cylinder, admin read-write master),
         operations/ (Cycle, LifecycleEvent, IdempotencyRecord, services.py 8 fungsi,
         exceptions.py, admin read-only), audit/ (AuditLog, OutboxEvent, admin read-only),
         migrasi termasuk CHECK SQL manual (operations 0002), docs/reports/F2.md,
         docs/demo/F2.md
Tes: 51/51 lulus (manage.py test --settings=config.settings.test, PostgreSQL nyata),
     termasuk 3 tes concurrency berbasis thread sungguhan (TransactionTestCase);
     2 constraint DB (CHECK + partial unique index) diverifikasi manual lewat INSERT
     SQL mentah yang melewati Python - lihat docs/reports/F2.md
Data: satu siklus aktif/tabung ditegakkan constraint DB, bukan hanya Python;
      7 operasi domain: kirim, kembali, tukar, hilang, maintenance, pensiun, reversal
Bukti: docs/reports/F2.md, docs/demo/F2.md
Risiko: MIG-P09 (baru) - reversal hanya cover DISPATCH, belum RETURNED/EXCHANGED/LOST;
        belum ada UI (disengaja, F2 berhenti sebelum layar operasional)
Next: pemilik proyek jalankan docs/demo/F2.md, review docs/reports/F2.md, lalu
      konfirmasi F2 diterima sebelum F3 dimulai

F3 | ACCEPTED (via instruksi eksplisit "Kerjakan F4 saja") | 6/6 checks
Artefak: imports/ (ImportBatch, RawRow, StagingRow, parsing.py, importer.py, admin read-only),
         management command import_workbook (--dry-run, idempotent) dan import_report
         (ringkasan agregat aman + laporan detail lokal), openpyxl==3.1.5 dipin (MIG-P07
         selesai), docs/reports/F3.md, docs/reports/f3-import-summary.json, docs/demo/F3.md
Tes: 76/76 lulus (51 lama + 25 baru, manage.py test --settings=config.settings.test), termasuk
     tanggal campuran/mustahil, status K/KEMBALI/SDH KEMBALI/SDH BALIK/teks bebas, kode gas tak
     ditebak, checksum mismatch dibatalkan total, dry-run rollback total, re-run idempotent;
     dijalankan sungguhan 2x terhadap SERI TABUNG.xlsm asli - lihat docs/reports/F3.md
Data: raw fisik=11.137 (10.597 berisi data + 540 kosong, PERSIS cocok F0); re-run kedua:
      0 raw/staging baru (idempotent); checksum tetap D96FC4E7...FDDFA33B81 sebelum/sesudah
      (diverifikasi sha256sum eksternal); baris 10.599-10.601 dikonfirmasi berisi data
Bukti: docs/reports/F3.md, docs/reports/f3-import-summary.json, docs/demo/F3.md
Risiko: MIG-P06 (parser tanggal) diisi PROPOSAL F3-PARSER-v1, masih PENDING konfirmasi pemilik
        sebelum F4; MIG-B05/B07/B08 tetap PENDING (SDH BALIK dan kode gas tambahan tidak
        ditebak); INSIDEN: 3 nama pelanggan asli sempat tercetak ke log percakapan sesi ini
        saat spot-check file lokal (tidak masuk Git, tapi masuk transkrip sesi) - lihat
        docs/reports/F3.md bagian insiden
Next: pemilik proyek jalankan docs/demo/F3.md, review docs/reports/f3-local/*.csv (lokal),
      putuskan proposal parser tanggal dan insiden log, lalu konfirmasi F3 diterima sebelum F4

F4 | ACCEPTED (via instruksi eksplisit "Kerjakan F5 saja") | 7/7 checks
Artefak: imports.PublishBatch/SourceLink/ReviewDecision, StagingRow.publish_outcome,
         imports/publisher.py (publish atomic per kelompok tabung, resume, exclude beralasan),
         Django Admin StagingRow (preview mapping + aksi exclude wajib alasan), command
         publish_staging dan reconcile_report, catalog.CustomerAlias.normalized_value,
         docs/reports/F4.md, docs/reports/f4-publish-summary.json, docs/demo/F4.md
Tes: 88/88 lulus (76 lama + 12 baru F4: crash/resume, re-run idempotent, duplikat bisnis
     (terdeteksi sbg overlap kronologi) diblokir sampai dikecualikan, rollback total per
     kelompok saat error di tengah jalan, rekonsiliasi raw=published+pending+excluded, role,
     kebijakan PENDING tetap memblokir - lihat docs/reports/F4.md untuk nama tes lengkap
Data: dijalankan sungguhan 2x publish_staging + reconcile_report terhadap 10.597 StagingRow
      nyata dari F3 (database dev/staging lokal saja): run1 48 kelompok/56 baris publish,
      run2 0 baru (idempotent); rekonsiliasi 10.597 = 56 PUBLISHED + 10.541 PENDING_REVIEW +
      0 EXCLUDED_APPROVED (cocok persis); 0 event IMPORT yatim; arsip raw tetap 11.137 baris
Bukti: docs/reports/F4.md, docs/reports/f4-publish-summary.json, docs/demo/F4.md
Risiko: mayoritas (10.541/10.597) tetap PENDING_REVIEW - SESUAI DESAIN karena kebijakan
        B1/B2/B3 belum disahkan pemilik; MIG-P09 tetap memblokir undo publish setelah commit;
        2.403 kelompok diblokir bisa jadi karena SATU baris bermasalah dalam riwayat satu
        tabung (B3: seluruh kelompok ikut tertahan, bukan hanya baris bermasalahnya)
Next: pemilik proyek jalankan docs/demo/F4.md, review layar Admin StagingRow dan
      docs/reports/F4.md, putuskan kebijakan B1/B2/B3, lalu konfirmasi F4 diterima sebelum F5

F5 | ACCEPTED (via instruksi eksplisit "Kerjakan F7 saja", pemilik memilih F7 web-only
      sebelum F6) | 6/6 checks
Artefak: operations/forms.py (7 form, validasi Bahasa Indonesia eksplisit), operations/views.py
         (pola generik form->preview->konfirmasi, idempotency key per preview), operations/urls.py,
         6 template baru (search/cylinder_detail/usage_log/operation_form/operation_preview/
         _pagination), templates/base.html dirombak responsif 360px-desktop, catalog.Cylinder
         .latest_cycle (properti, tanpa migrasi), docs/reports/F5.md, docs/demo/F5.md
Tes: 109/109 lulus (88 lama + 21 baru operations.test_views: role, alur normal kirim->kembali,
     input salah, hasil kosong, idempotency double-click, pagination server-side 2 halaman,
     timezone Asia/Makassar +8 jam dari UTC dibuktikan lewat string HTML); ruff+migrations
     bersih; DIVERIFIKASI TAMBAHAN lewat curl sungguhan ke dev server nyata (login, cari,
     kirim, preview, 2x konfirmasi/double-click, detail) - lihat docs/reports/F5.md
Data: 21 tes view baru; double-click via curl nyata: Cycle.count() tetap 1 setelah 2x POST
      konfirmasi identik; pagination 25 tabung -> 20+5, tanpa tumpang tindih
Bukti: docs/reports/F5.md, docs/demo/F5.md
Risiko: tidak ada tangkapan layar visual (tidak ada alat screenshot di lingkungan kerja) -
        verifikasi CSS responsif lewat pembacaan kode, bukan render visual; pemilik proyek
        disarankan buka docs/demo/F5.md di browser sungguhan sebagai langkah terakhir; ekspor
        dan dashboard ringkas belum dibangun (di luar scope instruksi sesi ini, format ekspor
        belum disetujui); select pelanggan sederhana (bukan autocomplete), cukup untuk skala
        Customer saat ini
Next: pemilik proyek jalankan docs/demo/F5.md di browser sungguhan (termasuk cek 360px),
      lalu konfirmasi F5 diterima sebelum F6 (bot Telegram) dimulai

F6 | TODO (SENGAJA DILOMPATI sementara - pemilik proyek memilih "F7 web-only dulu" saat
      diminta konfirmasi sebelum F7 dimulai; bot Telegram belum ada) | 0/? checks
Next: dikerjakan setelah F7 web direview; cakupan bot dari F7 (end-to-end web/bot, load bot)
      perlu disusulkan sebagai sesi tambahan setelah F6 selesai, sebelum F8

F7 | READY_FOR_REVIEW (cakupan WEB saja - lihat F6 di atas) | 6/6 checks (web)
Artefak: identity/throttle.py (rate limit login 5x/5menit per IP+username, cache framework),
         GasWayanLoginView diperbarui, config/settings/prod.py +HSTS (SECURE_HSTS_SECONDS/
         INCLUDE_SUBDOMAINS, PRELOAD sengaja False), operations/test_concurrency_web.py
         (5 user bersamaan lewat HTTP), operations/management/commands/perf_benchmark.py,
         docs/reports/F7.md, docs/reports/f7-performance.json, docs/demo/F7.md
Tes: 114/114 lulus (109 lama + 5 baru: 3 LoginRateLimitTests + 2 WebConcurrencyTests);
     manage.py check --deploy bersih (1 WARNING sengaja: HSTS preload); ruff+migrations bersih
Data: concurrency 5 Operator dispatch tabung sama lewat HTTP - tepat 1 sukses, 1 Cycle;
      backup/restore drill sungguhan (pg_dump+pg_restore) - 7 tabel kunci cocok persis
      (11.137 imports_rawrow, dst.), database+dump sementara dihapus setelah drill;
      performa 20.000 Cycle sintetis - p95 tertinggi 38,9ms (cari per pelanggan), jauh di
      bawah target lama 1000ms (BELUM disahkan, bukan klaim kapasitas 5 juta event)
Bukti: docs/reports/F7.md (matriks UAT 18 skenario), docs/reports/f7-performance.json,
       docs/demo/F7.md
Risiko: end-to-end bot BLOCKED menunggu F6; load test hanya skala 20rb (bukan 5 juta) dengan
        disclaimer eksplisit; rehearsal restore baru di instance Postgres yang sama (lintas-
        mesin menyusul F8); HSTS preload sengaja belum aktif
Next: pemilik proyek review docs/demo/F7.md dan docs/reports/F7.md, konfirmasi F7 web
      diterima, lalu putuskan jadwal F6 (bot Telegram) sebelum F8

F8 | TODO | 0/? checks
Next: menunggu ACCEPTED F6 (bot) dan F7 (termasuk cakupan bot yang masih tertunda)
```

Detail exit gate tiap fase: lihat `docs/phase-plan.md`. Detail item PENDING: lihat
`docs/migration-decisions-pending.md`.
