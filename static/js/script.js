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