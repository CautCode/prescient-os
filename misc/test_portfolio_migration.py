"""
Test script for Portfolio Migration - Phase 2, Step 5
Tests all database operations to verify portfolio-centric architecture works correctly
"""

from datetime import datetime
from src.db.operations import (
    create_portfolio,
    get_portfolio_state,
    get_all_portfolios,
    update_portfolio,
    add_portfolio_position,
    get_portfolio_positions,
    update_portfolio_position,
    close_portfolio_position,
    insert_trade,
    get_trades,
    get_trade_by_id,
    update_trade_status,
    insert_signal,
    insert_signals,
    get_current_signals,
    mark_signal_executed,
    insert_portfolio_history_snapshot,
    get_portfolio_history
)

def print_test(test_name):
    """Print test name"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")

def print_success(message):
    """Print success message"""
    print(f"✓ {message}")

def print_error(message):
    """Print error message"""
    print(f"✗ {message}")

def main():
    print("\n" + "="*60)
    print("PORTFOLIO MIGRATION TEST SUITE")
    print("Phase 2, Step 5: Database Operations Testing")
    print("="*60)

    try:
        # ====================================================================
        # TEST 1: Portfolio Management
        # ====================================================================
        print_test("1. Portfolio Management Functions")

        # Create first portfolio
        portfolio_id_1 = create_portfolio({
            'name': 'Test Momentum Portfolio',
            'description': 'Testing momentum strategy',
            'strategy_type': 'momentum',
            'initial_balance': 10000.00,
            'strategy_config': {
                'min_confidence': 0.75,
                'market_types': ['politics', 'crypto']
            }
        })
        print_success(f"Created portfolio 1 with ID: {portfolio_id_1}")

        # Create second portfolio
        portfolio_id_2 = create_portfolio({
            'name': 'Test Mean Reversion Portfolio',
            'description': 'Testing mean reversion strategy',
            'strategy_type': 'mean_reversion',
            'initial_balance': 5000.00,
            'strategy_config': {
                'z_score_threshold': 2.0
            }
        })
        print_success(f"Created portfolio 2 with ID: {portfolio_id_2}")

        # Get portfolio state
        portfolio = get_portfolio_state(portfolio_id_1)
        assert portfolio['name'] == 'Test Momentum Portfolio'
        assert portfolio['initial_balance'] == 10000.00
        assert portfolio['strategy_type'] == 'momentum'
        print_success(f"Retrieved portfolio {portfolio_id_1}: {portfolio['name']}")

        # Get all portfolios
        all_portfolios = get_all_portfolios(status='active')
        assert len(all_portfolios) >= 2
        print_success(f"Retrieved {len(all_portfolios)} active portfolios")

        # Update portfolio
        update_portfolio(portfolio_id_1, {
            'current_balance': 9500.00,
            'total_invested': 500.00,
            'trade_count': 1
        })
        updated = get_portfolio_state(portfolio_id_1)
        assert updated['current_balance'] == 9500.00
        print_success(f"Updated portfolio {portfolio_id_1} balance to ${updated['current_balance']}")

        # ====================================================================
        # TEST 2: Position Operations
        # ====================================================================
        print_test("2. Position Operations")

        # Add position to portfolio 1
        position_1 = {
            'trade_id': 'test_trade_001',
            'market_id': 'test_market_001',
            'market_question': 'Will this test pass?',
            'action': 'buy_yes',
            'amount': 500.00,
            'entry_price': 0.65,
            'entry_timestamp': datetime.now().isoformat(),
            'status': 'open',
            'current_pnl': 0.0
        }
        add_portfolio_position(position_1, portfolio_id=portfolio_id_1)
        print_success(f"Added position to portfolio {portfolio_id_1}: {position_1['trade_id']}")

        # Add position to portfolio 2
        position_2 = {
            'trade_id': 'test_trade_002',
            'market_id': 'test_market_002',
            'market_question': 'Will portfolio isolation work?',
            'action': 'buy_no',
            'amount': 200.00,
            'entry_price': 0.45,
            'entry_timestamp': datetime.now().isoformat(),
            'status': 'open',
            'current_pnl': 0.0
        }
        add_portfolio_position(position_2, portfolio_id=portfolio_id_2)
        print_success(f"Added position to portfolio {portfolio_id_2}: {position_2['trade_id']}")

        # Get positions for portfolio 1
        positions_1 = get_portfolio_positions(portfolio_id=portfolio_id_1, status='open')
        assert len(positions_1) == 1
        assert positions_1[0]['trade_id'] == 'test_trade_001'
        print_success(f"Portfolio {portfolio_id_1} has {len(positions_1)} open position(s)")

        # Get positions for portfolio 2
        positions_2 = get_portfolio_positions(portfolio_id=portfolio_id_2, status='open')
        assert len(positions_2) == 1
        assert positions_2[0]['trade_id'] == 'test_trade_002'
        print_success(f"Portfolio {portfolio_id_2} has {len(positions_2)} open position(s)")

        # Verify isolation
        assert positions_1[0]['trade_id'] != positions_2[0]['trade_id']
        print_success("✓ PORTFOLIO ISOLATION VERIFIED: Each portfolio has separate positions")

        # Update position
        update_portfolio_position('test_trade_001', {
            'current_pnl': 25.50
        }, portfolio_id=portfolio_id_1)
        updated_positions = get_portfolio_positions(portfolio_id=portfolio_id_1, status='open')
        assert updated_positions[0]['current_pnl'] == 25.50
        print_success(f"Updated position PnL to ${updated_positions[0]['current_pnl']}")

        # Close position
        close_portfolio_position('test_trade_001', exit_price=0.70, realized_pnl=25.50, portfolio_id=portfolio_id_1)
        closed_positions = get_portfolio_positions(portfolio_id=portfolio_id_1, status='closed')
        assert len(closed_positions) == 1
        print_success(f"Closed position test_trade_001 with PnL: ${closed_positions[0]['realized_pnl']}")

        # ====================================================================
        # TEST 3: Trade Operations
        # ====================================================================
        print_test("3. Trade Operations")

        # Insert trade for portfolio 1
        trade_1 = {
            'trade_id': 'test_trade_001',
            'timestamp': datetime.now().isoformat(),
            'market_id': 'test_market_001',
            'market_question': 'Will this test pass?',
            'action': 'buy_yes',
            'amount': 500.00,
            'entry_price': 0.65,
            'confidence': 0.80,
            'reason': 'Test trade for portfolio 1',
            'status': 'closed',
            'event_id': 'test_event_001',
            'event_title': 'Test Event 1',
            'event_end_date': '2025-12-31',
            'current_pnl': 25.50,
            'realized_pnl': 25.50
        }
        insert_trade(trade_1, portfolio_id=portfolio_id_1)
        print_success(f"Inserted trade for portfolio {portfolio_id_1}: {trade_1['trade_id']}")

        # Insert trade for portfolio 2
        trade_2 = {
            'trade_id': 'test_trade_002',
            'timestamp': datetime.now().isoformat(),
            'market_id': 'test_market_002',
            'market_question': 'Will portfolio isolation work?',
            'action': 'buy_no',
            'amount': 200.00,
            'entry_price': 0.45,
            'confidence': 0.75,
            'reason': 'Test trade for portfolio 2',
            'status': 'open',
            'event_id': 'test_event_002',
            'event_title': 'Test Event 2',
            'event_end_date': '2025-12-31',
            'current_pnl': 0.0,
            'realized_pnl': None
        }
        insert_trade(trade_2, portfolio_id=portfolio_id_2)
        print_success(f"Inserted trade for portfolio {portfolio_id_2}: {trade_2['trade_id']}")

        # Get trades for portfolio 1
        trades_1 = get_trades(portfolio_id=portfolio_id_1)
        assert len(trades_1) >= 1
        assert trades_1[0]['portfolio_id'] == portfolio_id_1
        print_success(f"Portfolio {portfolio_id_1} has {len(trades_1)} trade(s)")

        # Get trades for portfolio 2
        trades_2 = get_trades(portfolio_id=portfolio_id_2)
        assert len(trades_2) >= 1
        assert trades_2[0]['portfolio_id'] == portfolio_id_2
        print_success(f"Portfolio {portfolio_id_2} has {len(trades_2)} trade(s)")

        # Verify trade isolation
        trade_ids_1 = [t['trade_id'] for t in trades_1]
        trade_ids_2 = [t['trade_id'] for t in trades_2]
        assert 'test_trade_002' not in trade_ids_1
        assert 'test_trade_001' not in trade_ids_2
        print_success("✓ TRADE ISOLATION VERIFIED: Each portfolio has separate trades")

        # Get specific trade
        specific_trade = get_trade_by_id('test_trade_001', portfolio_id=portfolio_id_1)
        assert specific_trade is not None
        assert specific_trade['trade_id'] == 'test_trade_001'
        print_success(f"Retrieved specific trade: {specific_trade['trade_id']}")

        # Update trade status
        update_trade_status('test_trade_002', 'closed', pnl=15.00, portfolio_id=portfolio_id_2)
        updated_trade = get_trade_by_id('test_trade_002', portfolio_id=portfolio_id_2)
        assert updated_trade['status'] == 'closed'
        assert updated_trade['realized_pnl'] == 15.00
        print_success(f"Updated trade status to closed with PnL: ${updated_trade['realized_pnl']}")

        # ====================================================================
        # TEST 4: Signal Operations
        # ====================================================================
        print_test("4. Signal Operations")

        # Insert single signal for portfolio 1
        signal_1 = {
            'strategy_type': 'momentum',
            'timestamp': datetime.now(),
            'market_id': 'test_market_003',
            'market_question': 'Will signals work?',
            'action': 'buy_yes',
            'target_price': 0.72,
            'amount': 300.00,
            'confidence': 0.85,
            'reason': 'Strong momentum detected',
            'yes_price': 0.72,
            'no_price': 0.28,
            'market_liquidity': 50000.00,
            'market_volume': 100000.00,
            'event_id': 'test_event_003',
            'event_title': 'Test Event 3',
            'event_end_date': datetime.now(),
            'executed': False,
            'executed_at': None,
            'trade_id': None
        }
        signal_id_1 = insert_signal(signal_1, portfolio_id=portfolio_id_1)
        print_success(f"Inserted signal for portfolio {portfolio_id_1}: ID {signal_id_1}")

        # Insert multiple signals for portfolio 2
        signals_batch = [
            {
                'strategy_type': 'mean_reversion',
                'timestamp': datetime.now(),
                'market_id': f'test_market_00{i}',
                'market_question': f'Test signal {i}',
                'action': 'buy_no',
                'target_price': 0.35,
                'amount': 150.00,
                'confidence': 0.78,
                'reason': f'Mean reversion signal {i}',
                'yes_price': 0.35,
                'no_price': 0.65,
                'market_liquidity': 30000.00,
                'market_volume': 50000.00,
                'event_id': f'test_event_00{i}',
                'event_title': f'Test Event {i}',
                'event_end_date': datetime.now(),
                'executed': False,
                'executed_at': None,
                'trade_id': None
            }
            for i in range(4, 7)
        ]
        signal_ids = insert_signals(signals_batch, portfolio_id=portfolio_id_2)
        print_success(f"Inserted {len(signal_ids)} signals for portfolio {portfolio_id_2}")

        # Get signals for portfolio 1
        signals_1 = get_current_signals(portfolio_id=portfolio_id_1, executed=False)
        assert len(signals_1) >= 1
        assert all(s['portfolio_id'] == portfolio_id_1 for s in signals_1)
        print_success(f"Portfolio {portfolio_id_1} has {len(signals_1)} unexecuted signal(s)")

        # Get signals for portfolio 2
        signals_2 = get_current_signals(portfolio_id=portfolio_id_2, executed=False)
        assert len(signals_2) >= 3
        assert all(s['portfolio_id'] == portfolio_id_2 for s in signals_2)
        print_success(f"Portfolio {portfolio_id_2} has {len(signals_2)} unexecuted signal(s)")

        # Verify signal isolation
        print_success("✓ SIGNAL ISOLATION VERIFIED: Each portfolio has separate signals")

        # Mark signal as executed
        mark_signal_executed(signal_id_1, 'test_trade_003', portfolio_id=portfolio_id_1)
        executed_signals = get_current_signals(portfolio_id=portfolio_id_1, executed=True)
        assert len(executed_signals) >= 1
        print_success(f"Marked signal {signal_id_1} as executed")

        # ====================================================================
        # TEST 5: Portfolio History Operations
        # ====================================================================
        print_test("5. Portfolio History Operations")

        # Create history snapshot for portfolio 1
        snapshot_1 = {
            'snapshot_date': datetime.now().date(),
            'timestamp': datetime.now(),
            'balance': 9500.00,
            'total_invested': 500.00,
            'total_profit_loss': 25.50,
            'total_value': 9525.50,
            'open_positions': 0,
            'trade_count': 1
        }
        snapshot_id_1 = insert_portfolio_history_snapshot(snapshot_1, portfolio_id=portfolio_id_1)
        print_success(f"Created history snapshot for portfolio {portfolio_id_1}: ID {snapshot_id_1}")

        # Create history snapshot for portfolio 2
        snapshot_2 = {
            'snapshot_date': datetime.now().date(),
            'timestamp': datetime.now(),
            'balance': 4800.00,
            'total_invested': 200.00,
            'total_profit_loss': 15.00,
            'total_value': 4815.00,
            'open_positions': 0,
            'trade_count': 1
        }
        snapshot_id_2 = insert_portfolio_history_snapshot(snapshot_2, portfolio_id=portfolio_id_2)
        print_success(f"Created history snapshot for portfolio {portfolio_id_2}: ID {snapshot_id_2}")

        # Get history for portfolio 1
        history_1 = get_portfolio_history(portfolio_id=portfolio_id_1, limit=10)
        assert len(history_1) >= 1
        assert all(h['portfolio_id'] == portfolio_id_1 for h in history_1)
        print_success(f"Portfolio {portfolio_id_1} has {len(history_1)} history snapshot(s)")

        # Get history for portfolio 2
        history_2 = get_portfolio_history(portfolio_id=portfolio_id_2, limit=10)
        assert len(history_2) >= 1
        assert all(h['portfolio_id'] == portfolio_id_2 for h in history_2)
        print_success(f"Portfolio {portfolio_id_2} has {len(history_2)} history snapshot(s)")

        # Verify history isolation
        print_success("✓ HISTORY ISOLATION VERIFIED: Each portfolio has separate history")

        # ====================================================================
        # FINAL SUMMARY
        # ====================================================================
        print("\n" + "="*60)
        print("TEST SUITE COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\n✓ All portfolio management functions working")
        print("✓ All position operations working")
        print("✓ All trade operations working")
        print("✓ All signal operations working")
        print("✓ All history operations working")
        print("✓ Portfolio isolation verified across all tables")
        print("\n" + "="*60)
        print("MIGRATION STATUS: Phase 2 Step 4 & 5 COMPLETE")
        print("="*60)
        print(f"\nTest Portfolios Created:")
        print(f"  - Portfolio {portfolio_id_1}: {portfolio['name']}")
        print(f"  - Portfolio {portfolio_id_2}: Test Mean Reversion Portfolio")
        print("\nYou can now proceed to Phase 3: Controller Updates")
        print("="*60 + "\n")

    except Exception as e:
        print_error(f"TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
