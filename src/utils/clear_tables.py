#!/usr/bin/env python3
"""
Utility script to delete all data from tables.
This script will permanently delete all data but keep table structures.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from db.connection import engine, get_db, logger
from sqlalchemy import text

def clear_all_tables():
    """Delete all data from tables in the correct order to respect foreign key constraints"""
    if engine is None:
        logger.error("Database not configured. Cannot clear tables.")
        return False
    
    # List of tables to clear in correct order (child tables first)
    tables_to_clear = [
        'trading_signals',
        'signal_archives', 
        'market_snapshots',
        'markets',
        'events',
        'portfolio_snapshots',
        'portfolio_positions',
        'portfolio_history',
        'portfolio_state',
        'system_metadata',
        'trades'
    ]
    
    try:
        with get_db() as db:
            # Delete data from each table in correct order
            for table in tables_to_clear:
                try:
                    db.execute(text(f"DELETE FROM {table};"))
                    logger.info(f"Cleared data from table: {table}")
                except Exception as e:
                    logger.warning(f"Failed to clear table {table}: {e}")
            
            logger.info("All tables cleared successfully")
            return True
            
    except Exception as e:
        logger.error(f"Error clearing tables: {e}")
        return False

if __name__ == "__main__":
    print("WARNING: This will permanently delete ALL data from the database tables.")
    confirm = input("Are you sure you want to continue? (type 'yes' to confirm): ")
    
    if confirm.lower() == 'yes':
        success = clear_all_tables()
        if success:
            print("✅ All tables cleared successfully")
        else:
            print("❌ Failed to clear tables")
            sys.exit(1)
    else:
        print("Operation cancelled")