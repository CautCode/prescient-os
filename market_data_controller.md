# Market Data Controller - Key Questions Framework

This document defines the critical questions our market data controller must answer to identify viable trading opportunities on Polymarket. These questions will guide the development of our API wrappers and analysis tools.

## Core Market Viability Questions

### 1. Market Liquidity & Volume
**Why Important**: Ensures we can enter/exit positions without significant slippage
- What is the total volume traded in this market over the last 24h/7d/30d?
- What is the current bid-ask spread?
- How many unique traders are active in this market?
- What is the market depth at different price levels?
- Is there sufficient liquidity for our intended position size?

### 2. Market Timing & Resolution
**Why Important**: Determines holding period and capital efficiency
- When does this market resolve?
- How much time remains until resolution?
- Is the resolution date fixed or dependent on events?
- What is the optimal entry/exit timing window?
- Are there any upcoming catalysts that could move prices?

### 3. Market Efficiency & Mispricing Opportunities
**Why Important**: Identifies profit potential
- How efficiently is this market pricing the underlying probability?
- Are there discrepancies between market price and external probability sources?
- What is the historical accuracy of similar markets?
- Are there arbitrage opportunities between related markets?
- How quickly does the market react to new information?

### 4. Risk Assessment
**Why Important**: Protects capital and manages downside
- What is the maximum potential loss on this trade?
- How volatile has this market been historically?
- Are there any binary risk events that could cause sudden price movements?
- What external factors could invalidate our thesis?
- Is this market subject to manipulation or insider information?

### 5. Market Mechanics & Structure
**Why Important**: Understanding trading costs and mechanics
- What are the trading fees for this market?
- Are there any withdrawal restrictions or delays?
- How is the market maker providing liquidity?
- What is the minimum position size?
- Are there any technical issues with the market?

## Market Categorization Questions

### 6. Event Type Analysis
**Why Important**: Different event types have different predictability patterns
- Is this a political, sports, economic, or other type of event?
- How predictable are similar events historically?
- What data sources are available to inform our prediction?
- Are there established forecasting models for this event type?

### 7. Information Edge Assessment
**Why Important**: Determines if we have an advantage over other traders
- Do we have access to unique data or analysis methods?
- How much public information is already priced in?
- Are there expert opinions or prediction models we can leverage?
- Can we aggregate multiple data sources for better predictions?

### 8. Correlation & Portfolio Impact
**Why Important**: Portfolio diversification and risk management
- How correlated is this market with our existing positions?
- Does this market hedge or amplify our current exposure?
- What is the impact on our overall portfolio risk?
- Are there related markets we should consider simultaneously?

## Technical Implementation Questions

### 9. Data Quality & Availability
**Why Important**: Ensures reliable decision-making
- Is real-time market data available and reliable?
- How frequently is pricing data updated?
- Are there historical data gaps that could affect backtesting?
- What is the quality of order book data?

### 10. Execution Feasibility
**Why Important**: Determines if we can actually implement our strategy
- Can we automate trading for this market type?
- Are there API rate limits that would affect our strategy?
- How quickly can we execute trades when opportunities arise?
- Are there any regulatory restrictions on this market?

## Scoring Framework

Each question category should be assigned a weight and scoring criteria:

### High Priority (Critical for Trade Execution)
- Market Liquidity & Volume (25%)
- Risk Assessment (20%)
- Market Timing & Resolution (15%)

### Medium Priority (Important for Profitability)
- Market Efficiency & Mispricing (15%)
- Information Edge Assessment (10%)
- Event Type Analysis (10%)

### Supporting Factors (Optimization)
- Market Mechanics & Structure (3%)
- Correlation & Portfolio Impact (1%)
- Data Quality & Availability (1%)

## Market Scoring System (0-10 Scale)

### Core Scoring Factors

#### 1. Liquidity Score (0-10)
**Data Required**: Volume (24h/7d), bid-ask spread, unique traders, order book depth
- **10**: High volume (>$10k daily), tight spread (<2%), many traders (>100), deep order book
- **8-9**: Good volume ($5-10k daily), reasonable spread (2-4%), decent traders (50-100)
- **6-7**: Moderate volume ($1-5k daily), wider spread (4-8%), fewer traders (20-50)
- **4-5**: Low volume ($500-1k daily), large spread (8-15%), limited traders (10-20)
- **0-3**: Very low volume (<$500 daily), huge spread (>15%), few traders (<10)

#### 2. Time Value Score (0-10)
**Data Required**: Resolution date, current date, market price
- **Formula**: `score = min(10, (days_to_resolution / target_days) * price_efficiency_multiplier)`
- **Tunable Parameters**:
  - `target_days`: Preferred holding period (default: 30 days)
  - `short_term_bonus`: Extra points for quick opportunities (0-2 points)
  - `long_term_penalty`: Reduced score for very long-term markets

#### 3. Risk Score (0-10)
**Data Required**: Price volatility, market type, time to resolution
- **10**: Low volatility, clear resolution criteria, stable market
- **8-9**: Moderate volatility, well-defined outcome
- **6-7**: Higher volatility but manageable risk
- **4-5**: High volatility, some uncertainty in resolution
- **0-3**: Extreme volatility, unclear resolution, manipulation risk

#### 4. Opportunity Score (0-10)
**Data Required**: Current price, implied probability vs logical probability
- **10**: Clear mispricing opportunity (>20% edge)
- **8-9**: Good edge (10-20%)
- **6-7**: Decent edge (5-10%)
- **4-5**: Small edge (2-5%)
- **0-3**: No clear edge or overpriced

