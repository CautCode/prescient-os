# Prescient OS - Polymarket Trading Bot

An iterative approach to building an AI-powered trading bot for Polymarket prediction markets.

## Project Overview

This project aims to create an intelligent trading system that can:
1. Analyze market data from Polymarket
2. Identify profitable trading opportunities
3. Execute trades based on data-driven insights
4. Continuously learn and adapt trading strategies

## Development Approach

We're building this bot iteratively, starting with data collection and analysis before moving to trading execution:

### Phase 1: Market Data Collection & Analysis ⏳
- Implement market data controller to fetch and analyze Polymarket data
- Define key questions that determine market viability for trading
- Build wrappers around Polymarket API endpoints
- Create data analysis tools to identify patterns and opportunities

### Phase 2: Market Selection Algorithm (Planned)
- Develop scoring system for market attractiveness
- Implement filters for market liquidity, volatility, and time horizons
- Create risk assessment metrics

### Phase 3: Trading Strategy Development (Planned)
- Design trading algorithms based on market analysis
- Implement position sizing and risk management
- Create backtesting framework

### Phase 4: Live Trading (Planned)
- Integrate with Polymarket trading APIs
- Implement real-time monitoring and alerts
- Add performance tracking and optimization

## Current Status

**Phase 1 - Market Data Collection**
- ✅ Created Jupyter notebook for testing Polymarket Events API
- 🔄 Defining market data controller requirements
- ⏳ Building API wrappers and data analysis tools

## Project Structure

```
prescient-os/
├── src/
│   ├── polymarket_events_test.ipynb    # API testing notebook
│   └── market_data_controller.md       # Market analysis requirements
├── logs/                               # Application logs
├── venv/                              # Python virtual environment
└── README.md                         # This file
```

## Getting Started

1. **Environment Setup**
   ```bash
   # Activate virtual environment
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   
   # Install dependencies
   pip install requests pandas jupyter numpy
   ```

2. **Test API Connection**
   ```bash
   jupyter notebook src/polymarket_events_test.ipynb
   ```

3. **Review Market Analysis Framework**
   See `src/market_data_controller.md` for the key questions our system needs to answer.

## API Documentation

- [Polymarket API Reference](https://docs.polymarket.com/api-reference)
- [Events Endpoint](https://docs.polymarket.com/api-reference/events/list-events)

## Contributing

This is an iterative development project. Each phase builds upon the previous one, ensuring we have solid foundations before adding complexity.

## Disclaimer

This is a research and educational project. Always understand the risks involved in prediction market trading and never invest more than you can afford to lose.