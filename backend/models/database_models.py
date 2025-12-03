from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication and user management"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    savings_goals = db.relationship('SavingsGoal', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_total_spending(self, start_date=None, end_date=None):
        """Get total spending for user in a date range"""
        query = Transaction.query.filter_by(user_id=self.id, transaction_type='debit')
        
        if start_date:
            query = query.filter(Transaction.date >= start_date)
        if end_date:
            query = query.filter(Transaction.date <= end_date)
            
        return query.with_entities(db.func.sum(Transaction.amount)).scalar() or 0
    
    def __repr__(self):
        return f'<User {self.username}>'

class Category(db.Model):
    """Category model for transaction classification"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default='#007bff')  # Hex color code
    icon = db.Column(db.String(50), default='fas fa-shopping-cart')  # FontAwesome icon class
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='category', lazy=True)
    
    # Keywords for automatic categorization
    keywords = db.relationship('CategoryKeyword', backref='category', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Category {self.name}>'

class CategoryKeyword(db.Model):
    """Keywords associated with categories for automatic classification"""
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    weight = db.Column(db.Float, default=1.0)  # Importance weight for this keyword
    
    def __repr__(self):
        return f'<CategoryKeyword {self.keyword}>'

class Transaction(db.Model):
    """Transaction model for storing financial transactions"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=False)
    merchant = db.Column(db.String(200))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    transaction_type = db.Column(db.String(20), nullable=False, default='debit')  # debit, credit
    
    # Source information
    source = db.Column(db.String(50), default='manual')  # manual, sms, email, api
    raw_text = db.Column(db.Text)  # Original SMS/email text
    confidence_score = db.Column(db.Float, default=1.0)  # NLP extraction confidence
    gmail_message_id = db.Column(db.String(100))  # Gmail message ID for duplicate prevention
    
    # Additional metadata
    account_last_four = db.Column(db.String(4))  # Last 4 digits of account
    reference_number = db.Column(db.String(100))
    balance_after = db.Column(db.Numeric(10, 2))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.amount} - {self.description[:30]}...>'
    
    def to_dict(self):
        """Convert transaction to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'amount': float(self.amount),
            'description': self.description,
            'merchant': self.merchant,
            'date': self.date.isoformat(),
            'transaction_type': self.transaction_type,
            'category': self.category.name if self.category else 'Uncategorized',
            'category_id': self.category_id,
            'source': self.source,
            'confidence_score': self.confidence_score
        }

class SavingsGoal(db.Model):
    """Savings goal model for user financial planning"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_amount = db.Column(db.Numeric(10, 2), nullable=False)
    current_amount = db.Column(db.Numeric(10, 2), default=0.00)
    target_date = db.Column(db.DateTime)
    
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))  # Category to save on
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def progress_percentage(self):
        """Calculate completion percentage"""
        if self.target_amount == 0:
            return 0
        return min((float(self.current_amount) / float(self.target_amount)) * 100, 100)
    
    @property
    def remaining_amount(self):
        """Calculate remaining amount to reach goal"""
        return max(float(self.target_amount) - float(self.current_amount), 0)
    
    def __repr__(self):
        return f'<SavingsGoal {self.title}>'

class Budget(db.Model):
    """Budget model for monthly/category spending limits"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    period = db.Column(db.String(20), default='monthly')  # monthly, weekly, yearly
    
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_spent_amount(self):
        """Get amount spent against this budget"""
        query = Transaction.query.filter(
            Transaction.user_id == self.user_id,
            Transaction.date >= self.start_date,
            Transaction.transaction_type == 'debit'
        )
        
        if self.end_date:
            query = query.filter(Transaction.date <= self.end_date)
        
        if self.category_id:
            query = query.filter(Transaction.category_id == self.category_id)
        
        return query.with_entities(db.func.sum(Transaction.amount)).scalar() or 0
    
    @property
    def remaining_amount(self):
        """Calculate remaining budget amount"""
        return max(float(self.amount) - float(self.get_spent_amount()), 0)
    
    @property
    def usage_percentage(self):
        """Calculate budget usage percentage"""
        if self.amount == 0:
            return 0
        return min((float(self.get_spent_amount()) / float(self.amount)) * 100, 100)
    
    def __repr__(self):
        return f'<Budget {self.name}>'

class Notification(db.Model):
    """Notification model for user alerts and recommendations"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='info')  # info, warning, success, error
    
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Optional: Link to related objects
    related_transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))
    related_budget_id = db.Column(db.Integer, db.ForeignKey('budget.id'))
    related_savings_goal_id = db.Column(db.Integer, db.ForeignKey('savings_goal.id'))
    
    def __repr__(self):
        return f'<Notification {self.title}>'

