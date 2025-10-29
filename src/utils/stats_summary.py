#!/usr/bin/env python3
# Run with: python src/utils/stats_summary.py

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List
from prettytable import PrettyTable

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.db.connection import get_db
from src.db.operations import (
    get_portfolio_state,
    get_portfolio_positions,
    get_trades,
    get_portfolio_history,
    get_current_signals,
    get_events,
    get_markets
)
from sqlalchemy import text

# ANSI color codes for terminal formatting
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def format_currency(amount: float) -> str:
    """Format amount as currency with color"""
    if amount >= 0:
        return f"{Colors.GREEN}${amount:,.2f}{Colors.END}"
    else:
        return f"{Colors.RED}${amount:,.2f}{Colors.END}"

def format_percentage(value: float) -> str:
    """Format value as percentage with color"""
    if value >= 0:
        return f"{Colors.GREEN}{value:+.1f}%{Colors.END}"
    else:
        return f"{Colors.RED}{value:+.1f}%{Colors.END}"

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}")

def print_section(title: str):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}--- {title} ---{Colors.END}")

def get_portfolio_stats() -> Dict:
    """Get comprehensive portfolio statistics"""
    try:
        # Current portfolio state
        portfolio = get_portfolio_state()
        
        # Open positions
        open_positions = get_portfolio_positions(status='open')
        closed_positions = get_portfolio_positions(status='closed')
        
        # Recent trades
        recent_trades = get_trades(limit=100)
        
        # Portfolio history
        history = get_portfolio_history(limit=30)
        
        # Calculate additional stats
        total_invested = sum(pos['amount'] for pos in open_positions)
        total_unrealized_pnl = sum(pos['current_pnl'] for pos in open_positions)
        total_realized_pnl = sum(pos['realized_pnl'] for pos in closed_positions if pos['realized_pnl'])
        
        # Win rate calculation
        closed_with_pnl = [pos for pos in closed_positions if pos['realized_pnl'] is not None]
        winning_trades = len([pos for pos in closed_with_pnl if pos['realized_pnl'] > 0])
        win_rate = (winning_trades / len(closed_with_pnl) * 100) if closed_with_pnl else 0
        
        # Daily performance
        daily_change = 0
        if len(history) > 1:
            daily_change = history[0]['total_value'] - history[1]['total_value']
        
        return {
            'portfolio': portfolio,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'recent_trades': recent_trades,
            'history': history,
            'stats': {
                'total_invested': total_invested,
                'total_unrealized_pnl': total_unrealized_pnl,
                'total_realized_pnl': total_realized_pnl,
                'win_rate': win_rate,
                'daily_change': daily_change,
                'total_closed_trades': len(closed_with_pnl)
            }
        }
    except Exception as e:
        print(f"{Colors.RED}Error getting portfolio stats: {e}{Colors.END}")
        return {}

def get_trading_activity_stats() -> Dict:
    """Get trading activity statistics"""
    try:
        # Recent signals
        current_signals = get_current_signals(limit=50)
        executed_signals = get_current_signals(limit=50, executed=True)
        
        # Events and markets
        events = get_events({'is_filtered': True})
        markets = get_markets({'is_filtered': True})
        
        # Trade activity by day
        with get_db() as db:
            result = db.execute(text("""
                SELECT DATE(timestamp) as trade_date, 
                       COUNT(*) as trade_count,
                       SUM(amount) as total_amount,
                       SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades
                FROM trades 
                WHERE timestamp >= NOW() - INTERVAL '7 days'
                GROUP BY DATE(timestamp)
                ORDER BY trade_date DESC
            """)).fetchall()
            
            daily_activity = []
            for row in result:
                daily_activity.append({
                    'date': row[0],
                    'trade_count': row[1],
                    'total_amount': float(row[2]) if row[2] else 0,
                    'winning_trades': row[3]
                })
        
        return {
            'current_signals': current_signals,
            'executed_signals': executed_signals,
            'events': events,
            'markets': markets,
            'daily_activity': daily_activity
        }
    except Exception as e:
        print(f"{Colors.RED}Error getting trading activity stats: {e}{Colors.END}")
        return {}

def display_portfolio_overview(portfolio_data: Dict):
    """Display portfolio overview using PrettyTable"""
    if not portfolio_data:
        print(f"{Colors.YELLOW}No portfolio data available{Colors.END}")
        return
    
    portfolio = portfolio_data.get('portfolio', {})
    stats = portfolio_data.get('stats', {})
    
    # Create portfolio overview table
    table = PrettyTable()
    table.field_names = ["Metric", "Value"]
    table.align["Metric"] = "l"
    table.align["Value"] = "r"
    
    table.add_row(["Balance", format_currency(portfolio.get('balance', 0))])
    table.add_row(["Total Invested", format_currency(stats.get('total_invested', 0))])
    table.add_row(["Total P&L", format_currency(portfolio.get('total_profit_loss', 0))])
    table.add_row(["Unrealized P&L", format_currency(stats.get('total_unrealized_pnl', 0))])
    table.add_row(["Realized P&L", format_currency(stats.get('total_realized_pnl', 0))])
    table.add_row(["Daily Change", format_currency(stats.get('daily_change', 0))])
    table.add_row(["Total Value", format_currency(portfolio.get('balance', 0) + portfolio.get('total_profit_loss', 0))])
    
    print_section("Portfolio Overview")
    print(table)

