from django.contrib import admin

from .models import Customer, CustomerAlias, Cylinder, GasType


class CustomerAliasInline(admin.TabularInline):
    model = CustomerAlias
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("display_name",)
    inlines = [CustomerAliasInline]


@admin.register(GasType)
class GasTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "is_active")
    list_filter = ("is_active",)


@admin.register(Cylinder)
class CylinderAdmin(admin.ModelAdmin):
    """Master tabung boleh dikelola Admin (mis. tambah tabung baru), tapi TIDAK boleh mengubah
    `status` bebas di sini - status hanya berubah lewat operations.services. Field status dibuat
    read-only supaya Admin tidak bisa menimpa status secara manual dari layar ini."""

    list_display = ("serial_number", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("serial_number",)
    readonly_fields = ("status", "created_at", "updated_at")
