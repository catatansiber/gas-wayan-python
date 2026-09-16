"""Parser terkontrol untuk sheet Database - fungsi murni, tidak menyentuh Django ORM/DB,
supaya mudah difixture-test (lihat docs/migration-policy.md B1-B3, MIG-P06).

Aturan wajib (tidak boleh dilanggar tanpa keputusan bisnis baru):
- Tidak pernah menebak tanggal ambigu/mustahil (requirements.md prinsip wajib #9/A5).
- Hanya day-first (`d[/.-]m[/.-]y`) yang diterima - baseline MIG-B13, day-first konservatif.
- Tahun 2 digit: 00-68 -> 20xx, 69-99 -> 19xx (konvensi `strptime('%y')` Python) - PROPOSAL,
  belum dikonfirmasi pemilik proyek (lihat docs/reports/F3.md), hanya memengaruhi staging.
- `K`/`KEMBALI`/`SDH KEMBALI` -> RETURNED terkonfirmasi (A4). `SDH BALIK` dan teks lain TIDAK
  dipetakan otomatis (MIG-B05, PENDING) - selalu NEEDS_REVIEW.
"""

import datetime
import re

PARSER_VERSION = "F3-PARSER-v1"

OFFICIAL_GAS_CODES = {"O2", "AR", "C2H2", "N2", "CO2"}

RETURNED_KEYWORDS = {"K", "KEMBALI", "SDH KEMBALI"}
SDH_BALIK_KEYWORD = "SDH BALIK"

_DATE_TEXT_RE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})$")

_WS_RE = re.compile(r"\s+")


def trim(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_customer_name(raw_trimmed: str) -> str:
    """Trim + uppercase + collapse spasi ganda - dipakai untuk kandidat alias (FR-03)."""
    return _WS_RE.sub(" ", raw_trimmed.upper()).strip()


def expand_two_digit_year(yy: int) -> int:
    return 2000 + yy if yy <= 68 else 1900 + yy


def parse_date_text(raw_trimmed: str) -> datetime.date | None:
    """Parse teks tanggal day-first ketat. Mengembalikan None bila tidak sesuai pola atau
    nilainya mustahil (mis. bulan 13) - tidak pernah menebak."""
    match = _DATE_TEXT_RE.match(raw_trimmed)
    if not match:
        return None
    day_s, month_s, year_s = match.groups()
    day, month = int(day_s), int(month_s)
    year = int(year_s) if len(year_s) == 4 else expand_two_digit_year(int(year_s))
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


class DateCellResult:
    __slots__ = ("value", "is_native", "raw_text")

    def __init__(self, value, is_native, raw_text):
        self.value = value
        self.is_native = is_native
        self.raw_text = raw_text

    @property
    def parseable(self) -> bool:
        return self.value is not None


def parse_date_cell(cell_value) -> DateCellResult:
    """Terima nilai mentah sel openpyxl (native datetime/date, teks, angka, atau None)."""
    if isinstance(cell_value, datetime.datetime):
        return DateCellResult(cell_value.date(), True, cell_value.isoformat())
    if isinstance(cell_value, datetime.date):
        return DateCellResult(cell_value, True, cell_value.isoformat())
    raw_trimmed = trim(cell_value)
    if not raw_trimmed:
        return DateCellResult(None, False, raw_trimmed)
    parsed = parse_date_text(raw_trimmed)
    return DateCellResult(parsed, False, raw_trimmed)


class ReturnColumnResult:
    """Hasil klasifikasi kolom E (`Tanggal Pengembalian` - tanggal ATAU status bebas)."""

    __slots__ = ("status", "date", "date_unknown", "is_native", "raw_text")

    def __init__(self, status, date, date_unknown, is_native, raw_text):
        self.status = status
        self.date = date
        self.date_unknown = date_unknown
        self.is_native = is_native
        self.raw_text = raw_text


def classify_return_cell(cell_value) -> ReturnColumnResult:
    from imports.models import StagingRow

    ReturnStatus = StagingRow.ReturnStatus

    if isinstance(cell_value, datetime.datetime | datetime.date):
        date_result = parse_date_cell(cell_value)
        return ReturnColumnResult(
            ReturnStatus.DATE, date_result.value, False, True, date_result.raw_text
        )

    raw_trimmed = trim(cell_value)
    if not raw_trimmed:
        return ReturnColumnResult(ReturnStatus.NONE, None, False, False, raw_trimmed)

    parsed_date = parse_date_text(raw_trimmed)
    if parsed_date is not None:
        return ReturnColumnResult(ReturnStatus.DATE, parsed_date, False, False, raw_trimmed)

    upper = raw_trimmed.upper()
    if upper in RETURNED_KEYWORDS:
        status = {
            "K": ReturnStatus.K,
            "KEMBALI": ReturnStatus.KEMBALI,
            "SDH KEMBALI": ReturnStatus.SDH_KEMBALI,
        }[upper]
        return ReturnColumnResult(status, None, True, False, raw_trimmed)
    if upper == SDH_BALIK_KEYWORD:
        return ReturnColumnResult(ReturnStatus.SDH_BALIK, None, False, False, raw_trimmed)
    return ReturnColumnResult(ReturnStatus.OTHER_TEXT, None, False, False, raw_trimmed)


def match_gas_code(raw_trimmed: str) -> tuple[str, bool]:
    upper = raw_trimmed.upper()
    if upper in OFFICIAL_GAS_CODES:
        return upper, True
    return "", False


def build_dedupe_key(serial_number_raw: str, sent_at_raw: str, returned_at_raw: str) -> str:
    """Kunci kandidat duplikat bisnis, mengabaikan kolom `Nomor` (B3) - dibandingkan atas
    nilai mentah kolom tanggal, bukan hasil parse (lihat perbedaan metodologi di
    docs/source-audit.md bagian 4)."""
    if not serial_number_raw:
        return ""
    return "|".join(
        [
            normalize_customer_name(serial_number_raw),
            sent_at_raw.strip().upper(),
            returned_at_raw.strip().upper(),
        ]
    )


def cell_type_label(value) -> str:
    if value is None:
        return "blank"
    if isinstance(value, datetime.datetime | datetime.date):
        return "date"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    return "string"


def cell_to_json(value):
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    return value


def sanitize_csv_cell(value: str) -> str:
    """Cegah formula injection pada ekspor CSV (phase-plan F3 kerja)."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
