from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
from backend.services.nlp_processor import TransactionProcessor
from backend.services.savings_analyzer import SavingsAnalyzer
from backend.models.database_models import db, User, Transaction, Category

# Try to import Gmail service (optional)
try:
    from backend.services.gmail_service import GmailService
    from backend.services.multi_gmail_service import MultiAccountGmailService
    GMAIL_INTEGRATION_AVAILABLE = True
except ImportError:
    GMAIL_INTEGRATION_AVAILABLE = False
    print("Gmail integration not available. Install dependencies: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

app = Flask(__name__, 
           template_folder='frontend/templates',
           static_folder='frontend/static')

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath("database/finance_automator.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Data source configuration - Choose between 'sample' or 'gmail'
# Set via environment variable: export DATA_SOURCE_MODE=gmail
# Or change default here to 'gmail' for real email integration
app.config['DATA_SOURCE_MODE'] = os.getenv('DATA_SOURCE_MODE', 'sample')  # Options: 'sample' or 'gmail'

# Initialize extensions
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize NLP and Analytics services
transaction_processor = TransactionProcessor()
savings_analyzer = SavingsAnalyzer()

def get_category_id_from_name(category_name):
    """Helper function to get category ID from category name"""
    if not category_name:
        # Default to 'Other' category if no category provided
        category = Category.query.filter_by(name='Other').first()
        return category.id if category else 1
    
    # Create a mapping from lowercase NLP category names to database category names
    category_mapping = {
        'groceries': 'Groceries',
        'utilities': 'Utilities', 
        'transportation': 'Transportation',
        'entertainment': 'Entertainment',
        'healthcare': 'Healthcare',
        'dining': 'Dining',
        'shopping': 'Shopping',
        'bills': 'Bills',
        'education': 'Education',
        'other': 'Other'
    }
    
    # Map NLP category name to database category name
    db_category_name = category_mapping.get(category_name.lower(), 'Other')
    
    # Get category from database
    category = Category.query.filter_by(name=db_category_name).first()
    
    if category:
        return category.id
    else:
        # Fallback to 'Other' category
        other_category = Category.query.filter_by(name='Other').first()
        return other_category.id if other_category else 1

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        # Create new user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password_hash=hashed_password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's recent transactions
    recent_transactions = Transaction.query.filter_by(user_id=current_user.id)\
                                         .order_by(Transaction.date.desc())\
                                         .limit(10).all()
    
    # Get spending summary
    total_spending = db.session.query(db.func.sum(Transaction.amount))\
                              .filter_by(user_id=current_user.id).scalar() or 0
    
    # Get category breakdown
    category_spending = db.session.query(Category.name, db.func.sum(Transaction.amount))\
                                 .join(Transaction)\
                                 .filter(Transaction.user_id == current_user.id)\
                                 .group_by(Category.name).all()
    
    return render_template('dashboard.html', 
                         recent_transactions=recent_transactions,
                         total_spending=total_spending,
                         category_spending=category_spending)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_data():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Process the uploaded file
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                
                # Extract transactions using NLP
                transactions = transaction_processor.extract_transactions(text_content)
                
                # Save transactions to database
                saved_count = 0
                for trans_data in transactions:
                    # Get category ID from category name
                    category_id = get_category_id_from_name(trans_data.get('category'))
                    
                    transaction = Transaction(
                        user_id=current_user.id,
                        amount=trans_data['amount'],
                        description=trans_data['description'],
                        date=trans_data['date'],
                        category_id=category_id,
                        merchant=trans_data.get('merchant', ''),
                        transaction_type=trans_data.get('type', 'debit')
                    )
                    db.session.add(transaction)
                    saved_count += 1
                
                db.session.commit()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                return jsonify({'success': f'Successfully processed {saved_count} transactions'}), 200
                
            except Exception as e:
                return jsonify({'error': f'Error processing file: {str(e)}'}), 500
    
    return render_template('upload.html')

@app.route('/analytics')
@login_required
def analytics():
    """Advanced analytics page with real user data"""
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    # Get time period from query params (default: last 6 months)
    months = request.args.get('months', 6, type=int)
    start_date = datetime.now() - timedelta(days=months*30)
    
    # Get all user transactions
    transactions = Transaction.query.filter_by(user_id=current_user.id)\
                                   .filter(Transaction.date >= start_date)\
                                   .order_by(Transaction.date.desc()).all()
    
    # Calculate summary statistics
    total_spending = sum(t.amount for t in transactions if t.transaction_type == 'debit')
    total_income = sum(t.amount for t in transactions if t.transaction_type == 'credit')
    total_transactions = len(transactions)
    avg_transaction = total_spending / total_transactions if total_transactions > 0 else 0
    
    # Get active categories
    active_categories = db.session.query(Category.name, db.func.count(Transaction.id))\
                                 .join(Transaction)\
                                 .filter(Transaction.user_id == current_user.id)\
                                 .filter(Transaction.date >= start_date)\
                                 .filter(Transaction.transaction_type == 'debit')\
                                 .group_by(Category.name)\
                                 .all()
    
    # Category spending breakdown
    category_spending = db.session.query(
        Category.name,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction)\
     .filter(Transaction.user_id == current_user.id)\
     .filter(Transaction.date >= start_date)\
     .filter(Transaction.transaction_type == 'debit')\
     .group_by(Category.name)\
     .order_by(db.text('total DESC'))\
     .all()
    
    # Top merchants
    top_merchants = db.session.query(
        Transaction.merchant,
        db.func.count(Transaction.id).label('count'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(Transaction.user_id == current_user.id)\
     .filter(Transaction.date >= start_date)\
     .filter(Transaction.transaction_type == 'debit')\
     .filter(Transaction.merchant != '')\
     .group_by(Transaction.merchant)\
     .order_by(db.text('total DESC'))\
     .limit(5)\
     .all()
    
    # Monthly spending trend
    monthly_spending = db.session.query(
        db.func.strftime('%Y-%m', Transaction.date).label('month'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(Transaction.user_id == current_user.id)\
     .filter(Transaction.date >= start_date)\
     .filter(Transaction.transaction_type == 'debit')\
     .group_by(db.func.strftime('%Y-%m', Transaction.date))\
     .order_by('month')\
     .all()
    
    # Get previous month's spending for comparison
    previous_month_start = datetime.now() - timedelta(days=60)
    previous_month_end = datetime.now() - timedelta(days=30)
    previous_spending = sum(t.amount for t in transactions 
                          if previous_month_start <= t.date <= previous_month_end 
                          and t.transaction_type == 'debit')
    
    current_month_spending = sum(t.amount for t in transactions 
                               if t.date >= datetime.now() - timedelta(days=30)
                               and t.transaction_type == 'debit')
    
    spending_change = ((current_month_spending - previous_spending) / previous_spending * 100) if previous_spending > 0 else 0
    
    # Calculate savings
    current_month_income = sum(t.amount for t in transactions 
                              if t.date >= datetime.now() - timedelta(days=30)
                              and t.transaction_type == 'credit')
    savings_this_month = current_month_income - current_month_spending
    
    return render_template('analytics.html',
                         total_spending=total_spending,
                         total_income=total_income,
                         total_transactions=total_transactions,
                         avg_transaction=avg_transaction,
                         active_categories=len(active_categories),
                         category_spending=category_spending,
                         top_merchants=top_merchants,
                         monthly_spending=monthly_spending,
                         spending_change=spending_change,
                         savings_this_month=savings_this_month,
                         months_period=months)

@app.route('/savings')
@login_required
def savings():
    # Generate savings recommendations
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    recommendations = savings_analyzer.generate_recommendations(user_transactions)
    
    return render_template('savings.html', recommendations=recommendations)

# Gmail Integration Routes
@app.route('/gmail-setup')
@login_required
def gmail_setup():
    """Setup page for Gmail API integration"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available. Please install required dependencies.'}), 400
    
    # Don't initialize Gmail service immediately to avoid OAuth issues
    setup_instructions = {
        'step_1': 'Go to Google Cloud Console (https://console.cloud.google.com/)',
        'step_2': 'Create a new project or select existing project',
        'step_3': 'Enable Gmail API for your project',
        'step_4': 'Configure OAuth consent screen (add your email as test user)',
        'step_5': 'Create OAuth2 credentials (Desktop application type)',
        'step_6': 'Add redirect URIs: http://localhost:8080/, http://localhost:8081/',
        'step_7': 'Download credentials.json file and place in project root',
        'required_files': ['credentials.json (from Google Cloud Console)'],
        'oauth_consent_note': 'Important: Add your email as a test user in OAuth consent screen'
    }
    
    return render_template('gmail_setup.html', 
                         instructions=setup_instructions,
                         available=GMAIL_INTEGRATION_AVAILABLE)

@app.route('/api/gmail/sync', methods=['POST'])
@login_required
def sync_gmail():
    """Sync transactions - supports both sample data and real Gmail integration"""
    from datetime import datetime, timedelta
    import random
    
    try:
        # Get data source mode from config or request
        data = request.get_json() if request.is_json else {}
        mode = data.get('mode', app.config['DATA_SOURCE_MODE'])  # Can override via request
        days_back = data.get('days_back', 7)
        
        # MODE 1: REAL GMAIL INTEGRATION
        if mode == 'gmail':
            if not GMAIL_INTEGRATION_AVAILABLE:
                return jsonify({
                    'error': 'Gmail integration not available. Install dependencies: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib',
                    'suggestion': 'Switch to sample mode by setting mode=sample in request'
                }), 400
            
            # Initialize Gmail service
            gmail_service = GmailService()
            
            if not gmail_service.authenticated:
                return jsonify({
                    'error': 'Gmail not authenticated. Please set up Gmail credentials.',
                    'suggestion': 'Visit /gmail-setup to configure Gmail integration'
                }), 400
            
            # Fetch emails from Gmail
            print(f"🔍 Fetching emails from Gmail (last {days_back} days)...")
            emails = gmail_service.search_transaction_emails(days_back=days_back)
            print(f"📧 Found {len(emails)} emails to process")
            
            if not emails:
                return jsonify({
                    'message': 'No transaction emails found in Gmail',
                    'count': 0,
                    'skipped': 0,
                    'mode': 'gmail'
                }), 200
            
            # Initialize NLP processor
            total_processed = 0
            total_skipped = 0
            
            for email in emails:
                # Check if already processed by Gmail message ID
                existing = Transaction.query.filter_by(
                    user_id=current_user.id,
                    gmail_message_id=email.get('id')
                ).first()
                
                if existing:
                    total_skipped += 1
                    continue
                
                # Process email with NLP
                transactions_data = transaction_processor.process_text(email['body'])
                
                for trans_data in transactions_data:
                    # Double check: look for duplicates by amount, date and description
                    description_start = trans_data['description'][:100]
                    existing_duplicate = Transaction.query.filter_by(
                        user_id=current_user.id,
                        amount=trans_data['amount'],
                        transaction_type=trans_data.get('type', 'debit')
                    ).filter(
                        Transaction.date >= trans_data['date'] - timedelta(minutes=5),
                        Transaction.date <= trans_data['date'] + timedelta(minutes=5)
                    ).filter(
                        Transaction.description.like(f"{description_start}%")
                    ).first()
                    
                    if existing_duplicate:
                        total_skipped += 1
                        continue
                    
                    # Get category ID from category name
                    category_id = get_category_id_from_name(trans_data.get('category'))
                    
                    transaction = Transaction(
                        user_id=current_user.id,
                        amount=trans_data['amount'],
                        description=trans_data['description'],
                        date=trans_data['date'],
                        category_id=category_id,
                        merchant=trans_data.get('merchant', ''),
                        transaction_type=trans_data.get('type', 'debit'),
                        source='gmail',
                        gmail_message_id=email.get('id'),
                        raw_text=email['body'][:1000],
                        confidence_score=trans_data.get('confidence', 0.8)
                    )
                    db.session.add(transaction)
                    total_processed += 1
                    print(f"✅ Gmail: ₹{trans_data['amount']} - {trans_data['description']}")
            
            db.session.commit()
            
            return jsonify({
                'message': f'Successfully synced {total_processed} transactions from Gmail',
                'count': total_processed,
                'skipped': total_skipped,
                'emails_processed': len(emails),
                'mode': 'gmail'
            }), 200
        
        # MODE 2: SAMPLE DATA (DEFAULT)
        else:
            print("📊 Using SAMPLE DATA mode - Processing email-like text samples")
            
            # Initialize NLP processor for sample emails
            processor = transaction_processor
            
            # Sample EMAIL TEXTS for NLP processor to parse (realistic banking emails)
            sample_email_texts = [
                # HDFC Bank samples (various formats)
                """Dear Customer, Your A/c XX1234 is debited with Rs.1,250.50 on 25-Nov-24 for purchase at BIG BAZAAR. 
                Available balance: Rs.45,230.75. Info: HDFC Bank""",
                
                """Alert: Rs 850.75 debited from your account XX1234 on 26-Nov-24. 
                Transaction at DMART SUPERMARKET via Card ending 4567. 
                Avl Bal: Rs 44,380.00 -HDFC Bank""",
                
                # SBI Bank samples
                """SBI: Your account XX5678 debited by INR 2,100.00 on 24-Nov-24 14:32 PM 
                at RELIANCE FRESH. Ref# 123456789. Avl bal INR 42,280.00""",
                
                """Transaction Alert: INR 450.00 spent on 25-Nov-24 at STARBUCKS COFFEE using card XX9012. 
                Current balance: INR 41,830.00 -State Bank of India""",
                
                # ICICI Bank samples
                """ICICI Bank: Rs.1200.00 debited from A/c XX3456 on 26-NOV-24 
                for txn at PIZZA HUT. Available Bal:Rs.40,630.00""",
                
                """Your ICICI Bank Card XX7890 charged Rs 350 at MCDONALDS on 27-Nov-24. 
                Avl limit: Rs 40,280""",
                
                # UPI transactions
                """Rs 800 debited from your a/c XX1234 via UPI to SWIGGY on 25-Nov-24 18:45. 
                UPI Ref: 435678901234. Bal: Rs 39,480 -HDFC""",
                
                """UPI Payment successful! Rs.250.00 paid to UBER INDIA via UPI on 26-Nov-24. 
                Ref: 987654321098. Account balance: Rs.39,230.00""",
                
                # Online shopping
                """Payment of Rs 3,500.00 made to AMAZON SELLER SERVICES on 24-Nov-24 
                from card XX4567. Transaction ID: AMZ123456789. -ICICI Bank""",
                
                """Your a/c debited Rs.1,800.00 on 25-Nov-24 for MYNTRA DESIGNS purchase. 
                Order ID: MYN987654. Balance: Rs.35,930.00""",
                
                """Card transaction alert: Rs 2,200 spent at FLIPKART on 26-Nov-24. 
                Txn ref: FKT456789. Available bal: Rs 33,730""",
                
                # Entertainment & subscriptions
                """Your subscription payment of Rs.199.00 to NETFLIX.COM processed successfully on 25-Nov-24. 
                Card XX5678 charged. Next billing: 25-Dec-24""",
                
                """Auto-debit: Rs 149 paid to SPOTIFY PREMIUM on 26-Nov-24 from a/c XX1234. 
                Subscription active till 26-Dec-24. Bal: Rs 33,382""",
                
                """Rs.500.00 paid for BOOKMYSHOW tickets on 27-Nov-24. 
                Booking ID: BMS123456. Transaction successful.""",
                
                # Transportation
                """OLA CABS: Payment of Rs 150 completed on 25-Nov-24. 
                Trip ID: OLA123456789. Paid via UPI from XX1234""",
                
                """Fuel purchase of Rs.2,500.00 at HP PETROL PUMP on 26-Nov-24 14:30 
                using card XX9012. Balance: Rs.30,732.00""",
                
                # Utilities & bills
                """BESCOM Bill Payment: Rs 2,800.00 debited from a/c XX1234 on 25-Nov-24. 
                Bill period: Oct-24. Ref: BES987654321. Balance: Rs 27,932""",
                
                """Your Airtel Broadband bill of Rs.1,200.00 paid successfully on 26-Nov-24. 
                Service number: 9876543210. Account: XX5678""",
                
                """Mobile recharge of Rs 450 for Jio number 9876543210 successful. 
                Validity extended to 26-Dec-24. Paid from card XX1234""",
                
                # Healthcare
                """Payment of Rs.800.00 made to APOLLO PHARMACY on 25-Nov-24. 
                Prescription ID: APL123456. Card XX4567 used.""",
                
                """Rs 1,500 paid to CITY HOSPITAL for consultation on 26-Nov-24. 
                Patient ID: 123456. UPI Ref: 456789012345""",
                
                # Large payments (EMI, credit card)
                """Dear Customer, Rs.15,000.00 paid towards HDFC Credit Card bill on 25-Nov-24. 
                Card ending 4567. Due date: 15-Dec-24. Outstanding: Rs.5,000.00""",
                
                """EMI Debit Alert: Rs 25,000 deducted from a/c XX5678 for SBI HOME LOAN on 26-Nov-24. 
                Loan A/c: HL123456789. Balance: Rs.52,932.00 -SBI""",
                
                # Credits/Income
                """Rs.75,000.00 credited to your account XX1234 on 25-Nov-24. 
                Description: SALARY CREDIT - COMPANY PAYROLL. Balance: Rs.1,27,932.00""",
                
                """IMPS Credit: Rs 5,000.00 received in a/c XX1234 on 26-Nov-24 20:15. 
                From: FREELANCE CLIENT. Ref: IMPS123456789. Bal: Rs 1,32,932""",
                
                # WRONG/MALFORMED SAMPLES (for testing processor robustness)
                
                # Missing amount
                """Alert: Transaction at Big Bazaar on 25-Nov-24. 
                Your card was used. Please check your account.""",
                
                # Promotional email (should be filtered)
                """SALE ALERT! Get 50% off on all products at Big Bazaar! 
                Hurry! Limited time offer. Shop now and save big!""",
                
                # Incomplete transaction
                """Payment failed at Amazon on 26-Nov-24. 
                Insufficient balance. Please add funds to your account.""",
                
                # OTP/Security message (not a transaction)
                """Your OTP for HDFC NetBanking is 123456. Valid for 10 minutes. 
                Do not share with anyone. -HDFC Bank""",
                
                # Account statement notification (not a transaction)
                """Your account statement for Oct-2024 is ready. 
                Download from netbanking. Total transactions: 45. -ICICI Bank""",
                
                # Malformed amount format
                """Rs abc paid to merchant on date. Transaction successful. 
                Balance: xyz rupees""",
                
                # Very old format
                """Dear Sir/Madam, We wish to inform you that an amount of 
                Rupees Five Hundred Fifty only has been debited from your account 
                on the twenty-fifth day of November.""",
                
                # Multiple amounts (should pick transaction amount)
                """Rs 999.00 debited for purchase at Store XYZ on 25-Nov-24. 
                Cashback: Rs 50.00. Net amount: Rs 949.00. Balance: Rs 50,000.00""",
            ]
            
            # Remove existing Gmail transactions to avoid duplicates
            existing_gmail_transactions = Transaction.query.filter_by(
                user_id=current_user.id,
                source='gmail'
            ).all()
            
            removed_count = len(existing_gmail_transactions)
            for transaction in existing_gmail_transactions:
                db.session.delete(transaction)
            
            print(f"🗑️ Removed {removed_count} existing sample transactions")
            
            # Process sample emails using NLP processor
            processed_count = 0
            skipped_count = 0
            
            # Generate dates across last 6 months for realistic trends
            base_date = datetime.now() - timedelta(days=180)  # 6 months ago
            
            # Select 25-30 random email samples (including some malformed ones)
            selected_emails = random.sample(sample_email_texts, min(30, len(sample_email_texts)))
            
            print(f"\n📧 Processing {len(selected_emails)} sample emails through NLP processor...")
            print(f"📅 Date range: {base_date.strftime('%d %b %Y')} to {datetime.now().strftime('%d %b %Y')}")
            
            # Create transaction date distribution for better trends
            # More transactions in recent months, varied throughout the week
            date_weights = []
            for day_offset in range(180):
                # Recent months get more weight (more transactions)
                weight = 1 + (day_offset / 30)  # Increases over time
                date_weights.append(weight)
            
            for i, email_text in enumerate(selected_emails, 1):
                print(f"\n--- Processing Sample Email {i}/{len(selected_emails)} ---")
                print(f"📄 Email text: {email_text[:100]}...")
                
                # Use NLP processor to extract transaction details
                try:
                    transactions_data = processor.process_text(email_text)
                    
                    if not transactions_data:
                        print(f"⚠️ NLP Processor: No transactions found in email {i}")
                        skipped_count += 1
                        continue
                    
                    # Process each transaction found in the email
                    for trans_data in transactions_data:
                        # Generate weighted random date for realistic distribution
                        # More recent dates are more likely
                        random_days = random.choices(range(180), weights=date_weights, k=1)[0]
                        
                        # Generate transaction date with varied times
                        transaction_date = base_date + timedelta(
                            days=random_days, 
                            hours=random.randint(6, 22),  # 6 AM to 10 PM
                            minutes=random.randint(0, 59),
                            seconds=random.randint(0, 59)
                        )
                        
                        # DON'T use parsed date from email - use our generated date for variety
                        # This ensures transactions are spread across 6 months
                        
                        print(f"📅 Generated date: {transaction_date.strftime('%d %b %Y')}")
                        
                        # Check for duplicates
                        existing = Transaction.query.filter(
                            Transaction.user_id == current_user.id,
                            Transaction.amount == trans_data['amount'],
                            Transaction.date >= transaction_date - timedelta(minutes=5),
                            Transaction.date <= transaction_date + timedelta(minutes=5)
                        ).first()
                        
                        if existing:
                            print(f"⏭️ Skipping duplicate: ₹{trans_data['amount']}")
                            skipped_count += 1
                            continue
                        
                        # Create transaction
                        transaction = Transaction(
                            user_id=current_user.id,
                            amount=trans_data['amount'],
                            description=trans_data.get('description', 'Sample transaction'),
                            date=transaction_date,
                            category_id=trans_data.get('category_id'),
                            merchant=trans_data.get('merchant', ''),
                            transaction_type=trans_data.get('transaction_type', 'debit'),
                            source='gmail',
                            gmail_message_id=f'sample_msg_{i}_{current_user.id}_{processed_count}',
                            raw_text=email_text[:500],  # Store original email text
                            confidence_score=trans_data.get('confidence', 0.85)
                        )
                        
                        db.session.add(transaction)
                        processed_count += 1
                        print(f"✅ Added: ₹{trans_data['amount']} - {trans_data.get('description', 'N/A')[:50]} (Confidence: {trans_data.get('confidence', 0.85):.2f})")
                
                except Exception as e:
                    print(f"❌ Error processing email {i}: {str(e)}")
                    skipped_count += 1
                    continue
            
            db.session.commit()
            
            print(f"\n{'='*60}")
            print(f"📊 SAMPLE DATA PROCESSING COMPLETE:")
            print(f"   ✅ Successfully processed: {processed_count} transactions")
            print(f"   ⚠️ Skipped/Failed: {skipped_count} emails")
            print(f"   🗑️ Removed old transactions: {removed_count}")
            print(f"{'='*60}\n")
            
            if removed_count > 0:
                message = f'Successfully processed {processed_count} transactions from {len(selected_emails)} sample emails (replaced {removed_count} old transactions)'
            else:
                message = f'Successfully processed {processed_count} transactions from {len(selected_emails)} sample emails'
            
            return jsonify({
                'message': message,
                'count': processed_count,
                'skipped': skipped_count,
                'emails_processed': len(selected_emails),
                'mode': 'sample'
            }), 200
        
    except Exception as e:
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500

@app.route('/api/gmail/status')
@login_required
def gmail_status():
    """Check Gmail integration status and current data source mode"""
    current_mode = app.config['DATA_SOURCE_MODE']
    
    if current_mode == 'gmail':
        if not GMAIL_INTEGRATION_AVAILABLE:
            return jsonify({
                'available': False,
                'authenticated': False,
                'mode': 'gmail',
                'error': 'Gmail API dependencies not installed',
                'message': 'Install dependencies: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib'
            })
        
        # Check if Gmail is authenticated
        gmail_service = GmailService()
        
        return jsonify({
            'available': GMAIL_INTEGRATION_AVAILABLE,
            'authenticated': gmail_service.authenticated,
            'mode': 'gmail',
            'message': 'Gmail integration active' if gmail_service.authenticated else 'Gmail authentication required - visit /gmail-setup'
        })
    else:
        return jsonify({
            'available': True,
            'authenticated': True,
            'mode': 'sample',
            'message': 'Sample data mode active - click sync to load demo transactions. To use Gmail, set mode to "gmail" in request or environment.'
        })

@app.route('/api/data-source/mode', methods=['GET', 'POST'])
@login_required
def data_source_mode():
    """Get or set the data source mode (sample or gmail)"""
    if request.method == 'POST':
        data = request.get_json()
        new_mode = data.get('mode', 'sample')
        
        if new_mode not in ['sample', 'gmail']:
            return jsonify({'error': 'Invalid mode. Use "sample" or "gmail"'}), 400
        
        app.config['DATA_SOURCE_MODE'] = new_mode
        
        return jsonify({
            'message': f'Data source mode changed to: {new_mode}',
            'mode': new_mode,
            'description': 'Sample data' if new_mode == 'sample' else 'Real Gmail integration'
        })
    
    # GET request - return current mode
    current_mode = app.config['DATA_SOURCE_MODE']
    return jsonify({
        'mode': current_mode,
        'description': 'Sample data' if current_mode == 'sample' else 'Real Gmail integration',
        'options': ['sample', 'gmail']
    })

@app.route('/api/gmail/debug')
@login_required
def gmail_debug():
    """Debug endpoint to check existing transactions"""
    try:
        # Count transactions by source
        gmail_count = Transaction.query.filter_by(user_id=current_user.id, source='gmail').count()
        total_count = Transaction.query.filter_by(user_id=current_user.id).count()
        
        # Get recent Gmail transactions
        recent_gmail = Transaction.query.filter_by(
            user_id=current_user.id,
            source='gmail'
        ).order_by(Transaction.date.desc()).limit(5).all()
        
        recent_list = []
        for t in recent_gmail:
            recent_list.append({
                'amount': float(t.amount),
                'description': t.description,
                'date': t.date.isoformat(),
                'merchant': t.merchant,
                'category': t.category.name if t.category else 'Unknown'
            })
        
        return jsonify({
            'gmail_transactions': gmail_count,
            'total_transactions': total_count,
            'recent_gmail': recent_list
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/force_refresh', methods=['POST'])
@login_required
def force_gmail_refresh():
    """Force refresh with fresh sample data by removing existing transactions and adding new ones"""
    try:
        # Remove all Gmail transactions for this user
        gmail_transactions = Transaction.query.filter_by(
            user_id=current_user.id,
            source='gmail'
        ).all()
        
        removed_count = len(gmail_transactions)
        for transaction in gmail_transactions:
            db.session.delete(transaction)
        
        db.session.commit()
        print(f"Removed {removed_count} existing Gmail transactions")
        
        # Same sample transaction logic as sync_gmail
        from datetime import datetime, timedelta
        import random
        
        # Extended sample transaction templates for force refresh
        sample_transactions = [
            # Groceries
            {'amount': 1450.25, 'description': 'More Megastore - Fresh produce and essentials', 'merchant': 'More Megastore', 'category': 'groceries', 'type': 'debit'},
            {'amount': 980.50, 'description': 'Spencer\'s Retail - Weekly grocery haul', 'merchant': 'Spencer\'s', 'category': 'groceries', 'type': 'debit'},
            {'amount': 2300.75, 'description': 'Nature\'s Basket - Organic food shopping', 'merchant': 'Nature\'s Basket', 'category': 'groceries', 'type': 'debit'},
            {'amount': 650.00, 'description': 'Local Kirana Store - Daily essentials', 'merchant': 'Kirana Store', 'category': 'groceries', 'type': 'debit'},
            
            # Dining & Food
            {'amount': 520.00, 'description': 'Cafe Coffee Day - Coffee and pastry', 'merchant': 'CCD', 'category': 'dining', 'type': 'debit'},
            {'amount': 1450.00, 'description': 'Dominos Pizza - Large pizza order', 'merchant': 'Dominos', 'category': 'dining', 'type': 'debit'},
            {'amount': 380.00, 'description': 'Subway - Healthy lunch combo', 'merchant': 'Subway', 'category': 'dining', 'type': 'debit'},
            {'amount': 920.00, 'description': 'Zomato Gold - Premium restaurant meal', 'merchant': 'Zomato', 'category': 'dining', 'type': 'debit'},
            {'amount': 280.00, 'description': 'Tea Post - Evening snacks', 'merchant': 'Tea Post', 'category': 'dining', 'type': 'debit'},
            
            # Transportation
            {'amount': 320.00, 'description': 'Ola Auto - Short distance ride', 'merchant': 'Ola', 'category': 'transportation', 'type': 'debit'},
            {'amount': 180.00, 'description': 'Metro Card Recharge - Monthly pass', 'merchant': 'Metro', 'category': 'transportation', 'type': 'debit'},
            {'amount': 2800.00, 'description': 'Indian Oil - Full tank fuel', 'merchant': 'Indian Oil', 'category': 'transportation', 'type': 'debit'},
            {'amount': 450.00, 'description': 'Rapid Metro - Airport express', 'merchant': 'Rapid Metro', 'category': 'transportation', 'type': 'debit'},
            
            # Shopping & E-commerce
            {'amount': 4200.00, 'description': 'Amazon Prime - Electronics and gadgets', 'merchant': 'Amazon', 'category': 'shopping', 'type': 'debit'},
            {'amount': 2100.00, 'description': 'Myntra End of Season Sale - Fashion haul', 'merchant': 'Myntra', 'category': 'shopping', 'type': 'debit'},
            {'amount': 1650.00, 'description': 'Nykaa Beauty - Cosmetics and skincare', 'merchant': 'Nykaa', 'category': 'shopping', 'type': 'debit'},
            {'amount': 2900.00, 'description': 'Flipkart Big Billion Days - Home appliances', 'merchant': 'Flipkart', 'category': 'shopping', 'type': 'debit'},
            {'amount': 850.00, 'description': 'Ajio Fashion - Trendy clothing', 'merchant': 'Ajio', 'category': 'shopping', 'type': 'debit'},
            
            # Entertainment
            {'amount': 600.00, 'description': 'PVR Cinemas - Movie tickets for 2', 'merchant': 'PVR', 'category': 'entertainment', 'type': 'debit'},
            {'amount': 399.00, 'description': 'Disney+ Hotstar - Annual subscription', 'merchant': 'Disney+ Hotstar', 'category': 'entertainment', 'type': 'debit'},
            {'amount': 299.00, 'description': 'Amazon Prime Video - Monthly plan', 'merchant': 'Prime Video', 'category': 'entertainment', 'type': 'debit'},
            {'amount': 750.00, 'description': 'GameStop - Video game purchase', 'merchant': 'GameStop', 'category': 'entertainment', 'type': 'debit'},
            
            # Utilities & Bills
            {'amount': 3200.00, 'description': 'BSES Delhi - Electricity bill payment', 'merchant': 'BSES', 'category': 'utilities', 'type': 'debit'},
            {'amount': 1450.00, 'description': 'JioFiber - High-speed internet monthly', 'merchant': 'JioFiber', 'category': 'utilities', 'type': 'debit'},
            {'amount': 599.00, 'description': 'Vi Postpaid - Mobile bill payment', 'merchant': 'Vi', 'category': 'utilities', 'type': 'debit'},
            {'amount': 850.00, 'description': 'Indraprastha Gas - Cooking gas refill', 'merchant': 'IGL', 'category': 'utilities', 'type': 'debit'},
            
            # Healthcare
            {'amount': 1200.00, 'description': 'MedPlus Pharmacy - Prescription medicines', 'merchant': 'MedPlus', 'category': 'healthcare', 'type': 'debit'},
            {'amount': 2500.00, 'description': 'Max Healthcare - Specialist consultation', 'merchant': 'Max Hospital', 'category': 'healthcare', 'type': 'debit'},
            {'amount': 450.00, 'description': '1mg Online Pharmacy - Health supplements', 'merchant': '1mg', 'category': 'healthcare', 'type': 'debit'},
            
            # Bills & Financial
            {'amount': 18500.00, 'description': 'ICICI Credit Card - Monthly payment', 'merchant': 'ICICI Bank', 'category': 'bills', 'type': 'debit'},
            {'amount': 32000.00, 'description': 'HDFC Home Loan - EMI payment', 'merchant': 'HDFC Bank', 'category': 'bills', 'type': 'debit'},
            {'amount': 5500.00, 'description': 'LIC Premium - Life insurance payment', 'merchant': 'LIC', 'category': 'bills', 'type': 'debit'},
            
            # Income/Credits
            {'amount': 85000.00, 'description': 'Salary Credit - Monthly compensation', 'merchant': 'Employer', 'category': 'other', 'type': 'credit'},
            {'amount': 8500.00, 'description': 'Freelance Project - Web development work', 'merchant': 'Client', 'category': 'other', 'type': 'credit'},
            {'amount': 2200.00, 'description': 'Investment Returns - Mutual fund dividend', 'merchant': 'SBI Mutual Fund', 'category': 'other', 'type': 'credit'},
            {'amount': 1200.00, 'description': 'Cashback Credit - Credit card rewards', 'merchant': 'HDFC Rewards', 'category': 'other', 'type': 'credit'},
        ]
        
        # Add sample transactions with random dates in the last 60 days
        processed_count = 0
        base_date = datetime.now() - timedelta(days=60)
        
        # Select 25-30 random transactions for force refresh
        selected_transactions = random.sample(sample_transactions, min(30, len(sample_transactions)))
        
        for i, trans_data in enumerate(selected_transactions):
            # Generate random date in the last 60 days
            random_days = random.randint(0, 60)
            transaction_date = base_date + timedelta(days=random_days, hours=random.randint(8, 20), minutes=random.randint(0, 59))
            
            # Get category ID from category name
            category_id = get_category_id_from_name(trans_data.get('category'))
            
            transaction = Transaction(
                user_id=current_user.id,
                amount=trans_data['amount'],
                description=trans_data['description'],
                date=transaction_date,
                category_id=category_id,
                merchant=trans_data.get('merchant', ''),
                transaction_type=trans_data.get('type', 'debit'),
                source='gmail',  # Mark as Gmail source for consistency
                gmail_message_id=f'refresh_sample_{i}_{current_user.id}',  # Unique refresh sample ID
                raw_text=f"Force refresh sample: {trans_data['description']}",
                confidence_score=0.98  # Very high confidence for sample data
            )
            db.session.add(transaction)
            processed_count += 1
            print(f"✅ Added fresh sample transaction: ₹{trans_data['amount']} - {trans_data['description']}")
        
        db.session.commit()
        
        message = f'Force refresh completed! Removed {removed_count} old transactions, Added {processed_count} fresh sample transactions'
        
        return jsonify({
            'message': message,
            'removed_count': removed_count,
            'added_count': processed_count,
            'emails_processed': processed_count
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Gmail force refresh failed: {str(e)}'}), 500

@app.route('/api/gmail/test_search')
@login_required
def test_gmail_search():
    """Test Gmail search with detailed debugging"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        from datetime import datetime, timedelta
        
        gmail_service = GmailService()
        
        if not gmail_service.authenticated:
            return jsonify({'error': 'Gmail not authenticated'}), 401
        
        # Test date calculation
        days_back = 30
        start_date = datetime.now() - timedelta(days=days_back)
        query_date = start_date.strftime('%Y/%m/%d')
        
        # Test basic search
        test_query = f'from:indusind.com'
        
        results = gmail_service.service.users().messages().list(
            userId='me',
            q=test_query,
            maxResults=10
        ).execute()
        
        messages = results.get('messages', [])
        
        debug_info = {
            'current_date': datetime.now().strftime('%Y/%m/%d'),
            'days_back': days_back,
            'calculated_start_date': query_date,
            'test_query': test_query,
            'messages_found': len(messages),
            'message_ids': [msg['id'] for msg in messages[:5]],  # First 5 message IDs
        }
        
        # If we found messages, get details for first one
        if messages:
            first_msg = gmail_service._get_email_details(messages[0]['id'])
            if first_msg:
                debug_info['first_email_subject'] = first_msg.get('subject', '')
                debug_info['first_email_sender'] = first_msg.get('sender', '')
                debug_info['first_email_snippet'] = first_msg.get('body', '')[:200]
        
        return jsonify({
            'debug_info': debug_info,
            'message': f'Test search completed. Found {len(messages)} emails.'
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Test search failed: {str(e)}'}), 500

# Multi-Account Gmail Routes
@app.route('/api/gmail/accounts', methods=['GET'])
@login_required
def list_gmail_accounts():
    """List all configured Gmail accounts"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        multi_gmail = MultiAccountGmailService()
        accounts = multi_gmail.list_accounts()
        return jsonify({'accounts': accounts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/accounts/add', methods=['POST'])
@login_required
def add_gmail_account():
    """Add a new Gmail account"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        data = request.get_json()
        account_name = data.get('account_name', f'account_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        
        multi_gmail = MultiAccountGmailService()
        
        if multi_gmail.add_account(account_name):
            accounts = multi_gmail.list_accounts()
            return jsonify({
                'message': f'Account {account_name} added successfully',
                'accounts': accounts
            })
        else:
            return jsonify({'error': 'Failed to add account'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/accounts/<account_name>/switch', methods=['POST'])
@login_required
def switch_gmail_account(account_name):
    """Switch to a different Gmail account"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        multi_gmail = MultiAccountGmailService()
        
        if multi_gmail.switch_account(account_name):
            return jsonify({'message': f'Switched to account {account_name}'})
        else:
            return jsonify({'error': 'Account not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/sync-all', methods=['POST'])
@login_required
def sync_all_gmail_accounts():
    """Sync transactions from all Gmail accounts"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        data = request.get_json() if request.is_json else {}
        days_back = data.get('days_back', 7)
        
        multi_gmail = MultiAccountGmailService()
        
        # Load existing accounts
        if os.path.exists('gmail_token.pickle'):
            multi_gmail.add_account('primary')
        
        all_transactions = multi_gmail.sync_all_accounts(days_back=days_back)
        
        total_processed = 0
        total_skipped = 0
        
        for account_name, account_data in all_transactions.items():
            transactions = account_data['transactions']
            
            for email in transactions:
                try:
                    # First check if we already processed this Gmail message
                    existing_by_gmail_id = Transaction.query.filter_by(
                        user_id=current_user.id,
                        gmail_message_id=email.get('id')
                    ).filter(
                        Transaction.source.like('gmail_%')
                    ).first()
                    
                    if existing_by_gmail_id:
                        total_skipped += 1
                        continue  # Skip already processed email
                    
                    # Process email body text
                    transactions_data = transaction_processor.process_text(email['body'])
                    
                    for trans_data in transactions_data:
                        # Double check: also look for duplicates by amount, date and partial description
                        description_start = trans_data['description'][:100]  # First 100 chars
                        existing = Transaction.query.filter_by(
                            user_id=current_user.id,
                            amount=trans_data['amount'],
                            transaction_type=trans_data.get('type', 'debit')
                        ).filter(
                            Transaction.date >= trans_data['date'] - timedelta(minutes=5),
                            Transaction.date <= trans_data['date'] + timedelta(minutes=5)
                        ).filter(
                            Transaction.description.like(f"{description_start}%")
                        ).first()
                        
                        if not existing:
                            # Get category ID from category name
                            category_id = get_category_id_from_name(trans_data.get('category'))
                            
                            transaction = Transaction(
                                user_id=current_user.id,
                                amount=trans_data['amount'],
                                description=trans_data['description'],
                                date=trans_data['date'],
                                category_id=category_id,
                                merchant=trans_data.get('merchant', ''),
                                transaction_type=trans_data.get('type', 'debit'),
                                source=f'gmail_{account_name}',
                                gmail_message_id=email.get('id'),  # Store Gmail message ID
                                raw_text=email['body'][:1000]  # Store first 1000 chars of original email
                            )
                            db.session.add(transaction)
                            total_processed += 1
                        else:
                            total_skipped += 1
                
                except Exception as e:
                    print(f"Error processing email: {e}")
                    continue
        
        db.session.commit()
        
        if total_processed == 0 and total_skipped > 0:
            message = f'No new transactions to sync. {total_skipped} transactions were already processed from all accounts.'
        elif total_skipped > 0:
            message = f'Successfully synced {total_processed} new transactions. {total_skipped} duplicates were skipped from all accounts.'
        else:
            message = f'Successfully synced {total_processed} transactions from all accounts'
        
        return jsonify({
            'message': message,
            'count': total_processed,
            'skipped': total_skipped,
            'accounts': list(all_transactions.keys())
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Multi-account sync failed: {str(e)}'}), 500

@app.route('/api/gmail/debug', methods=['POST'])
@login_required
def debug_gmail():
    """Debug Gmail integration to see what emails are found"""
    if not GMAIL_INTEGRATION_AVAILABLE:
        return jsonify({'error': 'Gmail integration not available'}), 400
    
    try:
        data = request.get_json() if request.is_json else {}
        days_back = data.get('days_back', 7)
        max_results = data.get('max_results', 20)
        strict_mode = data.get('strict_mode', True)  # Only financial senders by default
        
        gmail_service = GmailService()
        
        if not gmail_service.authenticated:
            return jsonify({'error': 'Gmail not authenticated'}), 400
        
        # Get raw emails
        emails = gmail_service.search_transaction_emails(days_back=days_back, max_results=max_results)
        
        # Return detailed email information for debugging
        debug_info = []
        for email in emails:
            sender = email.get('sender', 'Unknown Sender').lower()
            subject = email.get('subject', 'No Subject')
            body = email.get('body', '')
            
            # Check if sender is financial
            is_financial_sender = any(domain in sender for domain in [
                'bank', 'sbi', 'hdfc', 'icici', 'axis', 'kotak', 'citi', 
                'paytm', 'phonepe', 'gpay', 'credit', 'debit', 'wallet'
            ])
            
            # Check for transaction indicators
            has_transaction_terms = any(keyword in (body + subject).lower() 
                                      for keyword in ['debited', 'credited', 'transaction', 'payment', 'purchase', 'rs.', '₹', 'amount'])
            
            debug_info.append({
                'subject': subject,
                'sender': email.get('sender', 'Unknown Sender'),
                'date': email.get('raw_date', 'Unknown Date'),
                'body_preview': body[:200] + '...' if len(body) > 200 else body,
                'is_financial_sender': is_financial_sender,
                'has_transaction_terms': has_transaction_terms,
                'is_transaction': is_financial_sender and has_transaction_terms
            })
        
        return jsonify({
            'total_emails': len(emails),
            'emails': debug_info,
            'message': f'Found {len(emails)} emails to analyze',
            'filter_info': f'Searching {"financial senders only" if strict_mode else "all senders"} from last {days_back} days'
        })
        
    except Exception as e:
        return jsonify({'error': f'Debug failed: {str(e)}'}), 500

# API Routes
@app.route('/api/transactions')
@login_required
def api_transactions():
    transactions = Transaction.query.filter_by(user_id=current_user.id)\
                                  .order_by(Transaction.date.desc()).all()
    
    return jsonify([{
        'id': t.id,
        'amount': t.amount,
        'description': t.description,
        'date': t.date.isoformat(),
        'category': t.category.name if t.category else 'Uncategorized',
        'merchant': t.merchant,
        'type': t.transaction_type
    } for t in transactions])

@app.route('/api/spending-chart')
@login_required
def api_spending_chart():
    """Get spending data for different time periods: 6days, 30days, or 6months"""
    from datetime import datetime, timedelta
    
    # Get period parameter (default: 6days)
    period = request.args.get('period', '6days')
    
    # Calculate date range based on period
    end_date = datetime.now()
    
    if period == '6days':
        start_date = end_date - timedelta(days=6)
        date_format = '%Y-%m-%d'  # Daily format
        group_by_format = '%Y-%m-%d'
        label_format = '%d %b'  # "25 Nov"
    elif period == '7days':
        start_date = end_date - timedelta(days=7)
        date_format = '%Y-%m-%d'  # Daily format
        group_by_format = '%Y-%m-%d'
        label_format = '%d %b'  # "25 Nov"
    elif period == '30days':
        start_date = end_date - timedelta(days=30)
        date_format = '%Y-%m-%d'  # Daily format
        group_by_format = '%Y-%m-%d'
        label_format = '%d %b'  # "25 Nov"
    elif period == '6months':
        start_date = end_date - timedelta(days=180)
        date_format = '%Y-%m'  # Monthly format
        group_by_format = '%Y-%m'
        label_format = '%b %Y'  # "Nov 2024"
    else:
        # Default to 7 days
        start_date = end_date - timedelta(days=6)
        date_format = '%Y-%m-%d'
        group_by_format = '%Y-%m-%d'
        label_format = '%d %b'
    
    # Query spending data grouped by the appropriate time period
    spending_data = db.session.query(
        db.func.strftime(group_by_format, Transaction.date).label('period'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.user_id == current_user.id,
        Transaction.transaction_type == 'debit',
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).group_by(db.func.strftime(group_by_format, Transaction.date))\
     .order_by('period').all()
    
    # Format labels for display
    labels = []
    amounts = []
    
    for item in spending_data:
        try:
            if period == '6months':
                # Parse "YYYY-MM" format
                date_obj = datetime.strptime(item.period, '%Y-%m')
                labels.append(date_obj.strftime(label_format))
            else:
                # Parse "YYYY-MM-DD" format
                date_obj = datetime.strptime(item.period, '%Y-%m-%d')
                labels.append(date_obj.strftime(label_format))
            amounts.append(float(item.total))
        except Exception as e:
            print(f"Error formatting date {item.period}: {e}")
            labels.append(item.period)
            amounts.append(float(item.total))
    
    return jsonify({
        'labels': labels,
        'amounts': amounts,
        'period': period,
        'months': labels,  # Keep for backward compatibility
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    })

@app.route('/api/category-chart')
@login_required
def api_category_chart():
    # Get category breakdown
    category_data = db.session.query(
        Category.name,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction)\
     .filter(Transaction.user_id == current_user.id)\
     .filter(Transaction.transaction_type == 'debit')\
     .group_by(Category.name).all()
    
    return jsonify({
        'categories': [item.name for item in category_data],
        'amounts': [float(item.total) for item in category_data]
    })

@app.route('/api/analytics/insights')
@login_required
def api_analytics_insights():
    """Generate PERSONALIZED AI-powered insights based on user's actual spending patterns"""
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    insights = []
    
    # Get transactions from last 30 days for current analysis
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_transactions = Transaction.query.filter_by(user_id=current_user.id)\
                                          .filter(Transaction.date >= thirty_days_ago)\
                                          .all()
    
    # Debug output
    print(f"🔍 DEBUG INSIGHTS - User: {current_user.username}")
    print(f"🔍 DEBUG INSIGHTS - Recent transactions (last 30 days): {len(recent_transactions)}")
    
    # Get transactions from 30-60 days ago for comparison
    sixty_days_ago = datetime.now() - timedelta(days=60)
    previous_transactions = Transaction.query.filter_by(user_id=current_user.id)\
                                            .filter(Transaction.date >= sixty_days_ago)\
                                            .filter(Transaction.date < thirty_days_ago)\
                                            .all()
    
    print(f"🔍 DEBUG INSIGHTS - Previous transactions (30-60 days ago): {len(previous_transactions)}")
    
    if not recent_transactions:
        print(f"⚠️ WARNING - No transactions found for user {current_user.username}")
        return jsonify({'insights': [{
            'type': 'info',
            'icon': 'fa-info-circle',
            'title': 'No Transaction Data',
            'description': 'Start syncing your transactions to receive personalized financial insights! Click the "Sync Email" button on the dashboard.',
            'impact': 'Low',
            'confidence': 100
        }]})
    
    # Calculate user-specific metrics
    username = current_user.username.capitalize()
    
    # Insight 1: PERSONALIZED Weekend vs Weekday spending analysis
    weekend_spending = sum(t.amount for t in recent_transactions 
                          if t.date.weekday() >= 5 and t.transaction_type == 'debit')
    weekday_spending = sum(t.amount for t in recent_transactions 
                          if t.date.weekday() < 5 and t.transaction_type == 'debit')
    
    # Count actual unique days
    weekend_dates = set(t.date.date() for t in recent_transactions if t.date.weekday() >= 5)
    weekday_dates = set(t.date.date() for t in recent_transactions if t.date.weekday() < 5)
    
    if len(weekend_dates) > 0 and len(weekday_dates) > 0:
        weekend_avg = weekend_spending / len(weekend_dates)
        weekday_avg = weekday_spending / len(weekday_dates)
        
        if weekend_avg > weekday_avg * 1.3:
            increase_pct = int((weekend_avg - weekday_avg) / weekday_avg * 100)
            weekend_categories = defaultdict(float)
            for t in recent_transactions:
                if t.date.weekday() >= 5 and t.transaction_type == 'debit' and t.category:
                    weekend_categories[t.category.name] += t.amount
            
            top_weekend_category = max(weekend_categories, key=weekend_categories.get) if weekend_categories else 'entertainment'
            
            insights.append({
                'type': 'warning',
                'icon': 'fa-calendar-weekend',
                'title': f'{username}, Your Weekend Spending Pattern',
                'description': f'You spend {increase_pct}% more on weekends (₹{weekend_avg:.0f}/day vs ₹{weekday_avg:.0f}/day). {top_weekend_category.capitalize()} is your main weekend expense category. Try planning budget-friendly weekend activities!',
                'impact': 'High',
                'confidence': 92
            })
        elif weekday_avg > weekend_avg * 1.2:
            insights.append({
                'type': 'success',
                'icon': 'fa-thumbs-up',
                'title': f'{username}, Great Weekend Control!',
                'description': f'Your weekend spending (₹{weekend_avg:.0f}/day) is lower than weekdays (₹{weekday_avg:.0f}/day). You\'re making smart financial choices on leisure time!',
                'impact': 'Positive',
                'confidence': 90
            })
    
    # Insight 2: PERSONALIZED Top category with specific amounts and trends
    category_totals = {}
    category_counts = {}
    for t in recent_transactions:
        if t.transaction_type == 'debit' and t.category:
            category_totals[t.category.name] = category_totals.get(t.category.name, 0) + t.amount
            category_counts[t.category.name] = category_counts.get(t.category.name, 0) + 1
    
    print(f"🔍 DEBUG INSIGHTS - Category totals: {category_totals}")
    print(f"🔍 DEBUG INSIGHTS - Category counts: {category_counts}")
    
    # Previous period categories for comparison
    prev_category_totals = {}
    for t in previous_transactions:
        if t.transaction_type == 'debit' and t.category:
            prev_category_totals[t.category.name] = prev_category_totals.get(t.category.name, 0) + t.amount
    
    print(f"🔍 DEBUG INSIGHTS - Previous category totals: {prev_category_totals}")
    
    if category_totals:
        top_category = max(category_totals, key=category_totals.get)
        top_amount = category_totals[top_category]
        top_count = category_counts[top_category]
        total_spending = sum(category_totals.values())
        percentage = (top_amount / total_spending * 100) if total_spending > 0 else 0
        avg_per_transaction = top_amount / top_count if top_count > 0 else 0
        
        # Check if spending increased
        prev_amount = prev_category_totals.get(top_category, 0)
        trend = ""
        if prev_amount > 0:
            change_pct = ((top_amount - prev_amount) / prev_amount * 100)
            if change_pct > 15:
                trend = f" This is {abs(change_pct):.0f}% higher than last month."
            elif change_pct < -15:
                trend = f" Great job - you reduced this by {abs(change_pct):.0f}% from last month!"
        
        if percentage > 30:
            insights.append({
                'type': 'info',
                'icon': 'fa-chart-pie',
                'title': f'{username}, {top_category.capitalize()} is Your Top Expense',
                'description': f'You spent ₹{top_amount:,.0f} on {top_category} ({percentage:.0f}% of expenses) across {top_count} transactions (avg ₹{avg_per_transaction:.0f}/transaction).{trend}',
                'impact': 'Medium',
                'confidence': 96
            })
    
    # Insight 3: PERSONALIZED Savings with specific goals
    total_income = sum(t.amount for t in recent_transactions if t.transaction_type == 'credit')
    total_expenses = sum(t.amount for t in recent_transactions if t.transaction_type == 'debit')
    savings = total_income - total_expenses
    savings_rate = (savings / total_income * 100) if total_income > 0 else 0
    
    # Previous period comparison
    prev_income = sum(t.amount for t in previous_transactions if t.transaction_type == 'credit')
    prev_expenses = sum(t.amount for t in previous_transactions if t.transaction_type == 'debit')
    prev_savings = prev_income - prev_expenses
    prev_savings_rate = (prev_savings / prev_income * 100) if prev_income > 0 else 0
    
    if total_income > 0:
        if savings_rate > 20:
            insights.append({
                'type': 'success',
                'icon': 'fa-piggy-bank',
                'title': f'Excellent Work, {username}!',
                'description': f'You\'re saving {savings_rate:.1f}% of your income (₹{savings:,.0f} this month). At this rate, you could save ₹{savings*12:,.0f} annually! Keep it up!',
                'impact': 'Positive',
                'confidence': 98
            })
        elif savings_rate >= 10:
            target_savings = total_income * 0.20
            gap = target_savings - savings
            insights.append({
                'type': 'info',
                'icon': 'fa-chart-line',
                'title': f'{username}, You\'re on Track!',
                'description': f'Current savings rate: {savings_rate:.1f}% (₹{savings:,.0f}). To reach the 20% goal, you need to save ₹{gap:,.0f} more per month. Focus on reducing discretionary spending!',
                'impact': 'Medium',
                'confidence': 94
            })
        else:
            monthly_reduction_needed = (total_income * 0.20) - savings
            insights.append({
                'type': 'danger',
                'icon': 'fa-exclamation-triangle',
                'title': f'{username}, Let\'s Improve Your Savings',
                'description': f'You\'re saving only {savings_rate:.1f}% (₹{savings:,.0f}). To reach 20%, you need to cut expenses by ₹{monthly_reduction_needed:,.0f}/month. Start with non-essential categories!',
                'impact': 'High',
                'confidence': 95
            })
        
        # Savings trend
        if prev_savings_rate > 0:
            if savings_rate > prev_savings_rate + 5:
                insights.append({
                    'type': 'success',
                    'icon': 'fa-arrow-trend-up',
                    'title': f'{username}, Your Savings are Growing!',
                    'description': f'Your savings rate improved from {prev_savings_rate:.1f}% to {savings_rate:.1f}%! You\'re moving in the right direction!',
                    'impact': 'Positive',
                    'confidence': 93
                })
    
    # Insight 4: PERSONALIZED Recurring merchant with specific savings potential
    merchant_data = defaultdict(lambda: {'count': 0, 'total': 0, 'dates': []})
    for t in recent_transactions:
        if t.merchant and t.transaction_type == 'debit':
            merchant_data[t.merchant]['count'] += 1
            merchant_data[t.merchant]['total'] += t.amount
            merchant_data[t.merchant]['dates'].append(t.date)
    
    frequent_merchants = {m: d for m, d in merchant_data.items() if d['count'] >= 4}
    if frequent_merchants:
        top_merchant = max(frequent_merchants, key=lambda m: frequent_merchants[m]['total'])
        visit_count = frequent_merchants[top_merchant]['count']
        total_spent = frequent_merchants[top_merchant]['total']
        avg_spend = total_spent / visit_count
        
        # Calculate potential savings
        potential_savings = total_spent * 0.10  # Assuming 10% savings from loyalty/bulk
        
        insights.append({
            'type': 'info',
            'icon': 'fa-store',
            'title': f'{username}, Frequent Shopper Alert!',
            'description': f'You visited {top_merchant} {visit_count} times, spending ₹{total_spent:,.0f} (₹{avg_spend:.0f}/visit). With loyalty programs or bulk buying, you could save up to ₹{potential_savings:.0f}!',
            'impact': 'Low',
            'confidence': 88
        })
    
    # Insight 5: PERSONALIZED High-value transaction detection
    high_value_transactions = [t for t in recent_transactions 
                               if t.transaction_type == 'debit' and t.amount > 5000]
    if high_value_transactions:
        total_high_value = sum(t.amount for t in high_value_transactions)
        percentage_of_spending = (total_high_value / total_expenses * 100) if total_expenses > 0 else 0
        
        if percentage_of_spending > 40:
            insights.append({
                'type': 'warning',
                'icon': 'fa-money-bill-wave',
                'title': f'{username}, Large Purchases Detected',
                'description': f'You made {len(high_value_transactions)} large transactions (₹5000+) totaling ₹{total_high_value:,.0f} ({percentage_of_spending:.0f}% of expenses). Review these carefully to ensure they\'re necessary!',
                'impact': 'High',
                'confidence': 91
            })
    
    # Insight 6: PERSONALIZED Daily spending pattern
    daily_spending = defaultdict(float)
    for t in recent_transactions:
        if t.transaction_type == 'debit':
            daily_spending[t.date.date()] += t.amount
    
    if daily_spending:
        avg_daily = sum(daily_spending.values()) / len(daily_spending)
        high_spend_days = [day for day, amount in daily_spending.items() if amount > avg_daily * 2]
        
        if len(high_spend_days) >= 3:
            insights.append({
                'type': 'warning',
                'icon': 'fa-calendar-day',
                'title': f'{username}, Spending Spike Days',
                'description': f'You had {len(high_spend_days)} days with unusually high spending (2x your daily average of ₹{avg_daily:.0f}). Try to spread out large purchases to avoid budget shocks!',
                'impact': 'Medium',
                'confidence': 86
            })
    
        # Insight 7: PERSONALIZED Category comparison with benchmarks
        if 'dining' in category_totals or 'entertainment' in category_totals:
            discretionary_total = category_totals.get('dining', 0) + category_totals.get('entertainment', 0)
            discretionary_pct = (discretionary_total / total_expenses * 100) if total_expenses > 0 else 0
            
            if discretionary_pct > 25:
                insights.append({
                    'type': 'info',
                    'icon': 'fa-utensils',
                    'title': f'{username}, High Discretionary Spending',
                    'description': f'Dining and entertainment account for {discretionary_pct:.0f}% of your spending (₹{discretionary_total:,.0f}). Consider cooking more meals at home or finding free entertainment options to save ₹{discretionary_total*0.3:.0f}/month!',
                    'impact': 'Medium',
                    'confidence': 89
                })
        
    print(f"✅ DEBUG INSIGHTS - Generated {len(insights)} insights for {username}")
    print(f"📊 DEBUG INSIGHTS - Insight types: {[i['type'] for i in insights]}")
    
    return jsonify({'insights': insights})

@app.route('/api/analytics/top-merchants')
@login_required
def api_top_merchants():
    """Get top merchants by spending - FIXED with better filtering"""
    from datetime import datetime, timedelta
    
    months = request.args.get('months', 1, type=int)
    start_date = datetime.now() - timedelta(days=months*30)
    
    # Debug: Check total transactions
    total_trans = Transaction.query.filter_by(user_id=current_user.id).count()
    print(f"🔍 DEBUG - Total transactions for user: {total_trans}")
    
    # Get all debit transactions with merchants
    all_debits = Transaction.query.filter_by(
        user_id=current_user.id,
        transaction_type='debit'
    ).filter(Transaction.date >= start_date).all()
    
    print(f"🔍 DEBUG - Debit transactions in date range: {len(all_debits)}")
    print(f"🔍 DEBUG - Sample merchants: {[t.merchant for t in all_debits[:5]]}")
    
    # Query with better filtering (check for None and empty string)
    merchants = db.session.query(
        Transaction.merchant,
        db.func.count(Transaction.id).label('count'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(Transaction.user_id == current_user.id)\
     .filter(Transaction.date >= start_date)\
     .filter(Transaction.transaction_type == 'debit')\
     .filter(Transaction.merchant != None)\
     .filter(Transaction.merchant != '')\
     .group_by(Transaction.merchant)\
     .order_by(db.text('total DESC'))\
     .limit(10)\
     .all()
    
    print(f"🔍 DEBUG - Merchants found: {len(merchants)}")
    
    total_spending = sum(m.total for m in merchants) if merchants else 0
    
    # If no merchants found, return empty list with debug info
    if not merchants:
        return jsonify({
            'merchants': [],
            'debug': {
                'total_transactions': total_trans,
                'debit_transactions': len(all_debits),
                'message': 'No merchants found. Check if transactions have merchant field populated.'
            }
        })
    
    return jsonify({
        'merchants': [{
            'name': m.merchant,
            'count': m.count,
            'total': float(m.total),
            'percentage': (m.total / total_spending * 100) if total_spending > 0 else 0
        } for m in merchants]
    })

# Initialize Dash app for advanced analytics
def create_dash_app(flask_app):
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname='/dash/')
    
    dash_app.layout = html.Div([
        html.H1("Advanced Analytics Dashboard", style={'textAlign': 'center', 'marginBottom': 30}),
        
        # Summary statistics
        html.Div(id='summary-stats', style={'marginBottom': 30}),
        
        # Charts in a responsive grid
        html.Div([
            html.Div([
                dcc.Graph(id='spending-trend')
            ], style={'width': '50%', 'display': 'inline-block'}),
            
            html.Div([
                dcc.Graph(id='category-breakdown')
            ], style={'width': '50%', 'display': 'inline-block'})
        ]),
        
        # Additional analytics
        html.Div([
            dcc.Graph(id='source-breakdown')
        ], style={'marginTop': 30}),
        
        dcc.Interval(id='interval-component', interval=30*1000, n_intervals=0)
    ])
    
    @dash_app.callback(
        Output('spending-trend', 'figure'),
        Input('interval-component', 'n_intervals')
    )
    def update_spending_trend(n):
        with flask_app.app_context():
            try:
                # Get all users' transactions (since Dash doesn't have access to current_user)
                # In production, you'd want to add proper user authentication for Dash
                monthly_data = db.session.query(
                    db.func.strftime('%Y-%m', Transaction.date).label('month'),
                    db.func.sum(Transaction.amount).label('total')
                ).group_by(db.func.strftime('%Y-%m', Transaction.date))\
                 .order_by('month').all()
                
                if monthly_data:
                    months = [item.month for item in monthly_data]
                    amounts = [float(item.total) for item in monthly_data]
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=months, 
                        y=amounts,
                        mode='lines+markers',
                        name='Monthly Spending',
                        line=dict(color='#1f77b4', width=3),
                        marker=dict(size=8)
                    ))
                    fig.update_layout(
                        title="Monthly Spending Trend (Gmail + Manual Transactions)",
                        xaxis_title="Month",
                        yaxis_title="Amount ($)",
                        template="plotly_white"
                    )
                else:
                    # No data available
                    fig = go.Figure()
                    fig.add_annotation(
                        text="No transaction data available",
                        xref="paper", yref="paper",
                        x=0.5, y=0.5, showarrow=False,
                        font=dict(size=16)
                    )
                    fig.update_layout(title="Monthly Spending Trend")
                
                return fig
            except Exception as e:
                # Error handling
                fig = go.Figure()
                fig.add_annotation(
                    text=f"Error loading data: {str(e)}",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=14, color="red")
                )
                fig.update_layout(title="Monthly Spending Trend - Error")
                return fig
    
    @dash_app.callback(
        Output('category-breakdown', 'figure'),
        Input('interval-component', 'n_intervals')
    )
    def update_category_breakdown(n):
        with flask_app.app_context():
            try:
                # Get category breakdown for all users' transactions
                category_data = db.session.query(
                    Category.name,
                    db.func.sum(Transaction.amount).label('total')
                ).join(Transaction)\
                 .group_by(Category.name).all()
                
                if category_data:
                    categories = [item.name for item in category_data]
                    amounts = [float(item.total) for item in category_data]
                    
                    # Create pie chart with custom colors
                    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', 
                             '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA']
                    
                    fig = go.Figure(data=[go.Pie(
                        labels=categories, 
                        values=amounts,
                        marker=dict(colors=colors[:len(categories)]),
                        textinfo='label+percent',
                        textposition='outside'
                    )])
                    fig.update_layout(
                        title="Spending by Category (Gmail + Manual Transactions)",
                        template="plotly_white",
                        showlegend=True,
                        legend=dict(
                            orientation="v",
                            yanchor="middle",
                            y=0.5,
                            xanchor="left",
                            x=1.05
                        )
                    )
                else:
                    # No data available
                    fig = go.Figure()
                    fig.add_annotation(
                        text="No transaction data available",
                        xref="paper", yref="paper",
                        x=0.5, y=0.5, showarrow=False,
                        font=dict(size=16)
                    )
                    fig.update_layout(title="Spending by Category")
                
                return fig
            except Exception as e:
                # Error handling
                fig = go.Figure()
                fig.add_annotation(
                    text=f"Error loading data: {str(e)}",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=14, color="red")
                )
                fig.update_layout(title="Spending by Category - Error")
                return fig
    
    @dash_app.callback(
        Output('summary-stats', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_summary_stats(n):
        with flask_app.app_context():
            try:
                # Get transaction statistics
                total_transactions = Transaction.query.count()
                gmail_transactions = Transaction.query.filter(Transaction.gmail_message_id.isnot(None)).count()
                manual_transactions = total_transactions - gmail_transactions
                total_amount = db.session.query(db.func.sum(Transaction.amount)).scalar() or 0
                
                return html.Div([
                    html.Div([
                        html.H3(f"${total_amount:.2f}", style={'margin': 0, 'color': '#2E86AB'}),
                        html.P("Total Spending", style={'margin': 0, 'fontSize': 14})
                    ], style={'textAlign': 'center', 'padding': 20, 'backgroundColor': '#F8F9FA', 
                             'borderRadius': 10, 'width': '22%', 'display': 'inline-block', 'margin': '1%'}),
                    
                    html.Div([
                        html.H3(f"{total_transactions}", style={'margin': 0, 'color': '#A23B72'}),
                        html.P("Total Transactions", style={'margin': 0, 'fontSize': 14})
                    ], style={'textAlign': 'center', 'padding': 20, 'backgroundColor': '#F8F9FA', 
                             'borderRadius': 10, 'width': '22%', 'display': 'inline-block', 'margin': '1%'}),
                    
                    html.Div([
                        html.H3(f"{gmail_transactions}", style={'margin': 0, 'color': '#F18F01'}),
                        html.P("Gmail Synced", style={'margin': 0, 'fontSize': 14})
                    ], style={'textAlign': 'center', 'padding': 20, 'backgroundColor': '#F8F9FA', 
                             'borderRadius': 10, 'width': '22%', 'display': 'inline-block', 'margin': '1%'}),
                    
                    html.Div([
                        html.H3(f"{manual_transactions}", style={'margin': 0, 'color': '#C73E1D'}),
                        html.P("Manual/Upload", style={'margin': 0, 'fontSize': 14})
                    ], style={'textAlign': 'center', 'padding': 20, 'backgroundColor': '#F8F9FA', 
                             'borderRadius': 10, 'width': '22%', 'display': 'inline-block', 'margin': '1%'})
                ], style={'textAlign': 'center'})
                
            except Exception as e:
                return html.Div(f"Error loading stats: {str(e)}", style={'color': 'red'})
    
    @dash_app.callback(
        Output('source-breakdown', 'figure'),
        Input('interval-component', 'n_intervals')
    )
    def update_source_breakdown(n):
        with flask_app.app_context():
            try:
                # Get breakdown by data source
                gmail_count = Transaction.query.filter(Transaction.gmail_message_id.isnot(None)).count()
                gmail_amount = db.session.query(db.func.sum(Transaction.amount))\
                    .filter(Transaction.gmail_message_id.isnot(None)).scalar() or 0
                
                manual_count = Transaction.query.filter(Transaction.gmail_message_id.is_(None)).count()
                manual_amount = db.session.query(db.func.sum(Transaction.amount))\
                    .filter(Transaction.gmail_message_id.is_(None)).scalar() or 0
                
                if gmail_count > 0 or manual_count > 0:
                    fig = go.Figure(data=[
                        go.Bar(name='Gmail Synced', x=['Count', 'Amount ($)'], 
                               y=[gmail_count, float(gmail_amount)],
                               marker_color='#F18F01'),
                        go.Bar(name='Manual/Upload', x=['Count', 'Amount ($)'], 
                               y=[manual_count, float(manual_amount)],
                               marker_color='#C73E1D')
                    ])
                    
                    fig.update_layout(
                        title="Transaction Sources Comparison",
                        xaxis_title="Metric",
                        yaxis_title="Value",
                        barmode='group',
                        template="plotly_white"
                    )
                else:
                    fig = go.Figure()
                    fig.add_annotation(
                        text="No transaction data available",
                        xref="paper", yref="paper",
                        x=0.5, y=0.5, showarrow=False,
                        font=dict(size=16)
                    )
                    fig.update_layout(title="Transaction Sources")
                
                return fig
                
            except Exception as e:
                fig = go.Figure()
                fig.add_annotation(
                    text=f"Error loading source data: {str(e)}",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=14, color="red")
                )
                fig.update_layout(title="Transaction Sources - Error")
                return fig

    return dash_app

# Create Dash app
dash_app = create_dash_app(app)

if __name__ == '__main__':
    # Ensure database directory exists
    os.makedirs('database', exist_ok=True)
    
    with app.app_context():
        db.create_all()
        
        # Create default categories
        default_categories = [
            'Groceries', 'Utilities', 'Entertainment', 'Transportation',
            'Healthcare', 'Shopping', 'Dining', 'Bills', 'Other'
        ]
        
        for cat_name in default_categories:
            if not Category.query.filter_by(name=cat_name).first():
                category = Category(name=cat_name, description=f"Default {cat_name} category")
                db.session.add(category)
        
        db.session.commit()
        
        print("🏦 Smart Personal Finance Automator")
        print("=" * 50)
        print("✅ Database initialized successfully!")
        print(f"📊 Database location: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print("🚀 Starting server at http://localhost:5001")
        print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
