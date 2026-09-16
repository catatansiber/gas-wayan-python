from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("pelanggan/", views.customer_list, name="customers"),
    path("pelanggan/tambah/", views.customer_create, name="customer-create"),
    path("pelanggan/<uuid:customer_id>/ubah/", views.customer_edit, name="customer-edit"),
    path("pelanggan/<uuid:customer_id>/hapus/", views.customer_delete, name="customer-delete"),
    path("jenis-gas/", views.gas_type_list, name="gas-types"),
    path("jenis-gas/tambah/", views.gas_type_create, name="gas-type-create"),
]
