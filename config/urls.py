"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("health.urls")),
    path("operasi/", include("operations.urls")),
    path("master/", include("catalog.urls")),
    path("", include("identity.urls")),
]
