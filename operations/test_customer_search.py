from django import forms
from django.test import TestCase

from catalog.models import Customer, CustomerAlias

from .forms import CustomerSearchField


class CustomerSearchFieldTests(TestCase):
    """Nama yang persis sama dengan satu pelanggan tidak boleh dianggap ambigu hanya karena
    ada pelanggan lain yang namanya memuat nama itu sebagai bagian (mis. 'YONO BAJA RINGAN')."""

    @classmethod
    def setUpTestData(cls):
        cls.exact = Customer.objects.create(display_name="YONO BAJA")
        cls.longer = Customer.objects.create(display_name="YONO BAJA RINGAN")
        cls.other = Customer.objects.create(display_name="TOKO LAIN")
        CustomerAlias.objects.create(customer=cls.other, raw_value="YONO BAJA CABANG")

    def setUp(self):
        self.field = CustomerSearchField(queryset=Customer.objects.filter(is_active=True))

    def test_exact_name_wins_over_longer_names(self):
        self.assertEqual(self.field.clean("YONO BAJA"), self.exact)

    def test_exact_name_ignores_case_and_extra_spaces(self):
        self.assertEqual(self.field.clean("  yono   baja "), self.exact)

    def test_partial_words_still_ambiguous_when_no_exact_match(self):
        with self.assertRaises(forms.ValidationError) as ctx:
            self.field.clean("YONO")
        self.assertEqual(ctx.exception.code, "ambiguous")

    def test_duplicate_exact_names_remain_ambiguous(self):
        Customer.objects.create(display_name="YONO BAJA")
        with self.assertRaises(forms.ValidationError) as ctx:
            self.field.clean("YONO BAJA")
        self.assertEqual(ctx.exception.code, "ambiguous")
