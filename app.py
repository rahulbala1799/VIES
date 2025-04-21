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
from collections import defaultdict

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-for-testing")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max file size: 16MB

# Session storage for uploaded data
UPLOADS = {}

def combine_duplicate_transactions(transactions):
    """
    Combine transactions with the same VAT ID and transaction type.
    
    Args:
        transactions (list): List of transaction dictionaries
        
    Returns:
        tuple: (original_transactions, combined_transactions)
    """
    # Store original transactions
    original_transactions = transactions.copy()
    
    # Create a dictionary to group transactions by VAT ID and type
    grouped = defaultdict(list)
    
    for transaction in transactions:
        # Create a key based on VAT ID and transaction type
        key = (transaction['country_code'], transaction['vat_number'], transaction['transaction_type'])
        grouped[key].append(transaction)
    
    # Combine transactions in each group
    combined_transactions = []
    for key, group in grouped.items():
        if len(group) > 1:
            # Combine transactions
            combined = {
                'country_code': key[0],
                'vat_number': key[1],
                'transaction_type': key[2],
                'amount': sum(t['amount'] for t in group),
                'customer': ', '.join(set(t['customer'] for t in group if t.get('customer'))) or group[0].get('customer', '')
            }
            combined_transactions.append(combined)
        else:
            # Just add the single transaction
            combined_transactions.append(group[0])
    
    return original_transactions, combined_transactions

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
            
            # Process data with the new method
            data, errors, warnings, metrics = excel_processor.process_data()
            
            if data is None or errors:
                for error in errors:
                    flash(error, 'error')
                return redirect(url_for('index'))
                
            # Show warnings if any
            for warning in warnings:
                flash(warning, 'warning')
            
            # Use current month and year for reporting period
            import datetime
            now = datetime.datetime.now()
            reporting_period = f"{now.year}-{now.month:02d}"
            
            # Create generator for the VIES file export
            company_name = "Company from Excel"
            tax_number = "Tax Number from Excel"
            generator = excel_processor.create_generator(company_name, tax_number, reporting_period, data)
            
            # Store in session for later generation
            session_id = str(uuid.uuid4())
            UPLOADS[session_id] = generator
            
            # Display success message with metrics
            flash(f'Successfully processed {metrics["total_rows"]} rows with {metrics["combined_transactions"]} unique VAT IDs.', 'success')
            
            return render_template(
                'index.html', 
                transactions=data['aggregated_transactions'],
                blank_vat_entries=data['blank_vat_entries'],
                suspicious_vat_entries=data['suspicious_vat_entries'],
                metrics=metrics,
                total_amount=f"{metrics['total_amount']:.2f}",
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