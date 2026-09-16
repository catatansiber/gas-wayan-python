from django import forms

from .models import Customer, GasType


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("display_name", "phone_number", "is_active")
        labels = {
            "display_name": "Nama pelanggan/relasi",
            "phone_number": "Nomor telepon",
            "is_active": "Aktif",
        }

    def clean_display_name(self):
        return " ".join(self.cleaned_data["display_name"].split())


class GasTypeForm(forms.ModelForm):
    class Meta:
        model = GasType
        fields = ("code", "is_active")
        labels = {"code": "Kode jenis gas", "is_active": "Aktif"}

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()
