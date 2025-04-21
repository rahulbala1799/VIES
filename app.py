from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
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
import io
import csv
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-for-testing")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max file size: 16MB

# Session storage for uploaded data
UPLOADS = {}
# Storage for approved VAT IDs
APPROVED_VATS = defaultdict(list)
# Storage for edited VAT entries
EDITED_VATS = defaultdict(dict)

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

@app.route('/approve_vat', methods=['POST'])
def approve_vat():
    """Mark a suspicious VAT ID as approved"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        vat_id = data.get('vat_id')
        session_id = data.get('session_id')
        
        if not vat_id or not session_id:
            return jsonify({'success': False, 'error': 'Missing required fields'})
            
        # Add to approved VATs list for this session
        if vat_id not in APPROVED_VATS[session_id]:
            APPROVED_VATS[session_id].append(vat_id)
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error approving VAT: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/edit_vat', methods=['POST'])
def edit_vat():
    """Edit a suspicious VAT ID"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        index = data.get('index')
        country_code = data.get('country_code')
        vat_number = data.get('vat_number')
        line_number = data.get('line_number')
        session_id = data.get('session_id')
        
        if not all([index, country_code, vat_number, session_id]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Basic validation
        if len(country_code) != 2:
            return jsonify({'success': False, 'error': 'Country code must be exactly 2 characters'})
            
        # Store edited vat information
        EDITED_VATS[session_id][index] = {
            'country_code': country_code.upper(),
            'vat_number': vat_number,
            'line_number': line_number
        }
        
        # If we have the generator in memory, update the transaction
        if session_id in UPLOADS:
            generator = UPLOADS[session_id]
            generator.update_vat_id(line_number, country_code.upper(), vat_number)
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error editing VAT: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/generate_excel_report', methods=['POST'])
def generate_excel_report():
    """Generate an Excel report with reconciliation results"""
    try:
        session_id = request.form.get('session_id')
        
        if not session_id or session_id not in UPLOADS:
            flash('Session expired or invalid. Please upload your file again.', 'error')
            return redirect(url_for('index'))
        
        generator = UPLOADS[session_id]
        
        # Create a pandas DataFrame for the report
        data = generator.get_all_transactions()
        df = pd.DataFrame(data)
        
        # Add reconciliation data if available
        reconciliation_data = []
        
        # Create an Excel writer
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='VIES Transactions', index=False)
            
            # Add a sheet for reconciliation if data exists
            if reconciliation_data:
                recon_df = pd.DataFrame(reconciliation_data)
                recon_df.to_excel(writer, sheet_name='Reconciliation', index=False)
            
        output.seek(0)
        
        # Generate filename with current date
        now = datetime.now()
        filename = f"VIES_Excel_Report_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Excel report generation error: {error_details}")
        flash(f'Error generating Excel report: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/generate_csv', methods=['POST'])
