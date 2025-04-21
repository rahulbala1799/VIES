"""
Module for generating German VIES return files.
"""
import csv
from datetime import datetime
from io import StringIO
import os


class VIESGenerator:
    """
    Class for generating VIES return files in the format required by 
    the German tax authorities.
    """
    
    def __init__(self, company_name, tax_number, reporting_period):
        """
        Initialize the VIES generator.
        
        Args:
            company_name (str): The name of the company
            tax_number (str): The tax identification number
            reporting_period (str): The reporting period in format YYYY-MM
        """
        self.company_name = company_name
        self.tax_number = tax_number
        self.reporting_period = reporting_period
        self.transactions = []
    
    def add_transaction(self, country_code, vat_number, amount, transaction_type='L'):
        """
        Add a transaction to the VIES return.
        
        Args:
            country_code (str): Two-letter ISO country code
            vat_number (str): VAT identification number without country code
            amount (float): Transaction amount in EUR
            transaction_type (str): Transaction type code (L for goods, S for services)
        """
        self.transactions.append({
            'country_code': country_code.upper(),
            'vat_number': vat_number.replace(' ', ''),
            'amount': round(float(amount), 2),
            'transaction_type': transaction_type.upper()
        })
    
    def generate_file(self):
        """
        Generate the VIES return file content.
        
        Returns:
            StringIO: A file-like object containing the CSV content
        """
        output = StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Parse reporting period
        year, month = self.reporting_period.split('-')
        
        # Write header
        writer.writerow([
            'Finanzamt', 
            self.company_name,
            self.tax_number,
            f"{month}/{year}"
        ])
        
        # Write transactions
        for transaction in self.transactions:
            # Combine country code and VAT number into a single field
            combined_vat_id = f"{transaction['country_code']}{transaction['vat_number']}"
            
            writer.writerow([
                combined_vat_id,
                f"{transaction['amount']:.2f}".replace('.', ','),
                transaction['transaction_type']
            ])
        
        output.seek(0)
        return output
    
    def save_file(self, directory='.'):
        """
        Save the VIES return to a file.
        
        Args:
            directory (str): Directory to save the file in
            
        Returns:
            str: Path to the saved file
        """
        # Create filename based on reporting period
        year, month = self.reporting_period.split('-')
        filename = f"VIES_{year}_{month}.csv"
        filepath = os.path.join(directory, filename)
        
        # Get file content
        content = self.generate_file()
        
        # Write to file
        with open(filepath, 'w', newline='') as f:
            f.write(content.getvalue())
        
        return filepath 