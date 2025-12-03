# import spacy
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple
import json

class TransactionProcessor:
    """
    Natural Language Processing service for extracting transaction data
    from SMS messages and email notifications from banks.
    """
    
    def __init__(self):
        """Initialize the NLP processor with basic patterns (spaCy temporarily disabled)"""
        try:
            # Load English language model
            # self.nlp = spacy.load("en_core_web_sm")
            self.nlp = None  # Temporarily disabled
        except:
            print("spaCy English model not found. Using basic text processing.")
            self.nlp = None
        
        # Common bank SMS/email patterns - Enhanced for Indian banks with better validation
        self.amount_patterns = [
            # Very specific transaction patterns (high confidence)
            r'(?:debited|credited|paid|spent|received)\s+(?:rs\.?\s*|inr\s*|₹\s*)([0-9,]+(?:\.[0-9]{2})?)', # debited Rs 1234
            r'(?:rs\.?\s*|inr\s*|₹\s*)([0-9,]+(?:\.[0-9]{2})?)\s+(?:has been|was|is)\s*(?:debited|credited|charged)', # Rs 1234 has been debited
            r'amount\s+(?:of\s+)?(?:rs\.?\s*|inr\s*|₹\s*)?([0-9,]+(?:\.[0-9]{2})?)\s+(?:debited|credited|paid)', # amount Rs 1234 debited
            r'(?:balance|available)\s+(?:is\s+)?(?:rs\.?\s*|₹\s*)?([0-9,]+(?:\.[0-9]{2})?)', # balance Rs 1234
            
            # UPI and digital payment specific patterns
            r'(?:upi|payment|txn)\s+(?:of\s+)?(?:rs\.?\s*|₹\s*)?([0-9,]+(?:\.[0-9]{2})?)', # UPI Rs 1234
            r'([0-9,]+(?:\.[0-9]{2})?)\s+(?:paid via|sent via|received via)\s+(?:upi|phonepe|gpay)', # 1234 paid via UPI
            
            # More cautious patterns (lower priority)
            r'(?:rs\.?\s*|inr\s*|₹\s*)([0-9,]+(?:\.[0-9]{2})?)\b(?!\d)', # Rs. 1,234.56 (with word boundary)
            r'\b([0-9]{1,6}(?:\.[0-9]{2})?)\s*(?:rs\.?|inr|₹)\b', # 1234 Rs (reasonable amounts only)
        ]
        
        self.date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})',
            r'on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        
        self.transaction_type_patterns = {
            'debit': [
                r'debited|deducted|charged|withdrawn|spent|paid|purchase|bought',
                r'payment\s+made|transaction\s+at|used\s+at'
            ],
            'credit': [
                r'credited|deposited|received|refund|cashback|salary|transfer\s+from',
                r'amount\s+received|credited\s+to'
            ]
        }
        
        self.merchant_patterns = [
            r'at\s+([A-Z][A-Z0-9\s&.-]+?)(?:\s+on|\s+for|\s+ref|\.|$)',
            r'(?:purchase|payment|transaction)\s+at\s+([A-Z][A-Z0-9\s&.-]+?)(?:\s+on|\s+for|\.|$)',
            r'used\s+at\s+([A-Z][A-Z0-9\s&.-]+?)(?:\s+on|\s+for|\.|$)',
            r'from\s+([A-Z][A-Z0-9\s&.-]+?)(?:\s+to|\s+on|\.|$)'
        ]
        
        # Common merchant name mappings
        self.merchant_aliases = {
            'AMAZON': 'Amazon',
            'WALMART': 'Walmart',
            'STARBUCKS': 'Starbucks',
            'MCDONALD': 'McDonald\'s',
            'NETFLIX': 'Netflix',
            'SPOTIFY': 'Spotify',
            'UBER': 'Uber',
            'LYFT': 'Lyft'
        }
        
        # Category keywords for automatic classification
        self.category_keywords = {
            'groceries': ['grocery', 'supermarket', 'walmart', 'target', 'costco', 'food mart', 'fresh', 
                         'big bazaar', 'dmart', 'reliance fresh', 'more', 'spencer', 'easyday', 'nilgiris',
                         'metro cash', 'food bazaar', 'kirana', 'provisions', 'vegetables', 'fruits'],
            'utilities': ['electric', 'electricity', 'water', 'gas', 'internet', 'phone', 'utility', 'telecom',
                         'airtel', 'jio', 'vodafone', 'bsnl', 'idea', 'tata sky', 'dish tv', 'adani', 'bescom',
                         'kseb', 'mseb', 'bill payment', 'recharge', 'postpaid', 'prepaid'],
            'transportation': ['fuel', 'petrol', 'diesel', 'gas station', 'uber', 'ola', 'taxi', 'auto',
                             'metro', 'parking', 'toll', 'cab', 'bhp petro', 'ioc', 'hp petrol', 'shell',
                             'bus', 'train', 'flight', 'ticket', 'booking', 'irctc', 'makemytrip', 'goibibo'],
            'entertainment': ['netflix', 'spotify', 'amazon prime', 'hotstar', 'zee5', 'sony liv', 'voot',
                            'movie', 'cinema', 'pvr', 'inox', 'bookmyshow', 'gaming', 'game', 'entertainment'],
            'healthcare': ['pharmacy', 'hospital', 'medical', 'doctor', 'apollo', '1mg', 'netmeds', 'pharmeasy',
                          'medplus', 'clinic', 'health', 'medicine', 'prescription'],
            'dining': ['restaurant', 'cafe', 'food', 'starbucks', 'mcdonald', 'kfc', 'pizza hut', 'dominos',
                      'pizza', 'delivery', 'zomato', 'swiggy', 'uber eats', 'foodpanda', 'dining', 'hotel',
                      'dhaba', 'tiffin', 'meal', 'lunch', 'dinner', 'breakfast'],
            'shopping': ['amazon', 'flipkart', 'myntra', 'ajio', 'nykaa', 'mall', 'store', 'clothing', 'electronics',
                        'fashion', 'shopping', 'retail', 'brand factory', 'lifestyle', 'max', 'westside',
                        'shoppers stop', 'online shopping', 'e-commerce'],
            'bills': ['credit card', 'loan', 'insurance', 'emi', 'payment', 'hdfc', 'icici', 'sbi', 'axis',
                     'kotak', 'citi', 'standard chartered', 'lic', 'bajaj', 'tata aig'],
            'education': ['school', 'college', 'university', 'fees', 'tuition', 'course', 'training', 'book',
                         'education', 'study', 'exam'],
            'other': ['atm', 'cash withdrawal', 'transfer', 'misc', 'miscellaneous']
        }
    
    def process_text(self, text: str) -> List[Dict]:
        """
        Main method to process text and extract transactions
        (Simplified version without spaCy)
        """
        return self.extract_transactions(text)
    
    def extract_transactions(self, text_data: str) -> List[Dict]:
        """
        Extract transaction information from text data (SMS/email content)
        
        Args:
            text_data: Raw text containing transaction information
            
        Returns:
            List of transaction dictionaries
        """
        transactions = []
        
        # Split text into individual messages/entries
        messages = self._split_messages(text_data)
        
        for message in messages:
            transaction = self._extract_single_transaction(message)
            if transaction:
                transactions.append(transaction)
        
        return transactions
    
    def _split_messages(self, text_data: str) -> List[str]:
        """Split text data into individual transaction messages"""
        # Common SMS/email separators
        separators = [
            r'\n\s*\n',  # Double newline
            r'\n-{3,}',  # Line with dashes
            r'\n={3,}',  # Line with equals
            r'Subject:',  # Email subject line
            r'From:',     # Email from line
        ]
        
        messages = [text_data]
        
        for separator in separators:
            new_messages = []
            for msg in messages:
                new_messages.extend(re.split(separator, msg, flags=re.IGNORECASE))
            messages = [m.strip() for m in new_messages if m.strip()]
        
        return messages
    
    def _extract_single_transaction(self, message: str) -> Optional[Dict]:
        """Extract transaction data from a single message"""
        if not message or len(message.strip()) < 10:
            return None
        

        message = message.strip()
        message_lower = message.lower()
        
        
        transaction_indicators = [
            'debited', 'credited', 'transaction', 'payment', 'purchase', 'spent', 'paid',
            'withdrawal', 'deposit', 'transfer', 'balance', 'amount', 'rs.', '₹', 'inr',
            'card used', 'bill payment', 'refund', 'cashback'
        ]
        if not any(indicator in message_lower for indicator in transaction_indicators):
            return None
        
        transaction = {
            'description': message,
            'raw_text': message,
            'confidence_score': 0.0
        }
        
        
        amount, amount_confidence = self._extract_amount(message)
        if amount is None or amount <= 0:
            return None 
        
        transaction['amount'] = amount
        transaction['confidence_score'] += amount_confidence * 0.5  
        
        
        date, date_confidence = self._extract_date(message)
        transaction['date'] = date or datetime.now()
        transaction['confidence_score'] += date_confidence * 0.2
        
        # Extract transaction type
        trans_type, type_confidence = self._extract_transaction_type(message)
        transaction['type'] = trans_type
        transaction['confidence_score'] += type_confidence * 0.15
        
        # Extract merchant
        merchant, merchant_confidence = self._extract_merchant(message)
        transaction['merchant'] = merchant or 'Unknown'
        transaction['confidence_score'] += merchant_confidence * 0.1
        
        # Categorize transaction
        category, category_confidence = self._categorize_transaction(message, merchant)
        transaction['category'] = category or 'Other'
        transaction['confidence_score'] += category_confidence * 0.05
        
        # Extract additional information
        transaction.update(self._extract_additional_info(message))
        
        # Only return transactions with reasonable confidence
        if transaction['confidence_score'] >= 0.3:
            return transaction
        
        return None
    
    def _extract_amount(self, text: str) -> Tuple[Optional[float], float]:
        """Extract monetary amount from text with validation to avoid phone numbers"""
        confidence = 0.0
        
        for pattern in self.amount_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    # Clean amount string and convert to float
                    amount_str = matches[0].replace(',', '').replace(' ', '')
                    amount = float(amount_str)
                    
                    # Validation: Skip amounts that look like phone numbers
                    if self._is_phone_number(amount_str):
                        print(f"   ⚠️ Skipping phone number detected as amount: {amount_str}")
                        continue
                    
                    # Validation: Reasonable amount range (₹0.01 to ₹10,00,000)
                    if amount < 0.01 or amount > 1000000:
                        print(f"   ⚠️ Skipping unrealistic amount: ₹{amount}")
                        continue
                    
                    # Higher confidence for amounts with currency symbols
                    if any(symbol in text for symbol in ['₹', '$', 'Rs', 'INR', 'USD']):
                        confidence = 0.9
                    else:
                        confidence = 0.7
                    
                    print(f"   ✅ Valid amount extracted: ₹{amount} (confidence: {confidence})")
                    return amount, confidence
                except (ValueError, IndexError):
                    continue
        
        return None, confidence
    
    def _is_phone_number(self, amount_str: str) -> bool:
        """Check if the extracted number is likely a phone number"""
        # Remove commas and spaces for analysis
        clean_number = amount_str.replace(',', '').replace(' ', '')
        
        # Indian phone number patterns
        if len(clean_number) == 10 and clean_number.startswith(('6', '7', '8', '9')):
            return True  # Indian mobile number
        if len(clean_number) == 11 and clean_number.startswith('0'):
            return True  # Indian landline with area code
        if len(clean_number) >= 10 and len(clean_number) <= 12:
            # Check if it has repeated digits (common in customer service numbers)
            digit_counts = {}
            for digit in clean_number:
                digit_counts[digit] = digit_counts.get(digit, 0) + 1
            # If any digit appears more than 4 times, likely a service number
            if any(count > 4 for count in digit_counts.values()):
                return True
        
        return False
    
    def _extract_date(self, text: str) -> Tuple[Optional[datetime], float]:
        """Extract date from text"""
        confidence = 0.0
        
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    date_str = matches[0]
                    # Try multiple date formats
                    date_formats = [
                        '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%m-%d-%Y',
                        '%d/%m/%y', '%d-%m-%y', '%m/%d/%y', '%m-%d-%y',
                        '%Y-%m-%d', '%d %b %Y', '%d %B %Y'
                    ]
                    
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            confidence = 0.8
                            return parsed_date, confidence
                        except ValueError:
                            continue
                            
                except (ValueError, IndexError):
                    continue
        
        # If no date found, check for relative dates
        if 'today' in text.lower():
            return datetime.now(), 0.6
        elif 'yesterday' in text.lower():
            return datetime.now() - timedelta(days=1), 0.6
        
        return None, confidence
    
    def _extract_transaction_type(self, text: str) -> Tuple[str, float]:
        """Determine if transaction is debit or credit"""
        text_lower = text.lower()
        
        for trans_type, patterns in self.transaction_type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    confidence = 0.8 if trans_type == 'debit' else 0.7  # Bias towards debit
                    return trans_type, confidence
        
        # Default to debit with low confidence
        return 'debit', 0.3
    
    def _extract_merchant(self, text: str) -> Tuple[Optional[str], float]:
        """Extract merchant/vendor name from text"""
        confidence = 0.0
        
        for pattern in self.merchant_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                merchant = matches[0].strip()
                
                # Clean merchant name
                merchant = re.sub(r'\s+', ' ', merchant)  # Remove extra spaces
                merchant = merchant.strip('.,;:')  # Remove trailing punctuation
                
                # Check for known aliases
                merchant_upper = merchant.upper()
                for alias, clean_name in self.merchant_aliases.items():
                    if alias in merchant_upper:
                        merchant = clean_name
                        confidence = 0.9
                        break
                else:
                    confidence = 0.7
                
                if len(merchant) > 2:  # Only return if meaningful length
                    return merchant, confidence
        
        return None, confidence
    
    def _categorize_transaction(self, text: str, merchant: Optional[str]) -> Tuple[Optional[str], float]:
        """Automatically categorize transaction based on text and merchant"""
        text_lower = text.lower()
        merchant_lower = (merchant or '').lower()
        combined_text = f"{text_lower} {merchant_lower}"
        
        confidence = 0.0
        best_category = None
        max_matches = 0
        best_score = 0
        
        # Check for each category
        for category, keywords in self.category_keywords.items():
            matches = 0
            score = 0
            
            for keyword in keywords:
                if keyword in combined_text:
                    matches += 1
                    # Give higher weight to longer, more specific keywords
                    score += len(keyword.split())
            
            # Calculate total score for this category
            total_score = matches + (score * 0.5)
            
            if total_score > best_score:
                best_score = total_score
                best_category = category
                confidence = min(0.9, total_score * 0.15)
        
        # Special rules for common patterns
        if not best_category or confidence < 0.3:
            # ATM withdrawals -> Other
            if any(term in combined_text for term in ['atm', 'cash withdrawal', 'pos withdrawal']):
                return 'other', 0.8
            
            # UPI transfers without clear merchant -> Other
            if any(term in combined_text for term in ['upi', 'transfer', 'neft', 'imps']):
                return 'other', 0.6
                
            # If we found some matches but low confidence, still return the best guess
            if best_category:
                return best_category, max(confidence, 0.4)
        
        return best_category, confidence
    
    def _extract_additional_info(self, text: str) -> Dict:
        """Extract additional information like account details, reference numbers"""
        additional_info = {}
        
        # Extract account last 4 digits
        account_pattern = r'(?:card|account).*?(\d{4})'
        account_match = re.search(account_pattern, text, re.IGNORECASE)
        if account_match:
            additional_info['account_last_four'] = account_match.group(1)
        
        # Extract reference number
        ref_patterns = [
            r'ref(?:erence)?[\s:]+([A-Z0-9]+)',
            r'txn[\s:]+([A-Z0-9]+)',
            r'transaction[\s:]+([A-Z0-9]+)'
        ]
        
        for pattern in ref_patterns:
            ref_match = re.search(pattern, text, re.IGNORECASE)
            if ref_match:
                additional_info['reference_number'] = ref_match.group(1)
                break
        
        # Extract balance information
        balance_pattern = r'(?:balance|bal)[\s:]*(?:Rs\.?\s*|₹\s*)?([0-9,]+(?:\.[0-9]{2})?)'
        balance_match = re.search(balance_pattern, text, re.IGNORECASE)
        if balance_match:
            try:
                balance = float(balance_match.group(1).replace(',', ''))
                additional_info['balance_after'] = balance
            except ValueError:
                pass
        
        return additional_info
    
    def validate_transaction(self, transaction: Dict) -> bool:
        """Validate if extracted transaction data is reasonable"""
        # Check required fields
        if not transaction.get('amount') or transaction['amount'] <= 0:
            return False
        
        # Check if amount is reasonable (not too large)
        if transaction['amount'] > 1000000:  # 1 million threshold
            return False
        
        # Check confidence score
        if transaction.get('confidence_score', 0) < 0.3:
            return False
        
        return True
    
    def process_batch(self, text_list: List[str]) -> List[Dict]:
        """Process multiple text inputs in batch"""
        all_transactions = []
        
        for text in text_list:
            transactions = self.extract_transactions(text)
            valid_transactions = [t for t in transactions if self.validate_transaction(t)]
            all_transactions.extend(valid_transactions)
        
        return all_transactions

