"""
Gmail API Service for Smart Finance Automator
Automatically fetches and processes bank notification emails
"""

import os
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email.mime.text import MIMEText
import pickle
import re

# Gmail API imports (to be installed)
try:
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("Gmail API not available. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

class GmailService:
    """
    Service class for integrating Gmail API with transaction processing
    """
    
    # Gmail API scope for reading emails
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials_file='credentials.json', token_file='gmail_token.pickle'):
        """
        Initialize Gmail service with OAuth2 authentication
        
        Args:
            credentials_file: Path to Google API credentials JSON file
            token_file: Path to store OAuth2 token
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.authenticated = False
        
        # Bank email patterns for filtering - Enhanced for better detection
        self.bank_domains = [
            # Major Indian banks
            'alerts@sbi.co.in', 'sbi.co.in',
            'alerts@hdfcbank.com', 'hdfcbank.com',
            'alerts@icicibank.com', 'icicibank.com',
            'alerts@axisbank.com', 'axisbank.com',
            'noreply@kotak.com', 'kotak.com',
            'alerts@citi.com', 'citi.com',
            'alerts@sc.com', 'sc.com',
            'indusind_bank@indusind.com', 'indusind.com', 'induslnd.com',  # IndusInd variations
            'alerts@bankofbaroda.com', 'bankofbaroda.com',
            'alerts@pnb.co.in', 'pnb.co.in',
            'noreply@unionbankofindia.co.in', 'unionbankofindia.co.in',
            # Digital payment services
            'noreply@paytm.com', 'paytm.com',
            'alerts@phonepe.com', 'phonepe.com',
            'noreply@gpay.com', 'pay.google.com',
            'noreply@amazonpay.in', 'amazonpay.in',
            # Credit card companies
            'amex.co.in', 'americanexpress.co.in'
        ]
        
        # Keywords to identify transaction emails - Enhanced for Indian banking
        self.transaction_keywords = [
            # Core transaction terms
            'debited', 'credited', 'transaction', 'payment', 'purchase',
            'withdrawal', 'deposit', 'balance', 'account', 'card used',
            'spent at', 'received from', 'transfer', 'bill payment',
            # Indian banking specific
            'a/c', 'acc', 'txn', 'ref no', 'reference', 'upi', 'imps', 'neft', 'rtgs',
            'available balance', 'current balance', 'statement', 'kyc',
            # Amount indicators
            'rs.', 'rs ', '₹', 'inr', 'amount', 'amt',
            # Digital payment terms
            'paytm', 'phonepe', 'gpay', 'bhim', 'mobikwik',
            # Card terms
            'debit card', 'credit card', 'atm', 'pos', 'online transaction'
        ]
        
        if GMAIL_AVAILABLE:
            self._authenticate()
    
    def _authenticate(self):
        """
        Authenticate with Gmail API using OAuth2
        """
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    print(f"Gmail credentials file '{self.credentials_file}' not found.")
                    print("Please download it from Google Cloud Console and place it in the project root.")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                # Try different ports to avoid conflicts
                try:
                    creds = flow.run_local_server(port=8080, host='localhost')
                except OSError:
                    try:
                        creds = flow.run_local_server(port=8081, host='localhost')
                    except OSError:
                        # Let the system choose an available port
                        creds = flow.run_local_server(port=0, host='localhost')
            
            # Save credentials for next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        # Build Gmail service
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            self.authenticated = True
            print("✅ Gmail API authentication successful!")
            return True
        except Exception as e:
            print(f"❌ Gmail API authentication failed: {e}")
            return False
    
    def search_transaction_emails(self, days_back: int = 30, max_results: int = 100) -> List[Dict]:
        """
        Search for transaction-related emails from bank domains
        
        Args:
            days_back: Number of days to look back for emails
            max_results: Maximum number of emails to fetch
            
        Returns:
            List of email data dictionaries
        """
        if not self.authenticated:
            print("Gmail API not authenticated")
            return []
        
        # Calculate date range
        start_date = datetime.now() - timedelta(days=days_back)
        query_date = start_date.strftime('%Y/%m/%d')
        
        # Build search query - First try bank domains, then fall back to keywords only
        bank_query = ' OR '.join([f'from:{domain}' for domain in self.bank_domains])
        keyword_query = ' OR '.join(self.transaction_keywords)
        
        # Expanded bank/financial domains for broader but still focused search
        financial_keywords = [
            'bank', 'credit', 'debit', 'payment', 'transaction', 'upi', 'gpay', 
            'paytm', 'phonepe', 'wallet', 'visa', 'mastercard', 'rupay'
        ]
        financial_query = ' OR '.join([f'from:*{domain}*' for domain in financial_keywords])
        
        # Try multiple queries in order of preference (VERY BROAD FOR DEBUGGING)
        queries = [
            f'from:indusind.com',  # Start with what we know exists
            f'subject:(account OR bank OR payment OR transaction OR amount OR balance OR money OR rs OR rupee OR ₹)',  # Very broad subject search
            f'(account OR bank OR payment OR transaction OR amount OR balance OR money OR rs OR rupee OR ₹) AND after:{query_date}',  # Very broad content search
            f'from:*bank*',  # Any email from any bank
            f'from:*pay*',  # Any payment service
            f'from:*alert*',  # Any alert service
            f'({bank_query}) AND ({keyword_query}) AND after:{query_date}',  # Original specific search
        ]
        
        all_messages = []
        
        for i, query in enumerate(queries):
            try:
                print(f"🔍 Searching with query {i+1}: {query}")
                
                # Search for emails
                results = self.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=max_results
                ).execute()
                
                messages = results.get('messages', [])
                
                if messages:
                    print(f"📧 Found {len(messages)} emails with query {i+1}")
                    all_messages.extend(messages)
                    break  # Use first successful query
                else:
                    print(f"No emails found with query {i+1}")
                    
            except Exception as e:
                print(f"Error with query {i+1}: {e}")
                continue
        
        if not all_messages:
            print("No transaction emails found with any query")
            return []
        
        # Remove duplicates based on message ID
        unique_messages = {msg['id']: msg for msg in all_messages}.values()
        print(f"📧 Found {len(unique_messages)} unique potential transaction emails")
        
        # Get email details
        email_data = []
        skipped_count = 0
        for i, message in enumerate(unique_messages, 1):
            print(f"\n📧 Processing email {i}/{len(unique_messages)}...")
            email_details = self._get_email_details(message['id'])
            if email_details:
                # Additional filtering by content
                if self._is_transaction_email(email_details):
                    email_data.append(email_details)
                    print(f"✅ ADDED: {email_details['subject'][:60]}...")
                else:
                    skipped_count += 1
                    print(f"❌ SKIPPED: {email_details['subject'][:60]}...")
        
        print(f"\n{'='*60}")
        print(f"📊 FINAL RESULTS:")
        print(f"   Total emails analyzed: {len(unique_messages)}")
        print(f"   ✅ Accepted (transactional): {len(email_data)}")
        print(f"   ❌ Rejected (non-transactional): {skipped_count}")
        print(f"{'='*60}\n")
        return email_data
    
    def _get_email_details(self, message_id: str) -> Optional[Dict]:
        """
        Get detailed information for a specific email
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Dictionary with email details
        """
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Extract body
            body = self._extract_email_body(message['payload'])
            
            # Parse date
            try:
                email_date = datetime.strptime(date.split(' (')[0], '%a, %d %b %Y %H:%M:%S %z')
            except:
                email_date = datetime.now()
            
            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': email_date,
                'body': body,
                'raw_date': date
            }
            
        except Exception as e:
            print(f"Error getting email details for {message_id}: {e}")
            return None
    
    def _extract_email_body(self, payload) -> str:
        """
        Extract text body from email payload
        
        Args:
            payload: Gmail message payload
            
        Returns:
            Email body text
        """
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body']['data']
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
        else:
            if payload['mimeType'] == 'text/plain':
                data = payload['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body
    
    def get_recent_bank_notifications(self, hours_back: int = 24) -> List[Dict]:
        """
        Get recent bank notification emails
        
        Args:
            hours_back: Hours to look back for emails
            
        Returns:
            List of recent transaction emails
        """
        if not self.authenticated:
            return []
        
        # Search for very recent emails
        start_time = datetime.now() - timedelta(hours=hours_back)
        query_date = start_time.strftime('%Y/%m/%d')
        
        bank_query = ' OR '.join([f'from:{domain}' for domain in self.bank_domains])
        query = f'({bank_query}) AND after:{query_date}'
        
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50
            ).execute()
            
            messages = results.get('messages', [])
            recent_emails = []
            
            for message in messages:
                email_details = self._get_email_details(message['id'])
                if email_details and self._contains_transaction_keywords(email_details['body']):
                    recent_emails.append(email_details)
            
            return recent_emails
            
        except Exception as e:
            print(f"Error getting recent notifications: {e}")
            return []
    
    def _contains_transaction_keywords(self, text: str) -> bool:
        """
        Check if email text contains transaction-related keywords
        
        Args:
            text: Email body text
            
        Returns:
            True if contains transaction keywords
        """
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.transaction_keywords)
    
    def _is_transaction_email(self, email_details: Dict) -> bool:
        """
        Check if an email is likely to be a transaction email based on content
        Uses comprehensive patterns to detect banking/financial transaction emails
        """
        subject = email_details.get('subject', '').lower()
        body = email_details.get('body', '').lower()
        sender = email_details.get('sender', '').lower()
        
        print(f"   🔍 Analyzing email from {sender}: '{subject[:60]}...'")
        
        # Combine subject and body for analysis
        text_to_check = f"{subject} {body}"
        
        # STRONG transaction indicators - if ANY of these are present, it's likely transactional
        strong_indicators = [
            # Transaction keywords
            'debited', 'credited', 'withdrawn', 'deposited', 'paid', 'received',
            'transaction', 'payment', 'purchase', 'spent',
            
            # Amount patterns (INR)
            'rs.', 'rs ', 'inr', '₹', 'rupees',
            
            # Account activity
            'account', 'a/c', 'acc no', 'balance',
            
            # Payment methods
            'upi', 'neft', 'imps', 'rtgs', 'card', 'atm', 'pos',
            
            # Transaction details
            'ref no', 'reference number', 'txn', 'merchant', 'available balance',
            
            # Banking context
            'bank alert', 'bank notification', 'transaction alert'
        ]
        
        # Trusted bank domains - emails from these are likely transactional
        trusted_banks = [
            'hdfcbank', 'sbi.co.in', 'icicibank', 'axisbank', 'kotak', 
            'indusind', 'yesbank', 'pnb', 'bankofbaroda', 'canarabank',
            'unionbank', 'idbi', 'idfc', 'rbl', 'paytm', 'phonepe', 'googlepay',
            'amazon.in', 'flipkart', 'myntra', 'swiggy', 'zomato', 'uber', 'ola'
        ]
        
        # EXCLUDE promotional/marketing emails
        exclude_patterns = [
            'unsubscribe', 'newsletter', 'offer', 'discount', 'sale',
            'limited time', 'hurry', 'shop now', 'buy now', 'free delivery',
            'advertisement', 'promotional', 'marketing'
        ]
        
        # Check for exclusions first
        has_spam_patterns = any(exclude in text_to_check for exclude in exclude_patterns)
        if has_spam_patterns and 'transaction' not in text_to_check and 'payment' not in text_to_check:
            print(f"   ❌ Excluded - Marketing/Promotional email")
            return False
        
        # Check if sender is from trusted bank
        is_trusted_sender = any(bank in sender for bank in trusted_banks)
        
        # Check for strong transaction indicators
        has_strong_indicator = any(indicator in text_to_check for indicator in strong_indicators)
        
        # Decision logic
        if is_trusted_sender and has_strong_indicator:
            print(f"   ✅ ACCEPTED - Trusted sender + transaction indicator")
            return True
        elif has_strong_indicator:
            print(f"   ✅ ACCEPTED - Strong transaction indicator found")
            return True
        elif is_trusted_sender:
            print(f"   ⚠️ ACCEPTED - Trusted bank sender (may be transactional)")
            return True
        else:
            print(f"   ❌ REJECTED - No strong transaction indicators")
            return False
    
   

# Example usage and testing functions
def test_gmail_service():
    """Test Gmail service functionality"""
    gmail = GmailService()
    
    if gmail.authenticated:
        print("🔍 Searching for transaction emails...")
        emails = gmail.search_transaction_emails(days_back=7, max_results=10)
        
        for email in emails:
            print(f"\n📧 From: {email['sender']}")
            print(f"📅 Date: {email['date']}")
            print(f"📋 Subject: {email['subject']}")
            print(f"📄 Body preview: {email['body'][:200]}...")
    else:
        print("Gmail authentication failed")
        setup_info = gmail.setup_gmail_integration()
        print("\n📋 Gmail API Setup Instructions:")
        for step, instruction in setup_info.items():
            if step.startswith('step_'):
                print(f"{step.replace('_', ' ').title()}: {instruction}")

if __name__ == "__main__":
    test_gmail_service()
