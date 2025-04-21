// Set default reporting period to current month and handle tabs
document.addEventListener('DOMContentLoaded', function() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    
    // Set default reporting period for both forms
    const reportingPeriodInputs = document.querySelectorAll('input[type="month"]');
    reportingPeriodInputs.forEach(input => {
        input.value = `${year}-${month}`;
    });
    
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.alert');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(message => {
                message.style.opacity = '0';
                message.style.transition = 'opacity 1s';
                setTimeout(() => {
                    message.style.display = 'none';
                }, 1000);
            });
        }, 5000);
    }
    
    // Add transaction button functionality
    const addTransactionBtn = document.getElementById('add-transaction');
    if (addTransactionBtn) {
        addTransactionBtn.addEventListener('click', addTransaction);
        
        // Add at least one transaction form by default
        addTransaction();
    }
    
    // Form submission validation
    const viesForm = document.getElementById('vies-form');
    if (viesForm) {
        viesForm.addEventListener('submit', function(e) {
            const transactionEntries = document.querySelectorAll('.transaction-entry');
            
            if (transactionEntries.length === 0) {
                e.preventDefault();
                alert('Please add at least one transaction.');
                return false;
            }
            
            return true;
        });
    }
    
    // Handle tabs
    const uploadTab = document.getElementById('upload-tab');
    const manualTab = document.getElementById('manual-tab');
    const uploadContent = document.getElementById('upload-content');
    const manualContent = document.getElementById('manual-content');
    
    if (uploadTab && manualTab) {
        uploadTab.addEventListener('click', function() {
            uploadTab.classList.add('active');
            manualTab.classList.remove('active');
            uploadContent.style.display = 'block';
            manualContent.style.display = 'none';
        });
        
        manualTab.addEventListener('click', function() {
            manualTab.classList.add('active');
            uploadTab.classList.remove('active');
            manualContent.style.display = 'block';
            uploadContent.style.display = 'none';
        });
    }
    
    // File upload styling
    const fileInput = document.getElementById('excel_file');
    const fileUploadArea = document.querySelector('.file-upload');
    
    if (fileInput && fileUploadArea) {
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length > 0) {
                const fileName = fileInput.files[0].name;
                const fileInfo = document.querySelector('.file-info');
                fileInfo.textContent = `Selected file: ${fileName}`;
                fileUploadArea.style.borderColor = '#005f73';
            }
        });
    }
});

// Add a new transaction entry
function addTransaction() {
    const template = document.getElementById('transaction-template');
    const container = document.getElementById('transaction-container');
    
    if (template && container) {
        const clone = document.importNode(template.content, true);
        container.appendChild(clone);
    }
}

// Remove a transaction entry
function removeTransaction(button) {
    const transactionEntry = button.closest('.transaction-entry');
    if (transactionEntry) {
        transactionEntry.remove();
    }
}

// VAT review functionality
let approvedVats = [];

/**
 * Marks a suspicious VAT ID as approved
 */
function markVatAsOk(index, vatId) {
    const row = document.getElementById(`vat-row-${index}`);
    if (!row) return;
    
    // Add visual indication
    row.classList.add('approved-vat');
    
    // Send approval to server
    fetch('/approve_vat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            vat_id: vatId,
            session_id: getSessionId()
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('VAT ID approved successfully', 'success');
        } else {
            showToast('Error approving VAT ID: ' + data.error, 'error');
            // Revert visual indication
            row.classList.remove('approved-vat');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Network error while approving VAT ID', 'error');
        // Revert visual indication
        row.classList.remove('approved-vat');
    });
}

/**
 * Opens the edit modal for a VAT ID
 */
function openEditModal(index, countryCode, vatNumber, lineNumber) {
    const modal = document.getElementById('edit-vat-modal');
    const countryCodeInput = document.getElementById('edit-country-code');
    const vatNumberInput = document.getElementById('edit-vat-number');
    const lineNumberInput = document.getElementById('edit-line-number');
    const indexInput = document.getElementById('edit-index');
    
    // Set current values
    countryCodeInput.value = countryCode;
    vatNumberInput.value = vatNumber;
    lineNumberInput.value = lineNumber;
    indexInput.value = index;
    
    // Show modal
    modal.style.display = 'block';
}

/**
 * Closes the edit modal
 */
