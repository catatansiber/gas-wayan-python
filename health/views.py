from django.db import connection
from django.http import JsonResponse


def health(request):
    """Health check publik (tanpa auth) - dipakai monitoring/orchestrator. Memeriksa koneksi
    database sungguhan, bukan hanya menjawab 200 tanpa memeriksa apa pun."""
    db_ok = True
    db_error = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover - jalur kegagalan infrastruktur
        db_ok = False
        db_error = str(exc)

    status = "ok" if db_ok else "error"
    payload = {"status": status, "database": "ok" if db_ok else "error"}
    if db_error:
        payload["database_error"] = db_error

    return JsonResponse(payload, status=200 if db_ok else 503)