# Database initialization function
def init_database():
    """Initialize database with default data"""
    # Create all tables
    db.create_all()
    
    # Create default categories
    default_categories = [
        {'name': 'Groceries', 'description': 'Food and grocery shopping', 'color': '#28a745', 'icon': 'fas fa-shopping-cart'},
        {'name': 'Utilities', 'description': 'Electricity, water, gas, internet bills', 'color': '#ffc107', 'icon': 'fas fa-bolt'},
        {'name': 'Transportation', 'description': 'Fuel, public transport, taxi, parking', 'color': '#17a2b8', 'icon': 'fas fa-car'},
        {'name': 'Entertainment', 'description': 'Movies, games, subscriptions, hobbies', 'color': '#e83e8c', 'icon': 'fas fa-gamepad'},
        {'name': 'Healthcare', 'description': 'Medical expenses, medicines, insurance', 'color': '#fd7e14', 'icon': 'fas fa-heartbeat'},
        {'name': 'Dining', 'description': 'Restaurants, cafes, food delivery', 'color': '#dc3545', 'icon': 'fas fa-utensils'},
        {'name': 'Shopping', 'description': 'Clothing, electronics, general shopping', 'color': '#6f42c1', 'icon': 'fas fa-shopping-bag'},
        {'name': 'Bills', 'description': 'Phone, credit card, loan payments', 'color': '#6c757d', 'icon': 'fas fa-file-invoice-dollar'},
        {'name': 'Education', 'description': 'Courses, books, training', 'color': '#20c997', 'icon': 'fas fa-graduation-cap'},
        {'name': 'Other', 'description': 'Miscellaneous expenses', 'color': '#6c757d', 'icon': 'fas fa-ellipsis-h'}
    ]
    
    for cat_data in default_categories:
        if not Category.query.filter_by(name=cat_data['name']).first():
            category = Category(**cat_data)
            db.session.add(category)
    
    # Add default keywords for categories
    category_keywords = {
        'Groceries': ['grocery', 'supermarket', 'walmart', 'target', 'costco', 'food', 'market'],
        'Utilities': ['electric', 'water', 'gas', 'internet', 'phone', 'utility', 'bill'],
        'Transportation': ['fuel', 'gas station', 'uber', 'lyft', 'taxi', 'parking', 'metro', 'bus'],
        'Entertainment': ['netflix', 'spotify', 'movie', 'cinema', 'game', 'entertainment', 'subscription'],
        'Healthcare': ['pharmacy', 'hospital', 'doctor', 'medical', 'health', 'medicine', 'cvs', 'walgreens'],
        'Dining': ['restaurant', 'cafe', 'starbucks', 'mcdonald', 'pizza', 'delivery', 'doordash', 'grubhub'],
        'Shopping': ['amazon', 'mall', 'store', 'clothing', 'electronics', 'shopping'],
        'Bills': ['credit card', 'loan', 'mortgage', 'insurance', 'payment', 'bill']
    }
    
    db.session.commit()
    
    # Add keywords to categories
    for cat_name, keywords in category_keywords.items():
        category = Category.query.filter_by(name=cat_name).first()
        if category:
            for keyword in keywords:
                if not CategoryKeyword.query.filter_by(category_id=category.id, keyword=keyword).first():
                    cat_keyword = CategoryKeyword(category_id=category.id, keyword=keyword)
                    db.session.add(cat_keyword)
    
    db.session.commit()
    print("Database initialized with default categories and keywords!")
