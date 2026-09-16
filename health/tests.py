from django.test import Client, TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_endpoint_is_public_and_reports_ok(self):
        client = Client()
        response = client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "ok")