#### 5. Market Quality Score (0-10)
**Data Required**: Market age, number of trades, price stability
- **10**: Mature market, many trades, stable pricing
- **8-9**: Established market with good activity
- **6-7**: Moderate activity and stability
- **4-5**: New or unstable market
- **0-3**: Very new, untested, or problematic market

### Composite Scoring Function

```python
def calculate_market_score(market_data, strategy_params):
    """
    Calculate market attractiveness score based on strategy parameters
    
    Args:
        market_data: Dict containing market information
        strategy_params: Dict containing strategy preferences
    
    Returns:
        Dict with overall score and component scores
    """
    
    # Base component scores (0-10 each)
    liquidity_score = calculate_liquidity_score(market_data)
    time_score = calculate_time_score(market_data, strategy_params)
    risk_score = calculate_risk_score(market_data, strategy_params)
    opportunity_score = calculate_opportunity_score(market_data)
    quality_score = calculate_quality_score(market_data)
    
    # Strategy-based weights (sum to 1.0)
    weights = {
        'liquidity': strategy_params.get('liquidity_weight', 0.25),
        'time': strategy_params.get('time_weight', 0.20),
        'risk': strategy_params.get('risk_weight', 0.20),
        'opportunity': strategy_params.get('opportunity_weight', 0.25),
        'quality': strategy_params.get('quality_weight', 0.10)
    }
    
    # Calculate weighted score
    overall_score = (
        liquidity_score * weights['liquidity'] +
        time_score * weights['time'] +
        risk_score * weights['risk'] +
        opportunity_score * weights['opportunity'] +
        quality_score * weights['quality']
    )
    
    return {
        'overall_score': round(overall_score, 2),
        'liquidity_score': liquidity_score,
        'time_score': time_score,
        'risk_score': risk_score,
        'opportunity_score': opportunity_score,
        'quality_score': quality_score
    }
```

### Strategy Profiles

#### High Risk, Short Term
```python
short_term_strategy = {
    'liquidity_weight': 0.35,    # Need high liquidity for quick trades
    'time_weight': 0.30,         # Time is critical
    'risk_weight': 0.10,         # Accept higher risk
    'opportunity_weight': 0.20,   # Good edge needed
    'quality_weight': 0.05,      # Less concerned with market maturity
    'target_days': 7,            # Looking for week-long trades
    'min_liquidity_score': 6,    # Hard filter
    'min_overall_score': 7       # High bar for entry
}
```

#### Conservative, Long Term
```python
long_term_strategy = {
    'liquidity_weight': 0.15,    # Less concerned with immediate liquidity
    'time_weight': 0.15,         # Time less critical
    'risk_weight': 0.35,         # Risk is primary concern
    'opportunity_weight': 0.25,   # Need good edge for patience
    'quality_weight': 0.10,      # Want established markets
    'target_days': 90,           # Looking for 3-month holds
    'min_risk_score': 7,         # Hard filter
    'min_overall_score': 6.5     # More lenient entry
}
```

#### Balanced Approach
```python
balanced_strategy = {
    'liquidity_weight': 0.25,
    'time_weight': 0.20,
    'risk_weight': 0.20,
    'opportunity_weight': 0.25,
    'quality_weight': 0.10,
    'target_days': 30,
    'min_liquidity_score': 5,
    'min_overall_score': 6
}
```

### Market Filtering System

#### Hard Filters (Eliminate Before Scoring)
```python
def apply_hard_filters(markets, strategy_params):
    """Remove markets that don't meet minimum criteria"""
    filtered = []
    
    for market in markets:
        # Minimum liquidity check
        if market['volume_24h'] < strategy_params.get('min_volume', 100):
            continue
            
        # Time horizon check
        days_to_resolution = (market['end_date'] - datetime.now()).days
        min_days = strategy_params.get('min_days_to_resolution', 1)
        max_days = strategy_params.get('max_days_to_resolution', 365)
        
        if not (min_days <= days_to_resolution <= max_days):
            continue
            
        # Market status check
        if market.get('closed', True):
            continue
            
        # Minimum price check (avoid extreme odds)
        prices = [market.get('yes_price', 0), market.get('no_price', 0)]
        if any(p < 0.05 or p > 0.95 for p in prices):
            continue
            
        filtered.append(market)
    
    return filtered
```

### Usage Examples

```python
# Get top high-risk, short-term opportunities
top_risky_short = get_top_markets(
    strategy=short_term_strategy,
    limit=10,
    sort_by='overall_score'
)

# Get best long-term conservative plays
top_conservative = get_top_markets(
    strategy=long_term_strategy,
    limit=5,
    min_score=7.0
)

# Find markets expiring soon with high liquidity
expiring_soon = get_top_markets(
    strategy={
        'max_days_to_resolution': 14,
        'min_liquidity_score': 8,
        'liquidity_weight': 0.4,
        'time_weight': 0.3,
        'opportunity_weight': 0.3
    }
)
```

## Implementation Goals

The market data controller should:

1. **Systematic Market Collection**: Fetch all active events/markets from Polymarket
2. **Configurable Scoring**: Score markets 0-10 based on tunable strategy parameters
3. **Multi-Strategy Support**: Support different risk/time/liquidity preferences
4. **Dynamic Filtering**: Apply hard filters before scoring to eliminate unsuitable markets
5. **Ranking & Selection**: Return top N markets based on composite scores
6. **Performance Tracking**: Monitor how well scored markets actually perform

## Next Steps

1. Build API wrappers to collect required market data
2. Implement the scoring functions for each component
3. Create strategy profile system with tunable parameters
4. Build market filtering and ranking pipeline
5. Add backtesting to validate scoring accuracy
6. Create dashboard to visualize top-ranked markets

---

*This scoring system is designed to be tunable and adaptable as we learn what factors actually predict profitable trades.*