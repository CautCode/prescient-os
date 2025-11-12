"""
Phase 1 Verification Script

This script verifies that all Phase 1 components are working correctly:
1. Strategy directory structure exists
2. Base strategy class can be imported
3. Momentum strategy controller can be imported and tested
4. Database operations updated correctly
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def print_success(message):
    print(f"[PASS] {message}")

def print_error(message):
    print(f"[FAIL] {message}")
    sys.exit(1)

def verify_file_structure():
    """Verify that all required files were created"""
    print("\n=== Verifying File Structure ===")

    required_files = [
        "src/strategies/__init__.py",
        "src/strategies/base_strategy.py",
        "src/strategies/momentum_strategy_controller.py"
    ]

    for file_path in required_files:
        if os.path.exists(file_path):
            print_success(f"File exists: {file_path}")
        else:
            print_error(f"File missing: {file_path}")

def verify_imports():
    """Verify that all modules can be imported"""
    print("\n=== Verifying Imports ===")

    try:
        from src.strategies import base_strategy
        print_success("base_strategy module imports successfully")
    except Exception as e:
        print_error(f"Failed to import base_strategy: {e}")

    try:
        from src.strategies import momentum_strategy_controller
        print_success("momentum_strategy_controller module imports successfully")
    except Exception as e:
        print_error(f"Failed to import momentum_strategy_controller: {e}")

def verify_base_strategy():
    """Verify base strategy class"""
    print("\n=== Verifying Base Strategy ===")

    from src.strategies.base_strategy import BaseStrategyController

    # Check that it's abstract
    try:
        BaseStrategyController()
        print_error("BaseStrategyController should be abstract")
    except TypeError:
        print_success("BaseStrategyController is properly abstract")

    # Check methods exist
    required_methods = [
        'export_events',
        'filter_events',
        'filter_markets',
        '_extract_event_filters',
        '_extract_market_filters',
        'merge_with_defaults',
        'prepare_signals_for_db'
    ]

    for method in required_methods:
        if hasattr(BaseStrategyController, method):
            print_success(f"Method exists: {method}")
        else:
            print_error(f"Method missing: {method}")

def verify_momentum_strategy():
    """Verify momentum strategy controller"""
    print("\n=== Verifying Momentum Strategy ===")

    from src.strategies.momentum_strategy_controller import (
        STRATEGY_INFO,
        generate_momentum_signals,
        prepare_signals_for_db
    )

    # Check STRATEGY_INFO
    required_keys = ['name', 'description', 'strategy_type', 'default_config']
    for key in required_keys:
        if key in STRATEGY_INFO:
            print_success(f"STRATEGY_INFO has '{key}': {STRATEGY_INFO.get(key, '')[:50] if isinstance(STRATEGY_INFO.get(key), str) else '...'}")
        else:
            print_error(f"STRATEGY_INFO missing '{key}'")

    # Test signal generation with mock data
    mock_markets = [
        {
            'id': 'test_market',
            'question': 'Test question?',
            'yes_price': 0.75,
            'no_price': 0.25,
            'liquidity': 10000,
            'volume': 50000,
            'event_id': 'test_event',
            'event_title': 'Test Event',
            'event_end_date': '2025-01-15'
        }
    ]

    signals = generate_momentum_signals(
        mock_markets,
        min_confidence=0.75,
        max_positions=10,
        trade_amount=100
    )

    if len(signals) == 1:
        print_success(f"Signal generation works: generated {len(signals)} signal(s)")
    else:
        print_error(f"Signal generation failed: expected 1 signal, got {len(signals)}")

    # Verify signal structure
    if signals:
        required_signal_keys = [
            'timestamp', 'market_id', 'market_question', 'action',
            'target_price', 'amount', 'confidence', 'reason'
        ]
        signal = signals[0]
        for key in required_signal_keys:
            if key in signal:
                print_success(f"Signal has '{key}'")
            else:
                print_error(f"Signal missing '{key}'")

def verify_database_operations():
    """Verify database operations updated"""
    print("\n=== Verifying Database Operations ===")

    from src.db.operations import insert_signals
    import inspect

    # Check function signature
    sig = inspect.signature(insert_signals)
    params = list(sig.parameters.keys())

    if 'strategy_type' in params:
        print_success("insert_signals has 'strategy_type' parameter")
    else:
        print_error("insert_signals missing 'strategy_type' parameter")

    print_success(f"Function signature: {sig}")

def verify_endpoints():
    """Verify FastAPI endpoints exist"""
    print("\n=== Verifying FastAPI Endpoints ===")

    from src.strategies.momentum_strategy_controller import app

    # Get all routes
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append((route.path, list(route.methods)))

    required_endpoints = [
        ('/', ['GET']),
        ('/strategy/execute-full-cycle', ['POST']),
        ('/strategy/info', ['GET']),
        ('/strategy/validate-config', ['POST']),
        ('/strategy/status', ['GET'])
    ]

    for path, methods in required_endpoints:
        found = any(r[0] == path and set(methods).issubset(set(r[1])) for r in routes)
        if found:
            print_success(f"Endpoint exists: {methods[0]} {path}")
        else:
            print_error(f"Endpoint missing: {methods[0]} {path}")

def main():
    print("=" * 60)
    print("Phase 1 Verification")
    print("=" * 60)

    try:
        verify_file_structure()
        verify_imports()
        verify_base_strategy()
        verify_momentum_strategy()
        verify_database_operations()
        verify_endpoints()

        print("\n" + "=" * 60)
        print("[SUCCESS] ALL PHASE 1 VERIFICATIONS PASSED")
        print("=" * 60)
        print("\nReady to proceed to Phase 2!")

    except SystemExit:
        print("\n" + "=" * 60)
        print("[ERROR] PHASE 1 VERIFICATION FAILED")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
