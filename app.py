from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import os
import tempfile
import uuid
from io import BytesIO
from dotenv import load_dotenv
from vies_generator.generator import VIESGenerator
from vies_generator.excel_processor import ExcelProcessor
import pandas as pd
import traceback

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-for-testing")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max file size: 16MB

# Session storage for uploaded data
UPLOADS = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-excel', methods=['POST'])
def upload_excel():
    try:
        # Check if file was provided
        if 'excel_file' not in request.files:
            flash('No file was provided.', 'error')
            return redirect(url_for('index'))
            
        file = request.files['excel_file']
        
        # Check if file was selected
        if file.filename == '':
            flash('No file was selected.', 'error')
            return redirect(url_for('index'))
            
        # Check file extension
        allowed_extensions = ['.xlsx', '.xls']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            flash(f'Invalid file type: {file_ext}. Only .xlsx and .xls files are allowed.', 'error')
            return redirect(url_for('index'))
        
        # Save file content to BytesIO
        try:
            file_content = BytesIO(file.read())
            
            # Process the Excel file
            excel_processor = ExcelProcessor(file_content=file_content)
            
            # Explicitly test loading the data
            if not excel_processor.load_data():
                flash('Failed to load Excel file. Please ensure it is a valid Excel file.', 'error')
                return redirect(url_for('index'))
                
            # Continue with processing
            column_map = excel_processor.map_columns()
            
            # Check if we have the necessary columns
            if 'amount' not in column_map:
                flash('Required "Value of Supplies" column not found in the Excel file.', 'error')
                return redirect(url_for('index'))
            
            # Use dummy company info - will be populated from the Excel if available
            company_name = "Company from Excel"
            tax_number = "Tax Number from Excel"
            
            # Use current month and year for reporting period
            import datetime
            now = datetime.datetime.now()
            reporting_period = f"{now.year}-{now.month:02d}"
            
            # Try to extract company info from Excel if available
            if excel_processor.data is not None:
                if 'customer' in column_map:
                    # Use first customer as company name if none provided
                    try:
                        first_row = excel_processor.data.iloc[0]
                        potential_name = first_row[column_map['customer']]
                        if not pd.isna(potential_name):
                            company_name = potential_name
                    except Exception as e:
                        # If there's an error, just use default
                        pass
            
            # Create generator with dummy data - we only need it for transactions
            generator = VIESGenerator(company_name, tax_number, reporting_period)
            
            # Process each row to extract transactions
            if excel_processor.data is not None:
                for _, row in excel_processor.data.iterrows():
                    try:
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
                            extracted_cc, extracted_vat = excel_processor.extract_country_code(vat)
                            vat_number = extracted_vat
                            
                            if extracted_cc and not country_code:
                                country_code = extracted_cc
                        
                        # Get country code from dedicated column if available
                        if 'country_code' in column_map and not country_code:
                            country_code = str(row[column_map['country_code']]) if not pd.isna(row[column_map['country_code']]) else ''
                        
                        # Get amount
                        if 'amount' in column_map:
                            amount_col = column_map['amount']
                            amount_val = row[amount_col]
                            
                            # Handle different number formats
                            if pd.isna(amount_val):
                                amount = 0
                            else:
                                # Try to convert to float, handling string representations like "1,000.00"
                                try:
                                    amount = float(amount_val)
                                except ValueError:
                                    # Try to handle comma as decimal separator
                                    try:
                                        amount = float(str(amount_val).replace(',', '.'))
                                    except:
                                        # If all conversion attempts fail, skip this row
                                        print(f"Skipping row with invalid amount: {amount_val}")
                                        continue
                        else:
                            continue  # Skip if no amount column
                        
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
                            
                        # Add transaction with additional customer info
                        transaction = {
                            'country_code': country_code.upper(),
                            'vat_number': vat_number.replace(' ', ''),
                            'amount': round(float(amount), 2),
                            'transaction_type': transaction_type.upper(),
                            'customer': customer
                        }
                        generator.transactions.append(transaction)
                        
                    except Exception as e:
                        print(f"Error processing row: {str(e)}")
                        continue
            
            # Check if we have any transactions
            if not generator.transactions:
                flash('No valid transactions found in the Excel file. Please check your data format.', 'error')
                return redirect(url_for('index'))
                
            # Store in session for later generation
            session_id = str(uuid.uuid4())
            UPLOADS[session_id] = generator
            
            # Calculate total amount
            total_amount = sum(transaction['amount'] for transaction in generator.transactions)
            
            flash(f'Successfully processed {len(generator.transactions)} transactions from the Excel file.', 'success')
            
            return render_template(
                'index.html', 
                transactions=generator.transactions,
                total_amount=f"{total_amount:.2f}",
                session_id=session_id
            )
            
        except Exception as e:
            # Get detailed error info
            error_details = traceback.format_exc()
            print(f"Excel processing error: {error_details}")
            flash(f'Error processing Excel file: {str(e)}', 'error')
            return redirect(url_for('index'))
        
    except Exception as e:
        # Get detailed error info
        error_details = traceback.format_exc()
        print(f"Upload error: {error_details}")
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/generate', methods=['POST'])
def generate_vies_file():
    """Generate and download the VIES file from processed data"""
    try:
        session_id = request.form.get('session_id')
        
        if not session_id or session_id not in UPLOADS:
            flash('Session expired or invalid. Please upload your file again.', 'error')
            return redirect(url_for('index'))
        
        generator = UPLOADS[session_id]
        
        # Generate file in a temporary directory
        temp_dir = tempfile.gettempdir()
        filepath = generator.save_file(temp_dir)
        
        # Provide a download link with current date if no reporting period
        try:
            year, month = generator.reporting_period.split('-')
        except:
            import datetime
            now = datetime.datetime.now()
            year, month = now.year, f"{now.month:02d}"
            
        filename = f"VIES_{year}_{month}.csv"
        
        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"File generation error: {error_details}")
        flash(f'Error generating VIES file: {str(e)}', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG", "True") == "True", 
            host='0.0.0.0', 
            port=int(os.getenv("PORT", 5000))) 