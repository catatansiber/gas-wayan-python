from django import template

register = template.Library()

LABELS = {
    "DISPATCHED": "Dikirim",
    "RETURNED": "Kembali",
    "EXCHANGED_OUT": "Ditukar keluar",
    "EXCHANGED_IN": "Ditukar masuk",
    "LOST": "Hilang",
    "MAINTENANCE_STARTED": "Mulai maintenance",
    "MAINTENANCE_COMPLETED": "Selesai maintenance",
    "RETIRED": "Pensiun",
    "REVERSED": "Dibatalkan",
    "CORRECTED": "Riwayat dikoreksi",
}


@register.filter
def event_label(value):
    return LABELS.get(value, value)
