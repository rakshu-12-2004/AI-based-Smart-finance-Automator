from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
from backend.models.database_models import Transaction, Category, User

class SavingsAnalyzer:
    """
    Advanced analytics service for generating personalized savings recommendations
    based on user spending patterns and financial behavior.
    
    NOTE: This analyzer now works exclusively with Gmail transaction data.
    All sample/mock data has been commented out to ensure recommendations
    are based solely on real transaction data extracted from Gmail emails.
    """
    
    def __init__(self):
        """Initialize the savings analyzer with default parameters"""
        self.min_recommendation_impact = 50.0  # Minimum monthly savings impact
        self.lookback_months = 6  # Months of historical data to analyze
        
        # Spending pattern thresholds
        self.high_frequency_threshold = 10  # Transactions per month
        self.high_amount_percentile = 75  # Top percentile for high amounts
        
        # Category-specific savings opportunities
        self.category_savings_potential = {
            'dining': {'potential': 0.3, 'difficulty': 'easy'},
            'entertainment': {'potential': 0.25, 'difficulty': 'easy'},
            'shopping': {'potential': 0.2, 'difficulty': 'medium'},
            'groceries': {'potential': 0.15, 'difficulty': 'medium'},
            'transportation': {'potential': 0.1, 'difficulty': 'hard'},
            'utilities': {'potential': 0.05, 'difficulty': 'hard'},
        }
    
    def generate_recommendations(self, transactions: List[Transaction]) -> List[Dict]:
        """
        Generate comprehensive savings recommendations based on transaction history
        
        Args:
            transactions: List of user transactions
            
        Returns:
            List of recommendation dictionaries
        """
        if not transactions:
            return []
        
        recommendations = []
        
        # Analyze spending patterns
        spending_analysis = self._analyze_spending_patterns(transactions)
        
        # Generate different types of recommendations
        recommendations.extend(self._recommend_subscription_optimization(spending_analysis))
        recommendations.extend(self._recommend_category_budget_limits(spending_analysis))
        recommendations.extend(self._recommend_high_frequency_spending_reduction(spending_analysis))
        recommendations.extend(self._recommend_seasonal_adjustments(spending_analysis))
        recommendations.extend(self._recommend_merchant_alternatives(spending_analysis))
        recommendations.extend(self._recommend_general_savings_tips(spending_analysis))
        
        # Sort by potential impact and return top recommendations
        recommendations.sort(key=lambda x: x.get('potential_monthly_savings', 0), reverse=True)
        
        return recommendations[:10]  # Return top 10 recommendations
    
    def _analyze_spending_patterns(self, transactions: List[Transaction]) -> Dict:
        """Analyze user spending patterns and identify trends"""
        # Filter transactions to recent months
        cutoff_date = datetime.now() - timedelta(days=30 * self.lookback_months)
        recent_transactions = [t for t in transactions if t.date >= cutoff_date]
        
        analysis = {
            'total_transactions': len(recent_transactions),
            'total_spending': sum(float(t.amount) for t in recent_transactions if t.transaction_type == 'debit'),
            'monthly_average': 0,
            'category_breakdown': defaultdict(list),
            'merchant_breakdown': defaultdict(list),
            'monthly_trends': defaultdict(float),
            'frequency_patterns': defaultdict(int),
            'amount_patterns': defaultdict(list)
        }
        
        if not recent_transactions:
            return analysis
        
        # Calculate monthly average
        months_span = max(1, (datetime.now() - min(t.date for t in recent_transactions)).days / 30)
        analysis['monthly_average'] = analysis['total_spending'] / months_span
        
        # Group by categories and merchants
        for transaction in recent_transactions:
            if transaction.transaction_type == 'debit':
                amount = float(transaction.amount)
                category = transaction.category.name if transaction.category else 'Other'
                merchant = transaction.merchant or 'Unknown'
                month_key = transaction.date.strftime('%Y-%m')
                
                analysis['category_breakdown'][category].append(amount)
                analysis['merchant_breakdown'][merchant].append(amount)
                analysis['monthly_trends'][month_key] += amount
                analysis['frequency_patterns'][category] += 1
                analysis['amount_patterns'][category].append(amount)
        
        return analysis
    
    def _recommend_subscription_optimization(self, analysis: Dict) -> List[Dict]:
        """Identify potential subscription services and recommend optimization"""
        recommendations = []
        
        # Look for recurring payments (same merchant, similar amounts)
        for merchant, amounts in analysis['merchant_breakdown'].items():
            if len(amounts) >= 3 and len(set(amounts)) <= 2:  # Recurring pattern
                monthly_cost = statistics.mean(amounts)
                
                # Check if it's likely a subscription
                subscription_keywords = ['netflix', 'spotify', 'amazon', 'subscription', 'monthly']
                if any(keyword in merchant.lower() for keyword in subscription_keywords) or monthly_cost < 50:
                    
                    potential_savings = monthly_cost * 0.5  # Assume 50% savings possible
                    
                    if potential_savings >= self.min_recommendation_impact:
                        recommendations.append({
                            'type': 'subscription_optimization',
                            'title': f'Review {merchant} Subscription',
                            'description': f'You spend ₹{monthly_cost:.0f}/month on {merchant}. Consider if you actively use this service.',
                            'potential_monthly_savings': potential_savings,
                            'difficulty': 'easy',
                            'action_items': [
                                f'Review your {merchant} usage in the last month',
                                'Consider downgrading to a cheaper plan',
                                'Look for annual plans with discounts',
                                'Cancel if not actively using'
                            ],
                            'category': 'entertainment' if any(k in merchant.lower() for k in ['netflix', 'spotify', 'prime']) else 'other'
                        })
        
        return recommendations
    
    def _recommend_category_budget_limits(self, analysis: Dict) -> List[Dict]:
        """Recommend budget limits for high-spending categories"""
        recommendations = []
        
        for category, amounts in analysis['category_breakdown'].items():
            if not amounts:
                continue
                
            monthly_average = sum(amounts) / max(1, len(analysis['monthly_trends']))
            
            # Get category-specific savings potential
            category_lower = category.lower()
            savings_info = self.category_savings_potential.get(category_lower, {'potential': 0.1, 'difficulty': 'medium'})
            
            potential_savings = monthly_average * savings_info['potential']
            
            if potential_savings >= self.min_recommendation_impact:
                recommendations.append({
                    'type': 'budget_limit',
                    'title': f'Set Budget for {category}',
                    'description': f'You spend ₹{monthly_average:.0f}/month on {category}. Setting a budget could help reduce spending.',
                    'potential_monthly_savings': potential_savings,
                    'difficulty': savings_info['difficulty'],
                    'current_spending': monthly_average,
                    'recommended_budget': monthly_average * (1 - savings_info['potential']),
                    'action_items': [
                        f'Set a monthly budget of ₹{monthly_average * (1 - savings_info["potential"]):.0f} for {category}',
                        'Track your spending weekly',
                        f'Find alternatives to reduce {category} costs',
                        'Use apps to compare prices'
                    ],
                    'category': category_lower
                })
        
        return recommendations
    
    def _recommend_high_frequency_spending_reduction(self, analysis: Dict) -> List[Dict]:
        """Identify high-frequency spending patterns"""
        recommendations = []
        
        for category, frequency in analysis['frequency_patterns'].items():
            monthly_frequency = frequency / max(1, len(analysis['monthly_trends']))
            
            if monthly_frequency >= self.high_frequency_threshold:
                amounts = analysis['category_breakdown'][category]
                avg_amount = statistics.mean(amounts) if amounts else 0
                total_monthly = avg_amount * monthly_frequency
                
                # Focus on categories where frequency reduction is feasible
                if category.lower() in ['dining', 'entertainment', 'shopping']:
                    potential_savings = total_monthly * 0.2  # 20% reduction
                    
                    if potential_savings >= self.min_recommendation_impact:
                        recommendations.append({
                            'type': 'frequency_reduction',
                            'title': f'Reduce {category} Frequency',
                            'description': f'You make {monthly_frequency:.0f} {category} transactions per month. Reducing frequency could save money.',
                            'potential_monthly_savings': potential_savings,
                            'difficulty': 'medium',
                            'current_frequency': monthly_frequency,
                            'recommended_frequency': monthly_frequency * 0.8,
                            'action_items': [
                                f'Plan {category} purchases in advance',
                                'Set weekly limits for impulse purchases',
                                'Use a shopping list to avoid unnecessary items',
                                'Find free alternatives for entertainment'
                            ],
                            'category': category.lower()
                        })
        
        return recommendations
    
    def _recommend_seasonal_adjustments(self, analysis: Dict) -> List[Dict]:
        """Analyze seasonal spending patterns and recommend adjustments"""
        recommendations = []
        
        if len(analysis['monthly_trends']) < 3:
            return recommendations
        
        # Identify months with highest spending
        sorted_months = sorted(analysis['monthly_trends'].items(), key=lambda x: x[1], reverse=True)
        
        if len(sorted_months) >= 2:
            highest_month = sorted_months[0]
            average_spending = sum(analysis['monthly_trends'].values()) / len(analysis['monthly_trends'])
            
            if highest_month[1] > average_spending * 1.3:  # 30% above average
                excess_spending = highest_month[1] - average_spending
                potential_savings = excess_spending * 0.3  # 30% of excess
                
                if potential_savings >= self.min_recommendation_impact:
                    recommendations.append({
                        'type': 'seasonal_adjustment',
                        'title': 'Plan for High-Spending Months',
                        'description': f'Your spending in {highest_month[0]} was ₹{highest_month[1]:.0f}, significantly higher than your average.',
                        'potential_monthly_savings': potential_savings / len(analysis['monthly_trends']),  # Amortized
                        'difficulty': 'medium',
                        'peak_month': highest_month[0],
                        'peak_amount': highest_month[1],
                        'average_amount': average_spending,
                        'action_items': [
                            'Create a separate fund for high-spending months',
                            'Plan major purchases in advance',
                            'Look for seasonal discounts and sales',
                            'Set spending alerts during peak months'
                        ],
                        'category': 'planning'
                    })
        
        return recommendations
    
    def _recommend_merchant_alternatives(self, analysis: Dict) -> List[Dict]:
        """Suggest alternative merchants or services"""
        recommendations = []
        
        # Find high-spending merchants
        high_spending_merchants = []
        for merchant, amounts in analysis['merchant_breakdown'].items():
            total_spent = sum(amounts)
            if total_spent > analysis['monthly_average'] * 0.1:  # 10% of monthly spending
                high_spending_merchants.append((merchant, total_spent, len(amounts)))
        
        for merchant, total_spent, frequency in high_spending_merchants:
            monthly_spent = total_spent / max(1, len(analysis['monthly_trends']))
            
            # Generic recommendations for finding alternatives
            if monthly_spent >= self.min_recommendation_impact:
                potential_savings = monthly_spent * 0.15  # 15% savings from alternatives
                
                recommendations.append({
                    'type': 'merchant_alternative',
                    'title': f'Find Alternatives to {merchant}',
                    'description': f'You spend ₹{monthly_spent:.0f}/month at {merchant}. Exploring alternatives might save money.',
                    'potential_monthly_savings': potential_savings,
                    'difficulty': 'medium',
                    'merchant': merchant,
                    'current_spending': monthly_spent,
                    'transaction_frequency': frequency,
                    'action_items': [
                        f'Research alternatives to {merchant}',
                        'Compare prices for similar products/services',
                        'Look for discount codes and cashback offers',
                        'Consider bulk purchases for better rates'
                    ],
                    'category': 'shopping'
                })
        
        return recommendations
    
    def _recommend_general_savings_tips(self, analysis: Dict) -> List[Dict]:
        """Generate general savings tips based on spending patterns"""
        recommendations = []
        
        monthly_spending = analysis['monthly_average']
        
        # Emergency fund recommendation
        if monthly_spending > 0:
            emergency_target = monthly_spending * 6
            monthly_savings_needed = emergency_target / 12  # Build over a year
            
            recommendations.append({
                'type': 'emergency_fund',
                'title': 'Build Emergency Fund',
                'description': f'Aim to save ₹{emergency_target:.0f} (6 months of expenses) for emergencies.',
                'potential_monthly_savings': 0,  # This is savings goal, not reduction
                'difficulty': 'medium',
                'target_amount': emergency_target,
                'monthly_contribution': monthly_savings_needed,
                'action_items': [
                    f'Save ₹{monthly_savings_needed:.0f} monthly in a separate account',
                    'Automate transfers to emergency fund',
                    'Use high-yield savings account',
                    'Avoid using emergency fund for non-emergencies'
                ],
                'category': 'planning'
            })
        
        # Investment recommendation
        if monthly_spending > 0:
            investment_amount = monthly_spending * 0.2  # 20% of spending for investment
            
            recommendations.append({
                'type': 'investment',
                'title': 'Start Investment Plan',
                'description': f'Consider investing ₹{investment_amount:.0f}/month for long-term wealth building.',
                'potential_monthly_savings': 0,  # This is investment, not reduction
                'difficulty': 'medium',
                'recommended_amount': investment_amount,
                'action_items': [
                    'Research low-cost index funds',
                    'Set up automatic investment transfers',
                    'Diversify across different asset classes',
                    'Review and rebalance quarterly'
                ],
                'category': 'investment'
            })
        
        return recommendations
    
    def calculate_savings_potential(self, transactions: List[Transaction]) -> Dict:
        """Calculate overall savings potential for the user"""
        analysis = self._analyze_spending_patterns(transactions)
        recommendations = self.generate_recommendations(transactions)
        
        total_potential = sum(rec.get('potential_monthly_savings', 0) for rec in recommendations)
        monthly_spending = analysis['monthly_average']
        
        savings_rate = (total_potential / monthly_spending * 100) if monthly_spending > 0 else 0
        
        return {
            'total_monthly_potential': total_potential,
            'current_monthly_spending': monthly_spending,
            'potential_savings_rate': savings_rate,
            'recommendations_count': len(recommendations),
            'easy_wins': len([r for r in recommendations if r.get('difficulty') == 'easy']),
            'medium_effort': len([r for r in recommendations if r.get('difficulty') == 'medium']),
            'hard_changes': len([r for r in recommendations if r.get('difficulty') == 'hard'])
        }
    
    def track_savings_progress(self, user_id: int, previous_months: int = 3) -> Dict:
        """Track user's progress on savings over time"""
        # This would require additional database tracking
        # For now, return placeholder structure
        return {
            'period_months': previous_months,
            'spending_reduction': 0,
            'recommendations_followed': 0,
            'total_recommendations': 0,
            'improvement_score': 0
        }

# # Example usage - COMMENTED OUT TO USE ONLY GMAIL DATA
# def test_savings_analyzer():
#     """Test the savings analyzer with sample data"""
#     analyzer = SavingsAnalyzer()
#     
#     # This would normally use real Transaction objects
#     # For testing, we'll just demonstrate the structure
#     sample_analysis = {
#         'total_spending': 50000,
#         'monthly_average': 25000,
#         'category_breakdown': {
#             'dining': [1500, 1200, 1800, 1600],
#             'entertainment': [800, 900, 750, 850],
#             'groceries': [4000, 3800, 4200, 3900]
#         },
#         'merchant_breakdown': {
#             'Netflix': [799, 799, 799],
#             'Zomato': [1200, 1500, 1800, 1300],
#             'BigBasket': [2000, 1800, 2200, 1900]
#         },
#         'monthly_trends': {'2024-08': 24000, '2024-09': 26000},
#         'frequency_patterns': {'dining': 15, 'entertainment': 8, 'groceries': 12},
#         'amount_patterns': {'dining': [150, 200, 180, 220, 175]}
#     }
#     
#     print("Sample savings recommendations would be generated based on this analysis structure")

# if __name__ == "__main__":
#     test_savings_analyzer()
