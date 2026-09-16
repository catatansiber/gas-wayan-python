# Gas Wayan Python

Fondasi modular monolith Django untuk sistem operasional tabung Gas Wayan. Menggantikan stack
TypeScript lama (`../Gas Wayan/`) - lihat `docs/decisions.md` (ADR-P001). Web memakai Django
Templates, PostgreSQL adalah source of truth, worker Python + Telegram Bot API menyusul di F6.

Status implementasi saat ini: **F1 - fondasi** (login, role, health check). Fitur operasional
(kirim/kembali/dsb.) belum ada - lihat `docs/phase-plan.md`.

## Prasyarat

- Python 3.13.15 ([python.org](https://www.python.org/downloads/) atau
  `winget install --id Python.Python.3.13 --version 3.13.15`)
- Docker Desktop (untuk PostgreSQL lokal) - **bukan** `../Gas Wayan/compose.yaml` lama
- PowerShell (Windows)

Proyek ini **tidak** memakai `.env`, secret, atau Docker Compose milik `../Gas Wayan/` (proyek
TypeScript lama). Keduanya berjalan berdampingan tanpa bentrok port (lihat tabel port di bawah).

## Setup dari checkout bersih

```powershell
# 1. Buat dan aktifkan virtual environment
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instal dependency terkunci (lock file, verifikasi hash)
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.txt
pip install --require-hashes -r requirements-dev.txt

# 3. Salin file environment (tanpa secret asli)
Copy-Item .env.example .env

# 4. Jalankan PostgreSQL lokal (proyek ini, terpisah dari proyek lama)
docker compose up -d postgres

# 5. Migrasi database
python manage.py migrate

# 6. Buat akun Admin pertama (interaktif - TIDAK ada password hardcoded)
python manage.py createsuperuser

# 7. Jalankan server development
python manage.py runserver
```

Buka `http://127.0.0.1:8000/` - akan diarahkan ke halaman login. Login dengan akun Admin dari
langkah 6, lalu akan diarahkan ke dashboard. Health check publik ada di
`http://127.0.0.1:8000/health/`.

Berhenti: `Ctrl+C` di terminal `runserver`, lalu `docker compose down` (tambahkan `-v` hanya jika
sengaja ingin menghapus data PostgreSQL lokal).

## Port dan nama, dan cara memastikan tidak bentrok dengan proyek lama

| Layanan | Proyek ini (gas-wayan-python) | Proyek lama (`../Gas Wayan/`) |
| --- | --- | --- |
| Django dev server | `127.0.0.1:8000` | API NestJS di `:3001`, web Next.js di `:3000` (tidak dipakai lagi) |
| PostgreSQL (host) | `localhost:55432` (compose project `gas-wayan-python`, DB `gaswayan_dev`) | `localhost:5432` (compose project `gas-wayan`, DB `gas_wayan`) |

Kedua Postgres boleh menyala bersamaan (`docker compose ps` di masing-masing folder menunjukkan
container terpisah). Jalankan `docker compose ps` di folder ini untuk memastikan hanya container
`gas-wayan-python-postgres-1` yang relevan.

## Perintah sehari-hari

| Kebutuhan | Perintah |
| --- | --- |
| Instal dependency (setelah `requirements*.in` berubah) | `scripts/compile_requirements.ps1` lalu `pip install --require-hashes -r requirements.txt -r requirements-dev.txt` |
| Infrastruktur (PostgreSQL) | `docker compose up -d postgres` |
| Buat migrasi baru | `python manage.py makemigrations` |
| Terapkan migrasi | `python manage.py migrate` |
| Development server | `python manage.py runserver` |
| Lint | `ruff check .` |
| Format (cek saja) | `ruff format --check .` |
| Format (terapkan) | `ruff format .` |
| Test (PostgreSQL nyata, bukan SQLite) | `python manage.py test --settings=config.settings.test` |
| System check | `python manage.py check` |
| Cek migrasi hilang | `python manage.py makemigrations --check --dry-run` |
| Audit workbook read-only (F0) | lihat `docs/demo/F0.md` |

## Struktur setting

`config/settings/{base,dev,test,prod}.py` - lihat `CLAUDE.md` untuk aturan tiap file. `prod.py`
mewajibkan `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, dan `DATABASE_URL` dari environment (tidak
ada default) dan **selalu** `DEBUG = False` (bukan dibaca dari env), supaya konfigurasi produksi
tidak bisa tertukar jadi `DEBUG=True` akibat `.env` yang salah.

## Role

`ADMIN`, `OPERATOR`, `VIEWER` (lihat `identity/models.py`, `identity/permissions.py`). Akses
diperiksa di server lewat dekorator `role_required`, bukan hanya menyembunyikan tautan di
template. `python manage.py createsuperuser` selalu membuat akun berrole `ADMIN`.

## Catatan keamanan

- `SERI TABUNG.xlsm` (`../SERI TABUNG.xlsm`) selalu read-only - lihat `docs/source-audit.md`.
- Jangan commit `.env`, token, password produksi, hasil impor, atau data pelanggan.
- Jangan menyalin `.env`/Compose dari `../Gas Wayan/` ke proyek ini.
