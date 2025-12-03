// Smart Finance Automator - Main JavaScript

// Global Application Object
const SmartFinanceApp = {
    // Configuration
    config: {
        apiBase: '/api',
        chartColors: [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
            '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384'
        ],
        currencySymbol: '₹'
    },
    
    // Utility functions
    utils: {
        // Format currency
        formatCurrency: function(amount) {
            return SmartFinanceApp.config.currencySymbol + parseFloat(amount).toFixed(2);
        },
        
        // Format number with commas
        formatNumber: function(number) {
            return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        },
        
        // Format date
        formatDate: function(dateString) {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-IN', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        },
        
        // Show toast notification
        showToast: function(message, type = 'info') {
            const toastContainer = document.getElementById('toastContainer') || this.createToastContainer();
            
            const toast = document.createElement('div');
            toast.className = `toast align-items-center text-white bg-${type} border-0`;
            toast.setAttribute('role', 'alert');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            `;
            
            toastContainer.appendChild(toast);
            const bsToast = new bootstrap.Toast(toast);
            bsToast.show();
            
            // Remove toast after it's hidden
            toast.addEventListener('hidden.bs.toast', () => {
                toast.remove();
            });
        },
        
        // Create toast container if it doesn't exist
        createToastContainer: function() {
            const container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
            return container;
        },
        
        // Debounce function
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        // API request wrapper
        apiRequest: async function(endpoint, options = {}) {
            const defaultOptions = {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            
            const config = { ...defaultOptions, ...options };
            
            try {
                const response = await fetch(SmartFinanceApp.config.apiBase + endpoint, config);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                return await response.json();
            } catch (error) {
                console.error('API Request failed:', error);
                SmartFinanceApp.utils.showToast('An error occurred. Please try again.', 'danger');
                throw error;
            }
        }
    },
    
    // Chart utilities
    charts: {
        defaultOptions: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        usePointStyle: true
                    }
                }
            }
        },
        
        // Create spending trend chart
        createSpendingChart: function(canvasId, data) {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return null;
            
            return new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        label: 'Spending Amount',
                        data: data.amounts || [],
                        borderColor: SmartFinanceApp.config.chartColors[1],
                        backgroundColor: SmartFinanceApp.config.chartColors[1] + '20',
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: SmartFinanceApp.config.chartColors[1],
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 6
                    }]
                },
                options: {
                    ...SmartFinanceApp.charts.defaultOptions,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return SmartFinanceApp.utils.formatCurrency(value);
                                }
                            }
                        }
                    },
                    plugins: {
                        ...SmartFinanceApp.charts.defaultOptions.plugins,
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return 'Amount: ' + SmartFinanceApp.utils.formatCurrency(context.parsed.y);
                                }
                            }
                        }
                    }
                }
            });
        },
        
        // Create category pie chart
        createCategoryChart: function(canvasId, data) {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return null;
            
            return new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.categories || [],
                    datasets: [{
                        data: data.amounts || [],
                        backgroundColor: SmartFinanceApp.config.chartColors,
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    ...SmartFinanceApp.charts.defaultOptions,
                    cutout: '60%',
                    plugins: {
                        ...SmartFinanceApp.charts.defaultOptions.plugins,
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = SmartFinanceApp.utils.formatCurrency(context.parsed);
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((context.parsed / total) * 100).toFixed(1);
                                    return `${label}: ${value} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }
    },
    
    // Dashboard functionality
    dashboard: {
        charts: {},
        
        init: function() {
            this.loadDashboardData();
            this.setupEventListeners();
        },
        
        loadDashboardData: async function() {
            try {
                // Load spending trends
                const spendingData = await SmartFinanceApp.utils.apiRequest('/spending-chart');
                this.charts.spending = SmartFinanceApp.charts.createSpendingChart('spendingTrendsChart', spendingData);
                
                // Load category breakdown
                const categoryData = await SmartFinanceApp.utils.apiRequest('/category-chart');
                this.charts.category = SmartFinanceApp.charts.createCategoryChart('categoryChart', categoryData);
                
            } catch (error) {
                console.error('Failed to load dashboard data:', error);
            }
        },
        
        setupEventListeners: function() {
            // Period selector buttons
            document.querySelectorAll('[data-period]').forEach(button => {
                button.addEventListener('click', (e) => {
                    document.querySelector('[data-period].active')?.classList.remove('active');
                    e.target.classList.add('active');
                    this.updateSpendingChart(e.target.dataset.period);
                });
            });
        },
        
        updateSpendingChart: function(period) {
            // Here you would fetch new data based on the period
            // For now, we'll just show a loading state
            SmartFinanceApp.utils.showToast(`Loading ${period} data...`, 'info');
        },
        
        refresh: function() {
            // Destroy existing charts
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.destroy) {
                    chart.destroy();
                }
            });
            
            // Reload data
            this.loadDashboardData();
            SmartFinanceApp.utils.showToast('Dashboard refreshed', 'success');
        }
    },
    
    // Upload functionality
    upload: {
        currentFile: null,
        
        init: function() {
            this.setupDropZone();
            this.setupFileInput();
            this.setupForm();
        },
        
        setupDropZone: function() {
            const dropZone = document.getElementById('dropZone');
            if (!dropZone) return;
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, this.preventDefaults, false);
            });
            
            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
            });
            
            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
            });
            
            dropZone.addEventListener('drop', this.handleDrop.bind(this), false);
        },
        
        setupFileInput: function() {
            const fileInput = document.getElementById('fileInput');
            if (!fileInput) return;
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handleFile(e.target.files[0]);
                }
            });
        },
        
        setupForm: function() {
            const form = document.getElementById('uploadForm');
            if (!form) return;
            
            form.addEventListener('submit', this.handleSubmit.bind(this));
        },
        
        preventDefaults: function(e) {
            e.preventDefault();
            e.stopPropagation();
        },
        
        handleDrop: function(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            
            if (files.length > 0) {
                this.handleFile(files[0]);
            }
        },
        
        handleFile: function(file) {
            // Validate file
            if (!this.validateFile(file)) {
                return;
            }
            
            this.currentFile = file;
            this.showFilePreview(file);
            document.getElementById('submitBtn').disabled = false;
        },
        
        validateFile: function(file) {
            const allowedTypes = ['text/plain', 'text/csv', 'application/json'];
            const maxSize = 16 * 1024 * 1024; // 16MB
            
            if (!allowedTypes.includes(file.type) && !file.name.match(/\.(txt|csv|json)$/i)) {
                SmartFinanceApp.utils.showToast('Please select a valid file type (.txt, .csv, .json)', 'warning');
                return false;
            }
            
            if (file.size > maxSize) {
                SmartFinanceApp.utils.showToast('File size must be less than 16MB', 'warning');
                return false;
            }
            
            return true;
        },
        
        showFilePreview: function(file) {
            const preview = document.getElementById('filePreview');
            const fileName = document.getElementById('fileName');
            const fileSize = document.getElementById('fileSize');
            
            if (preview && fileName && fileSize) {
                fileName.textContent = file.name;
                fileSize.textContent = this.formatFileSize(file.size);
                preview.style.display = 'block';
            }
        },
        
        formatFileSize: function(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        
        handleSubmit: async function(e) {
            e.preventDefault();
            
            if (!this.currentFile) {
                SmartFinanceApp.utils.showToast('Please select a file to upload', 'warning');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', this.currentFile);
            
            // Add processing options
            const options = ['autoCategories', 'skipDuplicates', 'extractDates', 'detectMerchants'];
            options.forEach(option => {
                const checkbox = document.getElementById(option);
                if (checkbox) {
                    formData.append(option, checkbox.checked);
                }
            });
            
            this.showProcessingState();
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                this.hideProcessingState();
                
                if (result.error) {
                    SmartFinanceApp.utils.showToast(result.error, 'danger');
                    this.showUploadForm();
                } else {
                    this.showResults(result);
                    SmartFinanceApp.utils.showToast(result.success, 'success');
                }
                
            } catch (error) {
                console.error('Upload error:', error);
                this.hideProcessingState();
                this.showUploadForm();
                SmartFinanceApp.utils.showToast('An error occurred while processing your file. Please try again.', 'danger');
            }
        },
        
        showProcessingState: function() {
            document.getElementById('uploadForm').style.display = 'none';
            document.getElementById('processingStatus').style.display = 'block';
            this.simulateProgress();
        },
        
        hideProcessingState: function() {
            document.getElementById('processingStatus').style.display = 'none';
        },
        
        showUploadForm: function() {
            document.getElementById('uploadForm').style.display = 'block';
        },
        
        simulateProgress: function() {
            const progressBar = document.querySelector('.progress-bar');
            if (!progressBar) return;
            
            let width = 0;
            const interval = setInterval(() => {
                width += Math.random() * 15;
                if (width >= 95) {
                    width = 95;
                    clearInterval(interval);
                }
                progressBar.style.width = width + '%';
            }, 500);
        },
        
        showResults: function(data) {
            const resultsDiv = document.getElementById('processingResults');
            if (!resultsDiv) return;
            
            // Parse results and update UI
            const message = data.success || '';
            const processedMatch = message.match(/(\d+) transactions/);
            const processedCount = processedMatch ? processedMatch[1] : '0';
            
            // Update statistics
            const elements = {
                processedCount: processedCount,
                categorizedCount: Math.floor(processedCount * 0.8),
                merchantsFound: Math.floor(processedCount * 0.6),
                confidenceScore: '85%'
            };
            
            Object.entries(elements).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) {
                    element.textContent = value;
                }
            });
            
            resultsDiv.style.display = 'block';
        }
    },
    
    // Initialize the application
    init: function() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initializeComponents());
        } else {
            this.initializeComponents();
        }
    },
    
    initializeComponents: function() {
        // Initialize components based on current page
        const currentPage = document.body.getAttribute('data-page');
        
        switch (currentPage) {
            case 'dashboard':
                this.dashboard.init();
                break;
            case 'upload':
                this.upload.init();
                break;
        }
        
        // Initialize common components
        this.initializeCommonComponents();
    },
    
    initializeCommonComponents: function() {
        // Initialize tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
        // Initialize popovers
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function (popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
        
        // Add smooth scrolling for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }
};

// Initialize the app
SmartFinanceApp.init();

// Global utility functions for backward compatibility
window.refreshDashboard = function() {
    if (SmartFinanceApp.dashboard && SmartFinanceApp.dashboard.refresh) {
        SmartFinanceApp.dashboard.refresh();
    }
};

window.clearFile = function() {
    const fileInput = document.getElementById('fileInput');
    const filePreview = document.getElementById('filePreview');
    const submitBtn = document.getElementById('submitBtn');
    
    if (fileInput) fileInput.value = '';
    if (filePreview) filePreview.style.display = 'none';
    if (submitBtn) submitBtn.disabled = true;
    
    if (SmartFinanceApp.upload) {
        SmartFinanceApp.upload.currentFile = null;
    }
};
