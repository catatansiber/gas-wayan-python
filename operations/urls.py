from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("cari/", views.search_cylinders, name="search"),
    path("log/", views.usage_log, name="usage-log"),
    path("tabung/<str:serial_number>/", views.cylinder_detail, name="cylinder-detail"),
    path("siklus/<uuid:cycle_id>/ubah/", views.correct_cycle_view, name="correct-cycle"),
    path(
        "siklus/<uuid:cycle_id>/hapus/",
        views.delete_cycle_history_view,
        name="delete-cycle-history",
    ),
    path("kirim/", views.dispatch_view, name="dispatch"),
    path("kembali/", views.return_view, name="return"),
    path("admin/tukar/", views.exchange_view, name="exchange"),
    path("admin/hilang/", views.lost_view, name="lost"),
    path("admin/maintenance/mulai/", views.maintenance_start_view, name="maintenance-start"),
    path(
        "admin/maintenance/selesai/",
        views.maintenance_complete_view,
        name="maintenance-complete",
    ),
]
