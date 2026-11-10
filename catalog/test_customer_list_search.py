from django.test import TestCase
from django.urls import reverse

from identity.models import Role, User

from .models import Customer, CustomerAlias


class CustomerListSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="cs-admin", password="x", role=Role.ADMIN)
        cls.yono = Customer.objects.create(display_name="YONO BAJA", phone_number="0812")
        cls.toko = Customer.objects.create(display_name="TOKO MAKMUR")
        CustomerAlias.objects.create(customer=cls.toko, raw_value="MAKMUR JAYA LAMA")

    def get(self, **params):
        self.client.force_login(self.admin)
        return self.client.get(reverse("catalog:customers"), params)

    def test_no_query_lists_everyone(self):
        response = self.get()
        self.assertContains(response, "YONO BAJA")
        self.assertContains(response, "TOKO MAKMUR")

    def test_search_by_name_words_any_order_and_case(self):
        response = self.get(q="baja yono")
        self.assertContains(response, "YONO BAJA")
        self.assertNotContains(response, "TOKO MAKMUR")

    def test_search_by_alias(self):
        response = self.get(q="jaya lama")
        self.assertContains(response, "TOKO MAKMUR")
        self.assertNotContains(response, "YONO BAJA")

    def test_search_by_phone(self):
        response = self.get(q="0812")
        self.assertContains(response, "YONO BAJA")
        self.assertNotContains(response, "TOKO MAKMUR")

    def test_no_match_shows_message_and_keeps_query(self):
        response = self.get(q="zzz")
        self.assertContains(response, "Tidak ada pelanggan/relasi yang cocok")
        self.assertContains(response, 'value="zzz"')

    def test_alias_match_does_not_duplicate_rows(self):
        CustomerAlias.objects.create(customer=self.toko, raw_value="MAKMUR BARU")
        response = self.get(q="makmur")
        self.assertEqual(len(response.context["customers"]), 1)