function closeEditModal() {
    const modal = document.getElementById('edit-vat-modal');
    modal.style.display = 'none';
}

/**
 * Saves the edited VAT ID
 */
function saveEditedVat() {
    const countryCode = document.getElementById('edit-country-code').value.trim().toUpperCase();
    const vatNumber = document.getElementById('edit-vat-number').value.trim();
    const lineNumber = document.getElementById('edit-line-number').value;
    const index = document.getElementById('edit-index').value;
    
    // Basic validation
    if (!countryCode || countryCode.length !== 2) {
        showToast('Country code must be exactly 2 characters', 'error');
        return;
    }
    
    if (!vatNumber) {
        showToast('VAT number cannot be empty', 'error');
        return;
    }
    
    // Send to server
    fetch('/edit_vat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            index: index,
            country_code: countryCode,
            vat_number: vatNumber,
            line_number: lineNumber,
            session_id: getSessionId()
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('VAT ID updated successfully', 'success');
            closeEditModal();
            
            // Update the table row with new values
            const row = document.getElementById(`vat-row-${index}`);
            if (row) {
                row.children[0].textContent = countryCode;
                row.children[1].textContent = vatNumber;
            }
        } else {
            showToast('Error updating VAT ID: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Network error while updating VAT ID', 'error');
    });
}

/**
 * Show toast notification
 */
function showToast(message, type) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.style.display = 'block';
    
    // Hide after 3 seconds
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

/**
 * Get or create session ID
 */
function getSessionId() {
    // Get session ID from a hidden input or generate a random one if needed
    let sessionId = document.querySelector('input[name="session_id"]');
    return sessionId ? sessionId.value : Date.now().toString();
}

// Close the modal when clicking outside of it
window.onclick = function(event) {
    const modal = document.getElementById('edit-vat-modal');
    if (event.target == modal) {
        closeEditModal();
    }
}

// Quarterly verification functions
document.addEventListener('DOMContentLoaded', function() {
    // Set up event listeners for quarterly verification
    const verifyButton = document.getElementById('verify-totals');
    if (verifyButton) {
        verifyButton.addEventListener('click', verifyQuarterlyTotals);
    }
    
    // Add event listeners to update totals when inputs change
    const monthlyInputs = document.querySelectorAll('.monthly-amount');
    monthlyInputs.forEach(input => {
        input.addEventListener('input', function() {
            // Clear previous verification results when inputs change
            document.getElementById('verification-result').style.display = 'none';
        });
    });
});

/**
 * Verify quarterly totals against uploaded data
 */
function verifyQuarterlyTotals() {
    // Get values from inputs
    const month1 = parseFloat(document.getElementById('month1-total').value) || 0;
    const month2 = parseFloat(document.getElementById('month2-total').value) || 0;
    const month3 = parseFloat(document.getElementById('month3-total').value) || 0;
    
    // Calculate quarterly sum
    const quarterlySum = month1 + month2 + month3;
    
    // Get VIES total from uploaded data
    let viesTotal = document.querySelector('.dashboard-card.highlight .card-value').textContent;
    viesTotal = parseFloat(viesTotal.replace('€', '').replace(',', '')) || 0;
    
    // Calculate difference
    const difference = Math.abs(quarterlySum - viesTotal);
    const percentageDifference = viesTotal > 0 ? (difference / viesTotal) * 100 : 0;
    
    // Update UI
    document.getElementById('quarterly-sum').textContent = `€${quarterlySum.toFixed(2)}`;
    document.getElementById('vies-total').textContent = `€${viesTotal.toFixed(2)}`;
    document.getElementById('difference').textContent = `€${difference.toFixed(2)} (${percentageDifference.toFixed(2)}%)`;
    
    // Show match status
    const matchStatus = document.getElementById('match-status');
    // Consider a match if difference is less than 1% or €10, whichever is smaller
    const threshold = Math.min(10, viesTotal * 0.01);
    const isMatch = difference <= threshold;
    
    matchStatus.textContent = isMatch 
        ? 'The totals match! (Difference is within acceptable threshold)' 
        : 'Warning: The totals do not match. Please review your data.';
    matchStatus.className = isMatch ? 'match-status match' : 'match-status mismatch';
    
    // Show verification result
    document.getElementById('verification-result').style.display = 'block';
} 