def generate_csv():
    """Generate a CSV report with specific headers for VIES reporting"""
    try:
        session_id = request.form.get('session_id')
        
        if not session_id or session_id not in UPLOADS:
            flash('Session expired or invalid. Please upload your file again.', 'error')
            return redirect(url_for('index'))
        
        generator = UPLOADS[session_id]
        
        # Create a CSV file with the exact format shown in the example
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Write version headers
        writer.writerow(['#v3.0'])
        writer.writerow(['#v3.2.0'])
        
        # Write the special header
        writer.writerow(['Umsatzsteue Summe (Eur Art der Leistu Importmeldung'])
        
        # Write data rows
        for transaction in generator.get_all_transactions():
            # Combine country code and VAT number without spaces
            vat_id = f"{transaction.get('country_code', '')}{transaction.get('vat_number', '')}"
            
            # Format amount with proper alignment
            amount = f"{transaction.get('amount', 0):.0f}"
            
            # For services, use 'S'
            service_type = 'S' if transaction.get('transaction_type') == 'S' else 'L'
            
            writer.writerow([
                vat_id,
                amount,
                service_type
            ])
        
        output.seek(0)
        
        # Generate filename with current date
        now = datetime.now()
        filename = f"VIES_CSV_Report_{now.strftime('%Y%m%d')}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),  # Include BOM for Excel compatibility
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"CSV report generation error: {error_details}")
        flash(f'Error generating CSV report: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    """Generate a PDF report with reconciliation results and transactions"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        session_id = data.get('sessionId')
        if not session_id or session_id not in UPLOADS:
            return jsonify({'success': False, 'error': 'Session expired or invalid'}), 400
        
        # Get reconciliation data
        reconciliation = data.get('reconciliation', {})
        transactions = data.get('transactions', [])
        suspicious_vats = data.get('suspiciousVats', [])
        
        # Create a PDF file
        buffer = io.BytesIO()
        # Add proper margins to ensure content fits and doesn't get cut off
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        elements = []
        
        # Calculate available width for tables (A4 width - margins)
        available_width = doc.width
        
        # Add title
        title_style = styles['Heading1']
        title = Paragraph("VIES Return Reconciliation Report", title_style)
        elements.append(title)
        elements.append(Spacer(1, 12))
        
        # Add date
        date_style = styles['Normal']
        date_text = Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", date_style)
        elements.append(date_text)
        elements.append(Spacer(1, 12))
        
        # Add reconciliation data
        if reconciliation:
            subtitle = Paragraph("Quarterly Reconciliation", styles['Heading2'])
            elements.append(subtitle)
            elements.append(Spacer(1, 12))
            
            # Create reconciliation table
            monthly_values = reconciliation.get('monthlyValues', ['0', '0', '0'])
            recon_data = [
                ['Description', 'Amount'],
                ['Month 1 Total', f"€{monthly_values[0]}"],
                ['Month 2 Total', f"€{monthly_values[1]}"],
                ['Month 3 Total', f"€{monthly_values[2]}"],
                ['Quarterly Total (VAT Returns)', reconciliation.get('quarterlySum', '€0.00')],
                ['VIES Total (Uploaded Data)', reconciliation.get('viesTotal', '€0.00')],
                ['Difference', reconciliation.get('difference', '€0.00')]
            ]
            
            # Adjust column widths to fit within page width
            recon_table = Table(recon_data, colWidths=[available_width * 0.7, available_width * 0.3])
            recon_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (1, 0), colors.black),
                ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                ('BACKGROUND', (0, 4), (0, 6), colors.lightgrey),
                ('GRID', (0, 0), (1, 6), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(recon_table)
            elements.append(Spacer(1, 12))
            
            # Add match status
            status_color = colors.green if reconciliation.get('isMatch', False) else colors.red
            status_style = ParagraphStyle(
                'Status',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                backColor=status_color,
                textColor=colors.white,
                alignment=1,
                spaceAfter=10,
                spaceBefore=10,
                borderPadding=10
            )
            status_text = Paragraph(reconciliation.get('matchStatus', ''), status_style)
            elements.append(status_text)
            elements.append(Spacer(1, 20))
        
        # Add transactions table
        if transactions:
            subtitle = Paragraph("VIES Transactions", styles['Heading2'])
            elements.append(subtitle)
            elements.append(Spacer(1, 12))
            
            # Create transactions table
            trans_data = [['Line Numbers', 'Customer', 'VAT Number', 'Amount', 'Type']]
            
            for t in transactions:
                trans_data.append([
                    t.get('lineNumbers', ''),
                    t.get('customer', ''),
                    t.get('vatNumber', ''),
                    t.get('amount', ''),
                    t.get('type', '')
                ])
            
            # Calculate relative column widths based on content
            col_widths = [
                available_width * 0.15,  # Line Numbers
                available_width * 0.30,  # Customer
                available_width * 0.25,  # VAT Number
                available_width * 0.15,  # Amount
                available_width * 0.15   # Type
            ]
            
            trans_table = Table(trans_data, repeatRows=1, colWidths=col_widths)
            trans_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),  # Smaller font size for better fit
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (3, 1), (3, -1), 'RIGHT'),  # Right-align amount column
                ('WORDWRAP', (0, 0), (-1, -1), True),  # Enable word wrapping
            ]))
            elements.append(trans_table)
        
        # Add suspicious VAT IDs if any
        if suspicious_vats:
            elements.append(Spacer(1, 20))
            subtitle = Paragraph("Suspicious VAT IDs", styles['Heading2'])
            elements.append(subtitle)
            elements.append(Spacer(1, 12))
            
            # Create suspicious VATs table
            sus_data = [['Country Code', 'VAT Number', 'Line Number', 'Status']]
            
            for vat in suspicious_vats:
                status = 'Approved' if vat.get('isApproved', False) else 'Not Verified'
                sus_data.append([
                    vat.get('countryCode', ''),
                    vat.get('vatNumber', ''),
                    vat.get('lineNumber', ''),
                    status
                ])
            
            # Set column widths for suspicious VAT table
            sus_col_widths = [
                available_width * 0.2,   # Country Code
                available_width * 0.4,   # VAT Number
                available_width * 0.2,   # Line Number
                available_width * 0.2    # Status
            ]
            
            sus_table = Table(sus_data, repeatRows=1, colWidths=sus_col_widths)
            sus_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),  # Slightly smaller font
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('WORDWRAP', (0, 0), (-1, -1), True),  # Enable word wrapping
            ]))
            elements.append(sus_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"VIES_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
    
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"PDF generation error: {error_details}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG", "True") == "True", 
            host='0.0.0.0', 
            port=int(os.getenv("PORT", 5000))) 