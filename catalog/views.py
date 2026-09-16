from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from identity.models import Role
from identity.permissions import role_required

from .forms import CustomerForm, GasTypeForm
from .models import Customer, GasType


@role_required(Role.ADMIN)
def customer_list(request):
    return render(request, "catalog/customer_list.html", {"customers": Customer.objects.all()})


@role_required(Role.ADMIN)
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Pelanggan/relasi ditambahkan.")
        return redirect("catalog:customers")
    return render(
        request, "catalog/master_form.html", {"form": form, "title": "Tambah pelanggan/relasi"}
    )


@role_required(Role.ADMIN)
def customer_edit(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Pelanggan/relasi diperbarui.")
        return redirect("catalog:customers")
    return render(
        request,
        "catalog/master_form.html",
        {"form": form, "title": f"Ubah pelanggan/relasi: {customer.display_name}"},
    )


@role_required(Role.ADMIN)
def customer_delete(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    if request.method == "POST":
        try:
            customer.delete()
        except ProtectedError:
            messages.error(
                request,
                "Pelanggan yang sudah memiliki transaksi tidak dapat dihapus. Nonaktifkan saja.",
            )
        else:
            messages.success(request, "Pelanggan/relasi dihapus.")
        return redirect("catalog:customers")
    return render(request, "catalog/customer_confirm_delete.html", {"customer": customer})


@role_required(Role.ADMIN)
def gas_type_list(request):
    return render(
        request, "catalog/gas_type_list.html", {"gas_types": GasType.objects.order_by("code")}
    )


@role_required(Role.ADMIN)
def gas_type_create(request):
    form = GasTypeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Jenis gas ditambahkan.")
        return redirect("catalog:gas-types")
    return render(request, "catalog/master_form.html", {"form": form, "title": "Tambah jenis gas"})
