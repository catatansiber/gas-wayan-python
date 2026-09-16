"""Form Django untuk layar operasional F5. Validasi di sini adalah pre-check UX (pesan
Bahasa Indonesia, cepat, tanpa query lock) - keputusan bisnis sesungguhnya (constraint,
role, idempotency) tetap ditegakkan `operations.services` (satu-satunya jalur mutasi)."""

from django import forms
from django.utils import timezone

from catalog.models import Customer, GasType

REQUIRED_MSG = "Wajib diisi."
INVALID_DATE_MSG = "Tanggal tidak sah."


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
    customer = forms.ModelChoiceField(
        label="Pelanggan",
        queryset=Customer.objects.filter(is_active=True).order_by("display_name"),
        error_messages={"required": REQUIRED_MSG, "invalid_choice": "Pelanggan tidak ditemukan."},
    )
    gas_type_code = forms.ChoiceField(label="Jenis gas", error_messages={"required": REQUIRED_MSG})
    sent_at = _date_field("Tanggal kirim")

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
    customer = forms.ModelChoiceField(
        label="Pelanggan/relasi",
        queryset=Customer.objects.filter(is_active=True).order_by("display_name"),
        error_messages={"required": REQUIRED_MSG, "invalid_choice": "Pelanggan tidak ditemukan."},
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
    customer = forms.ModelChoiceField(
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
