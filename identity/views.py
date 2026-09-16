from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import Cylinder

from . import throttle
from .forms import UserRoleForm
from .models import Role, User
from .permissions import role_required


class GasWayanLoginView(LoginView):
    """Rate limiting F7: 5 percobaan gagal per (IP, username) per 5 menit (cache framework,
    lihat identity/throttle.py) - mitigasi brute-force sederhana tanpa infrastruktur tambahan."""

    template_name = "identity/login.html"

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "")
        if throttle.is_rate_limited(request, username):
            messages.error(
                request, "Terlalu banyak percobaan gagal. Coba lagi dalam beberapa menit."
            )
            return self.render_to_response(self.get_context_data())
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        throttle.register_failed_attempt(self.request, self.request.POST.get("username", ""))
        return super().form_invalid(form)

    def form_valid(self, form):
        throttle.reset_attempts(self.request, self.request.POST.get("username", ""))
        return super().form_valid(form)


class GasWayanLogoutView(LogoutView):
    next_page = "identity:login"


@login_required
def dashboard(request):
    out_count = Cylinder.objects.filter(status=Cylinder.Status.OUT).count()
    return render(
        request, "identity/dashboard.html", {"user": request.user, "out_count": out_count}
    )


@role_required(Role.ADMIN)
def user_role_list(request):
    return render(
        request, "identity/user_role_list.html", {"accounts": User.objects.order_by("username")}
    )


@role_required(Role.ADMIN)
def user_role_edit(request, user_id):
    account = get_object_or_404(User, pk=user_id)
    form = UserRoleForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Role akun diperbarui.")
        return redirect("identity:user-roles")
    return render(request, "identity/user_role_form.html", {"form": form, "account": account})


@role_required(Role.ADMIN)
def admin_only(request):
    """Contoh halaman khusus ADMIN untuk membuktikan penolakan server-side (demo F1). Fungsi
    operasional Admin sesungguhnya (master data, impor, koreksi) dibangun mulai F2-F4."""
    return render(request, "identity/admin_only.html", {"user": request.user})