def display_positions_summary(portfolio_data: Dict):
    """Display positions summary using PrettyTable"""
    if not portfolio_data:
        print(f"{Colors.YELLOW}No position data available{Colors.END}")
        return
    
    open_positions = portfolio_data.get('open_positions', [])
    stats = portfolio_data.get('stats', {})
    
    # Create positions summary table
    table = PrettyTable()
    table.field_names = ["Status", "Count", "Total Amount", "P&L"]
    table.align["Status"] = "l"
    table.align["Count"] = "r"
    table.align["Total Amount"] = "r"
    table.align["P&L"] = "r"
    
    table.add_row([
        "Open Positions",
        len(open_positions),
        f"${sum(pos['amount'] for pos in open_positions):,.2f}",
        format_currency(sum(pos['current_pnl'] for pos in open_positions))
    ])
    
    table.add_row([
        "Closed Trades",
        stats.get('total_closed_trades', 0),
        "N/A",
        format_currency(stats.get('total_realized_pnl', 0))
    ])
    
    table.add_row([
        "Win Rate",
        f"{stats.get('win_rate', 0):.1f}%",
        "N/A",
        "N/A"
    ])
    
    print_section("Positions Summary")
    print(table)

def display_trading_activity(activity_data: Dict):
    """Display trading activity using PrettyTable"""
    if not activity_data:
        print(f"{Colors.YELLOW}No activity data available{Colors.END}")
        return
    
    current_signals = activity_data.get('current_signals', [])
    executed_signals = activity_data.get('executed_signals', [])
    events = activity_data.get('events', [])
    markets = activity_data.get('markets', [])
    
    # Create trading activity table
    table = PrettyTable()
    table.field_names = ["Metric", "Count", "Details"]
    table.align["Metric"] = "l"
    table.align["Count"] = "r"
    table.align["Details"] = "l"
    
    table.add_row([
        "Current Signals",
        len(current_signals),
        f"{len(executed_signals)} executed"
    ])
    
    table.add_row([
        "Filtered Events",
        len(events),
        "Active trading candidates"
    ])
    
    table.add_row([
        "Filtered Markets",
        len(markets),
        "Available for analysis"
    ])
    
    # Recent activity
    daily_activity = activity_data.get('daily_activity', [])
    if daily_activity:
        today = daily_activity[0] if daily_activity else {}
        table.add_row([
            "Today's Trades",
            today.get('trade_count', 0),
            f"${today.get('total_amount', 0):,.0f} volume"
        ])
    
    print_section("Trading Activity")
    print(table)

def display_recent_trades(portfolio_data: Dict):
    """Display recent trades using PrettyTable"""
    if not portfolio_data:
        print(f"{Colors.YELLOW}No trades data available{Colors.END}")
        return
    
    recent_trades = portfolio_data.get('recent_trades', [])[:5]  # Top 5
    
    if not recent_trades:
        print(f"{Colors.YELLOW}No recent trades{Colors.END}")
        return
    
    # Create recent trades table
    table = PrettyTable()
    table.field_names = ["Time", "Action", "Amount", "Price", "P&L"]
    table.align["Time"] = "l"
    table.align["Action"] = "l"
    table.align["Amount"] = "r"
    table.align["Price"] = "r"
    table.align["P&L"] = "r"
    
    for trade in recent_trades:
        timestamp = trade.get('timestamp', '')
        if timestamp:
            time_str = timestamp.split('T')[1][:8] if 'T' in timestamp else timestamp[:8]
        else:
            time_str = 'N/A'
        
        action = trade.get('action', 'N/A')[:10]
        amount = trade.get('amount', 0)
        price = trade.get('entry_price', 0)
        pnl = trade.get('current_pnl', 0) or trade.get('realized_pnl', 0) or 0
        
        table.add_row([
            time_str,
            action,
            f"${amount:,.0f}",
            f"{price:.4f}",
            format_currency(pnl)
        ])
    
    print_section("Recent Trades")
    print(table)

def display_performance_chart(portfolio_data: Dict):
    """Display performance chart using PrettyTable"""
    if not portfolio_data:
        print(f"{Colors.YELLOW}No performance data available{Colors.END}")
        return
    
    history = portfolio_data.get('history', [])[:10]  # Last 10 days
    
    if not history:
        print(f"{Colors.YELLOW}No performance history{Colors.END}")
        return
    
    # Create performance table
    table = PrettyTable()
    table.field_names = ["Date", "Value", "Chart"]
    table.align["Date"] = "l"
    table.align["Value"] = "r"
    table.align["Chart"] = "l"
    
    max_value = max(h['total_value'] for h in history) if history else 1
    min_value = min(h['total_value'] for h in history) if history else 0
    range_value = max_value - min_value if max_value != min_value else 1
    
    for record in reversed(history):
        value = record['total_value']
        normalized = (value - min_value) / range_value if range_value > 0 else 0.5
        bar_length = int(normalized * 20)
        bar = "#" * bar_length + "." * (20 - bar_length)
        date_str = record['snapshot_date'].strftime('%m/%d') if record['snapshot_date'] else 'N/A'
        
        table.add_row([
            date_str,
            f"${value:,.0f}",
            bar
        ])
    
    print_section("Performance (10 days)")
    print(table)

def main():
    """Main function to display stats summary"""
    print_header("Prescient OS - Trading Statistics Dashboard")
    
    # Get data
    portfolio_data = get_portfolio_stats()
    activity_data = get_trading_activity_stats()
    
    # Display all sections
    display_portfolio_overview(portfolio_data)
    display_positions_summary(portfolio_data)
    display_trading_activity(activity_data)
    display_recent_trades(portfolio_data)
    display_performance_chart(portfolio_data)
    
    # Footer
    print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.CYAN}Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
    print(f"{Colors.CYAN}{'='*80}{Colors.END}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Dashboard closed by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Error running dashboard: {e}{Colors.END}")
        import traceback
        print(f"{traceback.format_exc()}")