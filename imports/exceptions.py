class ImportError_(Exception):
    """Base error importer. Nama `ImportError_` menghindari bentrok builtin `ImportError`."""


class ChecksumMismatch(ImportError_):
    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checksum workbook tidak cocok - expected={expected} actual={actual}. "
            "Import dibatalkan, tidak ada RawRow/StagingRow ditulis."
        )


class SheetNotFound(ImportError_):
    def __init__(self, sheet_name: str):
        self.sheet_name = sheet_name
        super().__init__(f"Sheet '{sheet_name}' tidak ditemukan di workbook.")
