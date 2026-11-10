"""Form Django untuk layar operasional F5. Validasi di sini adalah pre-check UX (pesan
Bahasa Indonesia, cepat, tanpa query lock) - keputusan bisnis sesungguhnya (constraint,
role, idempotency) tetap ditegakkan `operations.services` (satu-satunya jalur mutasi)."""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from catalog.models import Customer, GasType

REQUIRED_MSG = "Wajib diisi."
INVALID_DATE_MSG = "Tanggal tidak sah."


class CustomerSearchField(forms.ModelChoiceField):
    """Pilih pelanggan dari pencarian nama tanpa memuat dropdown panjang.

    Nilai UUID tetap diterima agar payload halaman konfirmasi yang sudah dibuat tetap valid.
    Saat operator mengetik nama, setiap kata harus ada pada nama pelanggan atau aliasnya.
    Hasil yang tidak unik sengaja ditolak supaya transaksi tidak dikirim ke pelanggan keliru.
    """

    default_error_messages = {
        "required": REQUIRED_MSG,
        "invalid_choice": "Pelanggan tidak ditemukan.",
        "ambiguous": (
            "Ditemukan lebih dari satu pelanggan. Tambahkan kata pencarian atau pilih dari daftar."
        ),
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "class": "input",
                    "list": "customer-options",
                    "placeholder": "Ketik nama pelanggan…",
                    "autocomplete": "off",
                }
            ),
        )
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None

        value = str(value).strip()
        try:
            return self.queryset.get(pk=value)
        except (Customer.DoesNotExist, ValidationError, ValueError, TypeError):
            pass

        # Nama yang persis sama (abaikan huruf besar/kecil dan spasi ganda) menang atas nama
        # lain yang hanya memuatnya, mis. "YONO BAJA" vs "YONO BAJA RINGAN". Bila nama persis
        # sama dimiliki lebih dari satu pelanggan, tetap ambigu dan jatuh ke pencarian kata.
        terms = value.split()
        exact = self.queryset.filter(display_name__iexact=" ".join(terms))
        if exact.count() == 1:
            return exact.first()

        matches = self.queryset
        for term in terms:
            matches = matches.filter(
                Q(display_name__icontains=term) | Q(aliases__raw_value__icontains=term)
            )
        matches = matches.distinct()
        count = matches.count()
        if count == 1:
            return matches.first()
        if count > 1:
            raise forms.ValidationError(self.error_messages["ambiguous"], code="ambiguous")
        raise forms.ValidationError(self.error_messages["invalid_choice"], code="invalid_choice")


def _date_field(label, required=True, help_text=""):
    return forms.DateField(
        label=label,
        required=required,
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={"required": REQUIRED_MSG, "invalid": INVALID_DATE_MSG},
        help_text=help_text,
    )


def _validate_not_future(value):
    if value and value > timezone.localdate():
        raise forms.ValidationError("Tanggal tidak boleh di masa depan.")


def _serial_field(label="Nomor tabung"):
    return forms.CharField(
        label=label,
        max_length=64,
        error_messages={"required": REQUIRED_MSG},
        widget=forms.TextInput(attrs={"placeholder": "mis. 12345"}),
    )


def _reason_field(label="Alasan"):
    return forms.CharField(
        label=label,
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": REQUIRED_MSG},
        help_text="Wajib diisi - tercatat di audit log.",
    )


class SearchForm(forms.Form):
    serial_number = forms.CharField(label="Nomor tabung (exact)", required=False, max_length=64)
    customer = forms.CharField(label="Nama pelanggan (mengandung)", required=False, max_length=255)


