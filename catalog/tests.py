from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Customer, CustomerAlias, Cylinder, GasType


class CylinderConstraintTests(TestCase):
    def test_serial_number_must_be_unique(self):
        Cylinder.objects.create(serial_number="DUP-001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cylinder.objects.create(serial_number="DUP-001")

    def test_default_status_is_available(self):
        cylinder = Cylinder.objects.create(serial_number="NEW-001")
        self.assertEqual(cylinder.status, Cylinder.Status.AVAILABLE)


class GasTypeTests(TestCase):
    def test_gas_type_can_be_added_as_master_data(self):
        gas = GasType.objects.create(code="HE")
        self.assertTrue(gas.is_active)


class CustomerAliasTests(TestCase):
    def test_alias_unique_per_customer(self):
        customer = Customer.objects.create(display_name="Pelanggan Uji")
        CustomerAlias.objects.create(customer=customer, raw_value="Pelanggan  Uji ")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerAlias.objects.create(customer=customer, raw_value="Pelanggan  Uji ")
