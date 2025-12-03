"""
Multi-Account Gmail Service for Smart Finance Automator
Supports multiple Gmail accounts for transaction processing
"""

import os
import base64
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pickle

try:
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

class MultiAccountGmailService:
    """
    Service class for managing multiple Gmail accounts
    """
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials_file='credentials.json'):
        self.credentials_file = credentials_file
        self.accounts = {}  # Dictionary to store multiple account services
        self.current_account = None
        
        # Bank email patterns for filtering
        self.bank_domains = [
            'alerts@sbi.co.in',
            'alerts@hdfcbank.com', 
            'alerts@icicibank.com',
            'alerts@axisbank.com',
            'noreply@kotak.com',
            'alerts@citi.com',
            'alerts@sc.com',
            'noreply@paytm.com',
            'alerts@phonepe.com',
            'noreply@gpay.com',
            'alerts@bankofbaroda.com',
            'alerts@pnb.co.in',
            'noreply@unionbankofindia.co.in',
            'indusind_bank@indusind.com'
        ]
        
        self.transaction_keywords = [
            'debited', 'credited', 'transaction', 'payment', 'purchase',
            'withdrawal', 'deposit', 'balance', 'account', 'card used',
            'spent at', 'received from', 'transfer', 'bill payment'
        ]
    
    def add_account(self, account_name: str) -> bool:
        """
        Add a new Gmail account
        
        Args:
            account_name: Unique identifier for the account
            
        Returns:
            True if authentication successful
        """
        if not GMAIL_AVAILABLE:
            print("Gmail API not available")
            return False
        
        token_file = f'gmail_token_{account_name}.pickle'
        
        creds = None
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    print(f"Credentials file '{self.credentials_file}' not found.")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                try:
                    creds = flow.run_local_server(port=8080, host='localhost')
                except OSError:
                    try:
                        creds = flow.run_local_server(port=8081, host='localhost')
                    except OSError:
                        creds = flow.run_local_server(port=0, host='localhost')
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        try:
            service = build('gmail', 'v1', credentials=creds)
            
            # Get user email
            profile = service.users().getProfile(userId='me').execute()
            email_address = profile['emailAddress']
            
            self.accounts[account_name] = {
                'service': service,
                'email': email_address,
                'token_file': token_file
            }
            
            if not self.current_account:
                self.current_account = account_name
            
            print(f"✅ Added account: {email_address}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add account: {e}")
            return False
    
    def list_accounts(self) -> List[Dict]:
        """List all configured accounts"""
        accounts_info = []
        for name, info in self.accounts.items():
            accounts_info.append({
                'name': name,
                'email': info['email'],
                'is_current': name == self.current_account
            })
        return accounts_info
    
    def switch_account(self, account_name: str) -> bool:
        """Switch to a different account"""
        if account_name in self.accounts:
            self.current_account = account_name
            print(f"✅ Switched to account: {self.accounts[account_name]['email']}")
            return True
        print(f"❌ Account '{account_name}' not found")
        return False
    
    def remove_account(self, account_name: str) -> bool:
        """Remove an account"""
        if account_name in self.accounts:
            # Delete token file
            token_file = self.accounts[account_name]['token_file']
            if os.path.exists(token_file):
                os.remove(token_file)
            
            # Remove from accounts
            email = self.accounts[account_name]['email']
            del self.accounts[account_name]
            
            # Switch to another account if this was current
            if self.current_account == account_name:
                self.current_account = list(self.accounts.keys())[0] if self.accounts else None
            
            print(f"✅ Removed account: {email}")
            return True
        return False
    
    def sync_all_accounts(self, days_back: int = 7) -> Dict[str, List]:
        """
        Sync emails from all accounts
        
        Returns:
            Dictionary with account emails and their transactions
        """
        all_transactions = {}
        
        for account_name, account_info in self.accounts.items():
            print(f"📧 Syncing account: {account_info['email']}")
            
            # Temporarily switch to this account
            old_current = self.current_account
            self.current_account = account_name
            
            # Get transactions
            transactions = self.search_transaction_emails(days_back=days_back)
            all_transactions[account_name] = {
                'email': account_info['email'],
                'transactions': transactions
            }
            
            # Restore current account
            self.current_account = old_current
        
        return all_transactions
    
    def search_transaction_emails(self, days_back: int = 30, max_results: int = 100) -> List[Dict]:
        """Search for transaction emails in current account"""
        if not self.current_account or self.current_account not in self.accounts:
            print("No current account selected")
            return []
        
        service = self.accounts[self.current_account]['service']
        account_email = self.accounts[self.current_account]['email']
        
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
        
        # Try multiple queries in order of preference
        queries = [
            f'({bank_query}) AND ({keyword_query}) AND after:{query_date}',  # Specific bank domains + keywords
            f'({financial_query}) AND ({keyword_query}) AND after:{query_date}',  # Financial domains + keywords
            f'({keyword_query}) AND after:{query_date}',  # Just keywords (but filtered later by content)
            f'from:indusind_bank@indusind.com',  # Debug: IndusInd emails without date filter
            f'from:indusind.com',  # Debug: Any IndusInd domain emails
        ]
        
        all_messages = []
        
        for i, query in enumerate(queries):
            try:
                print(f"🔍 Searching {account_email} with query {i+1}: {query}")
                
                results = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=max_results
                ).execute()
                
                messages = results.get('messages', [])
                
                if messages:
                    print(f"📧 Found {len(messages)} emails in {account_email} with query {i+1}")
                    all_messages.extend(messages)
                    break  # Use first successful query
                else:
                    print(f"No emails found in {account_email} with query {i+1}")
                    
            except Exception as e:
                print(f"Error with query {i+1} for {account_email}: {e}")
                continue
        
        if not all_messages:
            print(f"No transaction emails found in {account_email}")
            return []
        
        # Remove duplicates based on message ID
        unique_messages = {msg['id']: msg for msg in all_messages}.values()
        print(f"📧 Found {len(unique_messages)} unique emails in {account_email}")
        
        # Get email details
        email_data = []
        for message in unique_messages:
            email_details = self._get_email_details(message['id'], service)
            if email_details:
                # Additional filtering by content
                if self._is_transaction_email(email_details):
                    email_data.append(email_details)
                    print(f"✅ Valid transaction email in {account_email}: {email_details['subject'][:50]}...")
                else:
                    print(f"❌ Skipped non-transaction email in {account_email}: {email_details['subject'][:50]}...")
        
        print(f"📊 Final result for {account_email}: {len(email_data)} transaction emails")
        return email_data
    
    def _get_email_details(self, message_id: str, service) -> Optional[Dict]:
        """Get detailed information for a specific email"""
        try:
            message = service.users().messages().get(
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
                'raw_date': date,
                'account_email': self.accounts[self.current_account]['email']
            }
            
        except Exception as e:
            print(f"Error getting email details: {e}")
            return None
    
    def _is_transaction_email(self, email_details: Dict) -> bool:
        """
        Check if an email is likely to be a transaction email based on content
        
        Args:
            email_details: Dictionary with email details
            
        Returns:
            True if email appears to be transaction-related
        """
        subject = email_details.get('subject', '').lower()
        body = email_details.get('body', '').lower()
        sender = email_details.get('sender', '').lower()
        
        # First check if sender is from a financial institution
        financial_senders = [
            'bank', 'sbi', 'hdfc', 'icici', 'axis', 'kotak', 'citi', 'sc.com',
            'indusind', 'indus',  # IndusInd Bank patterns
            'paytm', 'phonepe', 'gpay', 'freecharge', 'mobikwik',
            'visa', 'mastercard', 'rupay', 'credit', 'debit', 'wallet'
        ]
        
        is_financial_sender = any(domain in sender for domain in financial_senders)
        
        # Check for strong transaction indicators
        strong_transaction_indicators = [
            # Direct transaction terms
            'debited', 'credited', 'transaction', 'payment', 'purchase',
            'withdrawal', 'deposit', 'card used', 'spent at', 'received from',
            'bill payment', 'transfer', 'refund', 'cashback',
            
            # Amount indicators (must be present for transaction)
            'rs.', 'rs ', '₹', 'inr ', 'amount of', 'amount:', 'amt:',
            
            # UPI and digital payment terms
            'upi', 'neft', 'imps', 'rtgs', 'nach', 'emi',
        ]
        
        # Check for amount patterns (more specific)
        amount_patterns = [
            r'rs\.?\s*\d+', r'₹\s*\d+', r'inr\s*\d+', r'amount.*\d+',
            r'\d+\s*rupees?', r'spent.*\d+', r'paid.*\d+', r'received.*\d+'
        ]
        
        import re
        text_to_check = f"{subject} {body}"
        
        # Must have at least one strong transaction indicator
        has_transaction_indicator = any(indicator in text_to_check for indicator in strong_transaction_indicators)
        
        # Must have amount pattern or be from financial sender
        has_amount_pattern = any(re.search(pattern, text_to_check) for pattern in amount_patterns)
        
        # For non-financial senders, require both transaction indicators and amount patterns
        if not is_financial_sender:
            return has_transaction_indicator and has_amount_pattern
        
        # For financial senders, either transaction indicator OR amount pattern is sufficient
        return has_transaction_indicator or has_amount_pattern
    
    def _extract_email_body(self, payload) -> str:
        """Extract text body from email payload"""
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

# Example usage
if __name__ == "__main__":
    multi_gmail = MultiAccountGmailService()
    
    # Add primary account
    if multi_gmail.add_account('primary'):
        print("Primary account added successfully")
        
        # Search for transactions
        transactions = multi_gmail.search_transaction_emails(days_back=7)
        print(f"Found {len(transactions)} transactions")
        
        # List all accounts
        accounts = multi_gmail.list_accounts()
        print("Configured accounts:", accounts)