class DispatchForm(forms.Form):
    serial_number = _serial_field()
    customer = CustomerSearchField(
        label="Pelanggan",
        queryset=Customer.objects.filter(is_active=True).order_by("display_name"),
        help_text="Ketik satu atau beberapa kata, lalu pilih pelanggan dari daftar.",
    )
    gas_type_code = forms.ChoiceField(label="Jenis gas", error_messages={"required": REQUIRED_MSG})
    sent_at = _date_field("Tanggal kirim")
    # Diisi tersembunyi oleh operation_preview.html hanya ketika halaman preview sudah
    # memberi tahu user bahwa nomor tabung ini belum terdaftar (lihat dispatch_view). Dipakai
    # dispatch_cylinder() sebagai izin eksplisit untuk mendaftarkan tabung baru - tanpa flag
    # ini, tabung yang tidak ditemukan tetap menghasilkan CylinderNotFound seperti biasa.
    confirm_new_cylinder = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gas_type_code"].choices = [
            (gas.code, gas.code) for gas in GasType.objects.filter(is_active=True).order_by("code")
        ]

    def clean_sent_at(self):
        value = self.cleaned_data["sent_at"]
        _validate_not_future(value)
        return value


class ReturnForm(forms.Form):
    serial_number = _serial_field()
    returned_at = _date_field("Tanggal kembali")

    def clean_returned_at(self):
        value = self.cleaned_data["returned_at"]
        _validate_not_future(value)
        return value


class ExchangeForm(forms.Form):
    old_serial_number = _serial_field("Nomor tabung lama")
    new_serial_number = _serial_field("Nomor tabung pengganti")
    customer = CustomerSearchField(
        label="Pelanggan/relasi",
        queryset=Customer.objects.filter(is_active=True).order_by("display_name"),
        help_text="Harus sesuai dengan relasi pada tabung lama yang masih dikirim.",
    )
    exchanged_at = _date_field("Tanggal tukar")

    def clean_exchanged_at(self):
        value = self.cleaned_data["exchanged_at"]
        _validate_not_future(value)
        return value

    def clean(self):
        cleaned = super().clean()
        old = cleaned.get("old_serial_number")
        new = cleaned.get("new_serial_number")
        if old and new and old.strip() == new.strip():
            raise forms.ValidationError("Tabung lama dan tabung pengganti tidak boleh sama.")
        return cleaned


class LostForm(forms.Form):
    serial_number = _serial_field()
    last_customer = forms.CharField(
        label="Relasi terakhir",
        required=False,
        disabled=True,
        help_text="Diisi otomatis dari siklus aktif bila ada.",
    )
    occurred_at = _date_field("Tanggal kejadian")
    reason = _reason_field("Alasan/kronologi hilang")

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        _validate_not_future(value)
        return value


class MaintenanceStartForm(forms.Form):
    serial_number = _serial_field()
    occurred_at = _date_field("Tanggal mulai maintenance")
    reason = _reason_field("Alasan maintenance")

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        _validate_not_future(value)
        return value


class MaintenanceCompleteForm(forms.Form):
    serial_number = _serial_field()
    occurred_at = _date_field("Tanggal selesai maintenance")

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        _validate_not_future(value)
        return value


class RetireForm(forms.Form):
    serial_number = _serial_field()
    occurred_at = _date_field("Tanggal pensiun")
    reason = _reason_field("Alasan pensiun")

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        _validate_not_future(value)
        return value


class ReverseDispatchForm(forms.Form):
    serial_number = _serial_field()
    reason = _reason_field("Alasan koreksi")


class CycleCorrectionForm(forms.Form):
    customer = CustomerSearchField(
        label="Pelanggan/relasi",
        queryset=Customer.objects.filter(is_active=True).order_by("display_name"),
    )
    gas_type_code = forms.ChoiceField(label="Jenis gas", required=False)
    sent_at = _date_field("Tanggal kirim")
    returned_at = _date_field("Tanggal kembali", required=False)
    reason = _reason_field("Alasan perubahan")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gas_type_code"].choices = [("", "-")] + [
            (gas.code, gas.code) for gas in GasType.objects.filter(is_active=True).order_by("code")
        ]

    def clean(self):
        cleaned = super().clean()
        sent_at, returned_at = cleaned.get("sent_at"), cleaned.get("returned_at")
        if sent_at:
            _validate_not_future(sent_at)
        if returned_at:
            _validate_not_future(returned_at)
            if sent_at and returned_at < sent_at:
                self.add_error("returned_at", "Tanggal kembali tidak boleh sebelum tanggal kirim.")
        return cleaned
