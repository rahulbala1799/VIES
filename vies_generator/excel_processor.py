"""
Module for processing Excel files for VIES return generation.
"""
import pandas as pd
import re
import os
from io import BytesIO
from .generator import VIESGenerator
from collections import defaultdict

class ExcelProcessor:
    """Process Excel files containing VIES transaction data."""
    
    # VAT number format patterns by country code
    VAT_FORMATS = {
        'AT': r'^U\d{8}$',                 # Austria
        'BE': r'^\d{10}$',                 # Belgium
        'BG': r'^\d{9,10}$',               # Bulgaria
        'CY': r'^\d{8}[A-Z]$',             # Cyprus
        'CZ': r'^\d{8,10}$',               # Czech Republic
        'DE': r'^\d{9}$',                  # Germany
        'DK': r'^\d{8}$',                  # Denmark
        'EE': r'^\d{9}$',                  # Estonia
        'EL': r'^\d{9}$',                  # Greece
        'ES': r'^[A-Z0-9]\d{7}[A-Z0-9]$',  # Spain
        'FI': r'^\d{8}$',                  # Finland
        'FR': r'^[A-Z0-9]{2}\d{9}$',       # France
        'GB': r'^\d{9}$|^\d{12}$|^GD\d{3}$|^HA\d{3}$',  # United Kingdom
        'HR': r'^\d{11}$',                 # Croatia
        'HU': r'^\d{8}$',                  # Hungary
        'IE': r'^\d{7}[A-Z]{1,2}$',        # Ireland
        'IT': r'^\d{11}$',                 # Italy
        'LT': r'^\d{9}$|^\d{12}$',         # Lithuania
        'LU': r'^\d{8}$',                  # Luxembourg
        'LV': r'^\d{11}$',                 # Latvia
        'MT': r'^\d{8}$',                  # Malta
        'NL': r'^\d{9}B\d{2}$',            # Netherlands
        'PL': r'^\d{10}$',                 # Poland
        'PT': r'^\d{9}$',                  # Portugal
        'RO': r'^\d{2,10}$',               # Romania
        'SE': r'^\d{12}$',                 # Sweden
        'SI': r'^\d{8}$',                  # Slovenia
        'SK': r'^\d{10}$',                 # Slovakia
    }
    
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
        self.errors = []
        self.warnings = []
        self.blank_vat_entries = []
        self.suspicious_vat_entries = []
        
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
            self.errors.append(f"Error loading Excel file: {str(e)}")
            print(f"Error loading Excel file: {str(e)}")
            return False
            
    def validate_vat_number(self, country_code, vat_number):
        """
        Validate the VAT number format based on country code.
        
        Args:
            country_code (str): Two-letter country code
            vat_number (str): VAT number without country code
            
        Returns:
            tuple: (is_valid, suspicion_reason)
                is_valid: bool indicating if the VAT number format is valid
                suspicion_reason: str with reason for suspicion, or None if not suspicious
        """
        if not country_code or not vat_number:
            return False, "Missing country code or VAT number"
            
        country_code = country_code.upper()
        vat_number = vat_number.strip()
        
        # Check for repeating digits (more than 3 in a row)
        repeat_pattern = re.search(r'(\d)\1{3,}', vat_number)
        if repeat_pattern:
            digit = repeat_pattern.group(1)
            return False, f"Contains {len(repeat_pattern.group(0))} repeating '{digit}' digits"
            
        # Check for sequential digits (more than 4 in sequence)
        for i in range(len(vat_number) - 4):
            if vat_number[i:i+5].isdigit():
                if vat_number[i:i+5] in '01234567890' or vat_number[i:i+5] in '98765432109':
                    return False, f"Contains sequential digits: {vat_number[i:i+5]}"
        
        # Check for all same digits
        if vat_number.isdigit() and len(set(vat_number)) == 1:
            return False, f"All digits are the same: {vat_number[0]}"
            
        # Check if VAT number is suspiciously short
        if len(vat_number) < 5 and vat_number.isdigit():
            return False, f"VAT number is suspiciously short ({len(vat_number)} digits)"
            
        # Check against country-specific format if available
        if country_code in self.VAT_FORMATS:
            pattern = self.VAT_FORMATS[country_code]
            if not re.match(pattern, vat_number):
                return False, f"Does not match expected format for {country_code}"
                
        return True, None
            
    def map_columns(self):
        """
        Map Excel columns to expected VIES format.
        
        Returns:
            dict: Mapping of standard names to file's column names
        """
        # Define possible column names for each field
        column_mapping = {
            'line': ['line', 'line number', 'row', 'row number', '#'],
            'customer': ['customer', 'customer number', 'customer no', 'customer id', 'customer code', 'client number'],
            'country_code': ['country', 'country code', 'country indicator', 'country_indicator'],
            'vat_number': ['vat', 'vat number', 'vat no', 'customer\'s vat number', 'customer vat'],
            'amount': ['amount', 'value', 'eur', 'euro', 'value of supplies', 'value of supplies eur'],
            'transaction_type': ['type', 'transaction type', 'service type', 'other services']
        }
        
        mapping = {}
        for standard_name, possible_names in column_mapping.items():
            for col in self.data.columns:
                # Check if column name matches any of the possible names
                if any(possible.lower() == col.lower() for possible in possible_names):
                    mapping[standard_name] = col
                    break
        
        # Expected columns 
        expected_cols = ['line', 'customer', 'country_code', 'vat_number', 'amount', 'transaction_type']
        missing_cols = [col for col in expected_cols if col not in mapping]
        
        if missing_cols:
            self.warnings.append(f"Missing expected columns: {', '.join(missing_cols)}")
            print(f"Warning: Missing expected columns: {', '.join(missing_cols)}")
            
            # Try to intelligently map columns by position if names don't match
            if len(self.data.columns) >= 6:  # We need at least 6 columns
                # Map the first 6 columns directly to expected fields
                col_positions = {
                    0: 'line',
                    1: 'customer',
                    2: 'country_code', 
                    3: 'vat_number',
                    4: 'amount',
                    5: 'transaction_type'
                }
                
                for pos, standard_name in col_positions.items():
                    if pos < len(self.data.columns) and standard_name not in mapping:
                        mapping[standard_name] = self.data.columns[pos]
                        print(f"Auto-mapped {standard_name} to column {pos+1}: {self.data.columns[pos]}")
        
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
    
    def process_data(self):
        """
        Process the Excel data and create aggregated transactions.
        
        Returns:
            tuple: (processed_data, errors, warnings, metrics)
                processed_data: dict with transaction data
                errors: list of error messages
                warnings: list of warning messages
                metrics: dict with processing metrics
        """
        if not self.load_data():
            self.errors.append("Could not load Excel data")
            return None, self.errors, self.warnings, {}
            
        # Create mapping for columns
        column_map = self.map_columns()
        
        # Check if we have the minimum required columns
        required_fields = ['amount', 'vat_number']
        missing_fields = [field for field in required_fields if field not in column_map]
        
        if missing_fields:
            self.errors.append(f"Missing required columns: {', '.join(missing_fields)}")
            return None, self.errors, self.warnings, {}
        
        # Process each row and extract data
        total_rows = 0
        valid_transactions = []
        blank_vat_rows = []
        invalid_rows = []
        suspicious_vat_rows = []
        total_amount = 0
        
        # Dictionary to store aggregated data by VAT ID
        aggregated_by_vat = defaultdict(lambda: {
            'country_code': '',
            'vat_number': '',
            'customer_numbers': set(),
            'amount': 0,
            'transaction_type': '',
            'line_numbers': set(),
            'is_valid': True,
            'is_suspicious': False,
            'suspicion_reason': None
        })
        
        for i, row in self.data.iterrows():
            total_rows += 1
            try:
                line_number = f"{i+1}" # 1-indexed line number
                if 'line' in column_map:
                    try:
                        line_val = row[column_map['line']]
                        if not pd.isna(line_val):
                            line_number = str(line_val)
                    except:
                        pass
                
                # Get values, handle missing columns gracefully
                country_code = ''
                vat_number = ''
                customer = ''
                
                # Get customer name if available
                if 'customer' in column_map:
                    customer = str(row[column_map['customer']]) if not pd.isna(row[column_map['customer']]) else ''
                
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
                amount = 0
                if 'amount' in column_map:
                    amount_col = column_map['amount']
                    amount_val = row[amount_col]
                    
                    # Handle different number formats
                    if pd.isna(amount_val):
                        amount = 0
                    else:
                        # Try to convert to float, handling string representations
                        try:
                            amount = float(amount_val)
                        except ValueError:
                            # Try to handle comma as decimal separator
                            try:
                                amount = float(str(amount_val).replace(',', '.'))
                            except:
                                self.warnings.append(f"Invalid amount in row {line_number}: {amount_val}")
                                continue
                
                # Determine transaction type
                transaction_type = 'L'  # Default to Goods
                if 'transaction_type' in column_map:
                    type_value = row[column_map['transaction_type']]
                    # Check for specific text values
                    if not pd.isna(type_value):
                        type_text = str(type_value).strip().lower()
                        print(f"Processing transaction type: '{type_text}'")
                        if type_text in ['1', 'yes', 'y', 'true', 's', 'service', 'other services', 'other service', 'services']:
                            transaction_type = 'S'  # Services
                            print(f"Setting transaction type to S for '{type_text}'")
                        elif type_text in ['0', 'no', 'n', 'false', 'l', 'goods', 'good', 'supply', 'supplies']:
                            transaction_type = 'L'  # Goods/Supplies
                            print(f"Setting transaction type to L for '{type_text}'")
                
                # Check if this is a total line (not a missing VAT entry)
                is_total_line = False
                if 'line' in column_map:
                    line_value = str(row[column_map['line']]).strip().lower()
                    if line_value == 'total' or 'total' in line_value:
                        is_total_line = True
                        print(f"Detected total line from line field: {line_number}")
                
                # Also check if "Total" appears in the customer field
                if 'customer' in column_map and not is_total_line:
                    customer_value = str(row[column_map['customer']]).strip().lower()
                    if customer_value == 'total' or 'total' in customer_value:
                        is_total_line = True
                        print(f"Detected total line from customer field: {line_number}")
                
                # Check for blank VAT
                is_blank_vat = not vat_number or vat_number.strip() == ''
                
                # Validate VAT number if present
                is_suspicious = False
                suspicion_reason = None
                if not is_blank_vat and not is_total_line:
                    is_valid, suspicion_reason = self.validate_vat_number(country_code, vat_number)
                    if not is_valid:
                        is_suspicious = True
                        print(f"Suspicious VAT in row {line_number}: {country_code}{vat_number} - {suspicion_reason}")
                
                # Add to transactions with validation
                transaction = {
                    'line_number': line_number,
                    'customer': customer,
                    'country_code': country_code.upper(),
                    'vat_number': vat_number.replace(' ', ''),
                    'amount': amount,
                    'transaction_type': transaction_type.upper(),
                    'is_blank_vat': is_blank_vat and not is_total_line,
                    'is_total_line': is_total_line,
                    'is_suspicious': is_suspicious,
                    'suspicion_reason': suspicion_reason
                }
                
                # Track blank VAT entries separately (but not total lines)
                if is_blank_vat and not is_total_line:
                    blank_vat_rows.append(transaction)
                    continue
                    
                # Track suspicious VAT entries
                if is_suspicious:
                    suspicious_vat_rows.append(transaction)
                    
                # If it's a total line, we don't process it as a normal transaction
                if is_total_line:
                    continue
                    
                # Skip rows with missing essential data or zero amount
                if not country_code or amount == 0:
                    invalid_rows.append({
                        'line_number': line_number,
                        'reason': "Missing country code or zero amount"
                    })
                    continue
                
                # Add to valid transactions
                valid_transactions.append(transaction)
                total_amount += amount
                
                # Add to aggregated data
                vat_key = f"{country_code}:{vat_number}"
                aggregated_by_vat[vat_key]['country_code'] = country_code
                aggregated_by_vat[vat_key]['vat_number'] = vat_number
                aggregated_by_vat[vat_key]['customer_numbers'].add(customer)
                aggregated_by_vat[vat_key]['amount'] += amount
                aggregated_by_vat[vat_key]['line_numbers'].add(line_number)
                
                # For transaction type, prefer Services (S) if any transaction is services
                if transaction_type == 'S':
                    aggregated_by_vat[vat_key]['transaction_type'] = 'S'
                elif not aggregated_by_vat[vat_key]['transaction_type']:
                    aggregated_by_vat[vat_key]['transaction_type'] = transaction_type
                    
                # Mark as suspicious if any of the entries is suspicious
                if is_suspicious:
                    aggregated_by_vat[vat_key]['is_suspicious'] = True
                    aggregated_by_vat[vat_key]['suspicion_reason'] = suspicion_reason
                    
            except Exception as e:
                self.errors.append(f"Error processing row {i+1}: {str(e)}")
                continue
        
        # Convert to list for easier handling
        aggregated_transactions = []
        for vat_key, data in aggregated_by_vat.items():
            customer_note = ", ".join(sorted([c for c in data['customer_numbers'] if c]))
            transaction = {
                'country_code': data['country_code'],
                'vat_number': data['vat_number'],
                'amount': round(data['amount'], 2),
                'transaction_type': data['transaction_type'],
                'customer': customer_note,
                'line_numbers': ", ".join(sorted(data['line_numbers'])),
                'multiple_customers': len(data['customer_numbers']) > 1,
                'is_blank_vat': False,
                'is_suspicious': data['is_suspicious'],
                'suspicion_reason': data['suspicion_reason']
            }
            aggregated_transactions.append(transaction)
            
        # Store blank VAT entries for display
        self.blank_vat_entries = blank_vat_rows
        self.suspicious_vat_entries = suspicious_vat_rows
            
        # Create metrics
        metrics = {
            'total_rows': total_rows,
            'valid_transactions': len(valid_transactions),
            'blank_vat_entries': len(blank_vat_rows),
            'suspicious_vat_entries': len(suspicious_vat_rows),
            'invalid_rows': len(invalid_rows),
            'combined_transactions': len(aggregated_transactions),
            'total_amount': round(total_amount, 2)
        }
        
        return {
            'original_transactions': valid_transactions,
            'aggregated_transactions': aggregated_transactions,
            'blank_vat_entries': blank_vat_rows,
            'suspicious_vat_entries': suspicious_vat_rows,
            'invalid_rows': invalid_rows
        }, self.errors, self.warnings, metrics
        
    def create_generator(self, company_name, tax_number, reporting_period, data=None):
        """
        Create a VIES generator from the processed data.
        
        Args:
            company_name (str): Company name
            tax_number (str): Company tax number
            reporting_period (str): Reporting period in YYYY-MM format
            data (dict, optional): Pre-processed data
            
        Returns:
            VIESGenerator: Generator with transactions
        """
        if data is None:
            data, _, _, _ = self.process_data()
            if data is None:
                raise ValueError("Could not process data")
        
        # Create generator
        generator = VIESGenerator(company_name, tax_number, reporting_period)
        
        # Add transactions to generator
        for transaction in data['aggregated_transactions']:
            generator.add_transaction(
                transaction['country_code'],
                transaction['vat_number'],
                transaction['amount'],
                transaction['transaction_type']
            )
            
            # Add additional fields that the generator doesn't handle natively
            if 'customer' in transaction:
                generator.transactions[-1]['customer'] = transaction['customer']
            if 'line_numbers' in transaction:
                generator.transactions[-1]['line_numbers'] = transaction['line_numbers']
            if 'multiple_customers' in transaction:
                generator.transactions[-1]['multiple_customers'] = transaction['multiple_customers']
        
        return generator 