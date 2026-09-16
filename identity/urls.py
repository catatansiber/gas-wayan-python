from django.urls import path

from . import views

app_name = "identity"

urlpatterns = [
    path("login/", views.GasWayanLoginView.as_view(), name="login"),
    path("logout/", views.GasWayanLogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("admin-only/", views.admin_only, name="admin-only"),
    path("akun/role/", views.user_role_list, name="user-roles"),
    path("akun/<int:user_id>/role/", views.user_role_edit, name="user-role-edit"),
]
