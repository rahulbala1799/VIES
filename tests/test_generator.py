import unittest
import os
import tempfile
from vies_generator.generator import VIESGenerator

class TestVIESGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.gettempdir()
        self.company_name = "Test Company GmbH"
        self.tax_number = "DE123456789"
        self.reporting_period = "2023-09"
        self.generator = VIESGenerator(self.company_name, self.tax_number, self.reporting_period)

    def test_init(self):
        self.assertEqual(self.generator.company_name, self.company_name)
        self.assertEqual(self.generator.tax_number, self.tax_number)
        self.assertEqual(self.generator.reporting_period, self.reporting_period)
        self.assertEqual(len(self.generator.transactions), 0)

    def test_add_transaction(self):
        country_code = "FR"
        vat_number = "12345678901"
        amount = 1000.00
        transaction_type = "L"
        
        self.generator.add_transaction(country_code, vat_number, amount, transaction_type)
        
        self.assertEqual(len(self.generator.transactions), 1)
        transaction = self.generator.transactions[0]
        self.assertEqual(transaction["country_code"], country_code)
        self.assertEqual(transaction["vat_number"], vat_number)
        self.assertEqual(transaction["amount"], amount)
        self.assertEqual(transaction["transaction_type"], transaction_type)

    def test_generate_file(self):
        self.generator.add_transaction("FR", "12345678901", 1000.00, "L")
        self.generator.add_transaction("ES", "B12345678", 2000.00, "S")
        
        output = self.generator.generate_file()
        content = output.getvalue()
        
        # Check header row
        self.assertIn("Finanzamt", content)
        self.assertIn(self.company_name, content)
        self.assertIn(self.tax_number, content)
        self.assertIn("09/2023", content)
        
        # Check transaction rows
        self.assertIn("FR;12345678901;1000,00;L", content)
        self.assertIn("ES;B12345678;2000,00;S", content)

    def test_save_file(self):
        self.generator.add_transaction("FR", "12345678901", 1000.00, "L")
        
        filepath = self.generator.save_file(self.temp_dir)
        
        self.assertTrue(os.path.exists(filepath))
        
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)

if __name__ == '__main__':
    unittest.main() 