# Example usage and test patterns
def test_nlp_processor():
    """Test the NLP processor with sample SMS messages"""
    processor = TransactionProcessor()
    
    sample_messages = [
        "Your A/c X1234 debited Rs.500.00 on 15/10/2024 for payment at AMAZON INDIA. Bal: Rs.25,000.50",
        "Rs 1,250.75 debited from Card x5678 at STARBUCKS COFFEE on 14-Oct-2024. Available bal: Rs 45,000.00",
        "Amount Rs.2,000.00 credited to your account X9876 on 13/10/2024 from SALARY CREDIT. Ref: TXN123456",
        "Your card ending 4321 used for Rs.750.00 at UBER TRIP on 12/10/2024 19:45. Current balance: Rs.18,500.25"
    ]
    
    for i, message in enumerate(sample_messages, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Input: {message}")
        
        transactions = processor.extract_transactions(message)
        for transaction in transactions:
            print(f"Amount: {transaction.get('amount')}")
            print(f"Type: {transaction.get('type')}")
            print(f"Merchant: {transaction.get('merchant')}")
            print(f"Category: {transaction.get('category')}")
            print(f"Date: {transaction.get('date')}")
            print(f"Confidence: {transaction.get('confidence_score'):.2f}")

if __name__ == "__main__":
    test_nlp_processor()
