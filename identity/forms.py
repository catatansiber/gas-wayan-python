from django import forms

from .models import Role, User


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("role", "is_active")
        labels = {"role": "Role", "is_active": "Akun aktif"}

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.instance.is_superuser and role != Role.ADMIN:
            raise forms.ValidationError("Akun superadmin harus tetap memiliki role Admin.")
        return role
