from django.test import Client, TestCase
from django.urls import reverse

from .models import Role, User


class RoleAccessTests(TestCase):
    """Bukti acceptance F1: role diuji otomatis, akses terlarang ditolak SERVER, bukan hanya UI."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin1", password="pass12345!", role=Role.ADMIN
        )
        cls.operator = User.objects.create_user(
            username="operator1", password="pass12345!", role=Role.OPERATOR
        )
        cls.viewer = User.objects.create_user(
            username="viewer1", password="pass12345!", role=Role.VIEWER
        )

    def test_admin_can_login_and_reach_dashboard(self):
        client = Client()
        ok = client.login(username="admin1", password="pass12345!")
        self.assertTrue(ok)
        response = client.get(reverse("identity:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin1")

    def test_operator_can_login_and_reach_dashboard(self):
        client = Client()
        self.assertTrue(client.login(username="operator1", password="pass12345!"))
        response = client.get(reverse("identity:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_viewer_can_login_and_reach_dashboard(self):
        client = Client()
        self.assertTrue(client.login(username="viewer1", password="pass12345!"))
        response = client.get(reverse("identity:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_login_rejects_wrong_password(self):
        client = Client()
        ok = client.login(username="admin1", password="wrong-password")
        self.assertFalse(ok)

    def test_admin_can_reach_admin_only_page(self):
        client = Client()
        client.login(username="admin1", password="pass12345!")
        response = client.get(reverse("identity:admin-only"))
        self.assertEqual(response.status_code, 200)

    def test_operator_is_denied_admin_only_page_by_server(self):
        client = Client()
        client.login(username="operator1", password="pass12345!")
        response = client.get(reverse("identity:admin-only"))
        self.assertEqual(response.status_code, 403)

    def test_viewer_is_denied_admin_only_page_by_server(self):
        client = Client()
        client.login(username="viewer1", password="pass12345!")
        response = client.get(reverse("identity:admin-only"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login_not_shown_dashboard(self):
        client = Client()
        response = client.get(reverse("identity:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("identity:login"), response.url)

    def test_anonymous_user_is_redirected_to_login_for_admin_only_page(self):
        client = Client()
        response = client.get(reverse("identity:admin-only"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("identity:login"), response.url)


class SuperuserRoleTests(TestCase):
    def test_createsuperuser_forces_admin_role(self):
        user = User.objects.create_superuser(username="root1", password="pass12345!")
        self.assertEqual(user.role, Role.ADMIN)


class LoginRateLimitTests(TestCase):
    """F7: mitigasi brute-force sederhana - lihat identity/throttle.py."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="throttle-target", password="pass12345!", role=Role.VIEWER
        )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_sixth_failed_attempt_is_blocked_even_with_correct_password(self):
        client = Client()
        for _ in range(5):
            response = client.post(
                reverse("identity:login"),
                {"username": "throttle-target", "password": "salah"},
            )
            self.assertEqual(response.status_code, 200)

        response = client.post(
            reverse("identity:login"),
            {"username": "throttle-target", "password": "pass12345!"},
        )
        self.assertContains(response, "Terlalu banyak percobaan")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_successful_login_resets_attempt_counter(self):
        client = Client()
        for _ in range(3):
            client.post(
                reverse("identity:login"),
                {"username": "throttle-target", "password": "salah"},
            )
        ok = client.login(username="throttle-target", password="pass12345!")
        self.assertTrue(ok)

        client2 = Client()
        ok2 = client2.login(username="throttle-target", password="pass12345!")
        self.assertTrue(ok2)

    def test_rate_limit_is_scoped_per_username_not_whole_ip(self):
        User.objects.create_user(username="other-user", password="pass12345!", role=Role.VIEWER)
        client = Client()
        for _ in range(5):
            client.post(
                reverse("identity:login"),
                {"username": "throttle-target", "password": "salah"},
            )
        # IP sama, username BEDA - tidak ikut diblokir.
        other_ok = client.login(username="other-user", password="pass12345!")
        self.assertTrue(other_ok)
