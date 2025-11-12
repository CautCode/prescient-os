"""
Strategy Controllers Package

This package contains all trading strategy controllers for Prescient OS.
Each strategy controller is responsible for:
- Defining its own filtering parameters
- Filtering events and markets with strategy-specific criteria
- Generating trading signals using strategy-specific logic
- Saving signals to the database

Available Strategies:
- momentum: Buy markets with >50% probability on most likely outcome
"""

__version__ = "1.0.0"
