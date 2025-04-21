"""
Module for processing Excel files for VIES return generation.
"""
import pandas as pd
import re
import os
from io import BytesIO
from .generator import VIESGenerator

class ExcelProcessor:
    """Process Excel files containing VIES transaction data."""
    
    def __init__(self, file_path=None, file_content=None):
        """
        Initialize the Excel processor.
        
        Args:
            file_path (str, optional): Path to the Excel file.
            file_content (BytesIO, optional): Content of the uploaded file.
        """
        self.file_path = file_path
        self.file_content = file_content
        self.data = None
        
    def load_data(self):
        """
        Load data from the Excel file.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Determine file extension to select the appropriate engine
            if self.file_path:
                file_ext = os.path.splitext(self.file_path)[1].lower()
                engine = 'openpyxl' if file_ext == '.xlsx' else 'xlrd'
                self.data = pd.read_excel(self.file_path, engine=engine)
            elif self.file_content:
                # For BytesIO content, try both engines
                try:
                    # Try with openpyxl first (for .xlsx)
                    self.data = pd.read_excel(self.file_content, engine='openpyxl')
                except Exception as e1:
                    # If that fails, try with xlrd (for .xls)
                    try:
                        # Reset file pointer position
                        self.file_content.seek(0)
                        self.data = pd.read_excel(self.file_content, engine='xlrd')
                    except Exception as e2:
                        # If both fail, raise a more descriptive error
                        raise ValueError(f"Failed to read Excel file with both engines: {str(e1)} and {str(e2)}")
            else:
                return False
            
            # Clean column names (remove whitespace, lowercase)
            self.data.columns = [str(col).strip().lower() for col in self.data.columns]
            
            return True
        except Exception as e:
            print(f"Error loading Excel file: {str(e)}")
            return False
            
    def map_columns(self):
        """
        Map Excel columns to expected VIES format.
        
        Returns:
            dict: Mapping of standard names to file's column names
        """
        # Define possible column names for each field
        column_mapping = {
            'customer': ['customer', 'name', 'customer name', 'company', 'company name', 'client'],
            'country_code': ['country', 'country code', 'country indicator', 'country_indicator'],
            'vat_number': ['vat', 'vat number', 'vat no', 'customer\'s vat number', 'customer vat'],
            'amount': ['amount', 'value', 'eur', 'euro', 'value of supplies', 'value of supplies eur'],
            'transaction_type': ['type', 'transaction type', 'service type', 'other services'],
            'triangular': ['triangular', 'triangular transaction', 'triangular transactions']
        }
        
        mapping = {}
        for standard_name, possible_names in column_mapping.items():
            for col in self.data.columns:
                # Check if column name matches any of the possible names
                if any(possible.lower() == col.lower() for possible in possible_names):
                    mapping[standard_name] = col
                    break
        
        return mapping
    
    def extract_country_code(self, vat_number):
        """
        Extract country code from VAT number if not provided separately.
        
        Args:
            vat_number (str): The VAT number which may include country code
            
        Returns:
            tuple: (country_code, clean_vat_number)
        """
        if not vat_number or pd.isna(vat_number):
            return ('', '')
            
        vat_number = str(vat_number).strip().upper()
        
        # Regular expression to match 2-letter country code at the beginning
        match = re.match(r'^([A-Z]{2})([A-Z0-9]+)$', vat_number.replace(' ', ''))
        
        if match:
            country_code = match.group(1)
            clean_number = match.group(2)
            return (country_code, clean_number)
        
        return ('', vat_number)
    
    def process_to_generator(self, company_name, tax_number, reporting_period):
        """
        Process the Excel data and create a VIES generator.
        
        Args:
            company_name (str): Company name
            tax_number (str): Company tax number
            reporting_period (str): Reporting period in YYYY-MM format
            
        Returns:
            VIESGenerator: Generator with transactions from Excel
        """
        if not self.load_data():
            raise ValueError("Could not load Excel data")
            
        # Create mapping for columns
        column_map = self.map_columns()
        
        # Check if we have the minimum required columns
        required_fields = ['amount']
        missing_fields = [field for field in required_fields if field not in column_map]
        
        if missing_fields:
            raise ValueError(f"Missing required columns: {', '.join(missing_fields)}")
            
        # Create generator
        generator = VIESGenerator(company_name, tax_number, reporting_period)
        
        # Process each row
        for _, row in self.data.iterrows():
            try:
                # Get values, handle missing columns gracefully
                country_code = ''
                vat_number = ''
                
                # Get VAT number and extract country code if needed
                if 'vat_number' in column_map:
                    vat = str(row[column_map['vat_number']]) if not pd.isna(row[column_map['vat_number']]) else ''
                    extracted_cc, extracted_vat = self.extract_country_code(vat)
                    vat_number = extracted_vat
                    
                    if extracted_cc and not country_code:
                        country_code = extracted_cc
                
                # Get country code from dedicated column if available
                if 'country_code' in column_map and not country_code:
                    country_code = str(row[column_map['country_code']]) if not pd.isna(row[column_map['country_code']]) else ''
                
                # Get amount
                amount_col = column_map['amount']
                amount = float(row[amount_col]) if not pd.isna(row[amount_col]) else 0
                
                # Determine transaction type
                transaction_type = 'L'  # Default to Goods
                if 'transaction_type' in column_map:
                    type_value = row[column_map['transaction_type']]
                    # Check for specific text values
                    if not pd.isna(type_value):
                        type_text = str(type_value).strip().lower()
                        if type_text in ['1', 'yes', 'y', 'true', 's', 'service', 'other services', 'other service']:
                            transaction_type = 'S'  # Services
                        elif type_text in ['l', 'goods', 'good', 'supply', 'supplies']:
                            transaction_type = 'L'  # Goods/Supplies
                
                # Skip rows with missing essential data
                if not country_code or not vat_number or amount <= 0:
                    continue
                    
                # Add transaction
                generator.add_transaction(country_code, vat_number, amount, transaction_type)
                
            except Exception as e:
                print(f"Error processing row: {str(e)}")
                continue
                
        return generator 