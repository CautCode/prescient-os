-- ============================================================================
-- PRESCIENT OS - PORTFOLIO-CENTRIC ARCHITECTURE SCHEMA v2
-- ============================================================================
-- This schema supports multiple independent portfolios with separate:
-- - Capital allocation and balances
-- - Trading positions and P&L tracking
-- - Strategy configurations
-- - Historical performance tracking
--
-- Migration Strategy: Drop and rebuild (no data migration)
-- Old schema preserved in git history
-- ============================================================================

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PORTFOLIOS TABLE (replaces portfolio_state)
-- ----------------------------------------------------------------------------
-- Central table for managing multiple independent portfolios
-- Each portfolio has its own balance, strategy, and configuration

CREATE TABLE portfolios (
    portfolio_id SERIAL PRIMARY KEY,

    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(100) NOT NULL,  -- 'momentum', 'mean_reversion', 'arbitrage', 'hybrid', etc.

    -- Financial State
    initial_balance DECIMAL(15, 2) NOT NULL,
    current_balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) DEFAULT 0,
    total_profit_loss DECIMAL(15, 2) DEFAULT 0,
    trade_count INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'paused', 'archived'
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),

    -- Strategy Configuration (flexible JSONB for strategy-specific params)
    strategy_config JSONB DEFAULT '{}'::jsonb,

    -- Performance Tracking (denormalized for fast queries)
    total_trades_executed INTEGER DEFAULT 0,
    total_winning_trades INTEGER DEFAULT 0,
    total_losing_trades INTEGER DEFAULT 0,
    avg_trade_pnl DECIMAL(15, 2) DEFAULT 0,
    max_drawdown DECIMAL(15, 2) DEFAULT 0,

    -- Metadata
    last_trade_at TIMESTAMP,
    last_price_update TIMESTAMP,

    UNIQUE(name)
);

-- Indexes for performance
CREATE INDEX idx_portfolios_status ON portfolios(status);
CREATE INDEX idx_portfolios_strategy_type ON portfolios(strategy_type);
CREATE INDEX idx_portfolios_status_strategy ON portfolios(status, strategy_type);

-- ----------------------------------------------------------------------------
-- PORTFOLIO POSITIONS TABLE
-- ----------------------------------------------------------------------------
-- Tracks all positions for each portfolio with full isolation

CREATE TABLE portfolio_positions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    trade_id VARCHAR(255) NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT,
    action VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 4) NOT NULL,
    entry_timestamp TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL,
    current_pnl DECIMAL(15, 2) DEFAULT 0,
    realized_pnl DECIMAL(15, 2),
    exit_price DECIMAL(10, 4),
    exit_timestamp TIMESTAMP,

    -- Foreign key constraint with CASCADE delete
    CONSTRAINT fk_portfolio_positions_portfolio
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
        ON DELETE CASCADE
);

-- Indexes for efficient portfolio-filtered queries
CREATE INDEX idx_portfolio_positions_portfolio_id ON portfolio_positions(portfolio_id);
CREATE INDEX idx_portfolio_positions_portfolio_status ON portfolio_positions(portfolio_id, status);
CREATE INDEX idx_portfolio_positions_portfolio_market ON portfolio_positions(portfolio_id, market_id);

-- ----------------------------------------------------------------------------
-- TRADES TABLE
-- ----------------------------------------------------------------------------
-- Records all trades executed for each portfolio

CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    trade_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT,
    action VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 4) NOT NULL,
    confidence DECIMAL(5, 4),
    reason TEXT,
    status VARCHAR(50) NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    current_pnl DECIMAL(15, 2) DEFAULT 0,
    realized_pnl DECIMAL(15, 2),

    -- Foreign key constraint with CASCADE delete
    CONSTRAINT fk_trades_portfolio
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
        ON DELETE CASCADE
);

-- Indexes for efficient trade queries by portfolio
CREATE INDEX idx_trades_portfolio_id ON trades(portfolio_id);
CREATE INDEX idx_trades_portfolio_timestamp ON trades(portfolio_id, timestamp);
CREATE INDEX idx_trades_portfolio_status ON trades(portfolio_id, status);

-- ----------------------------------------------------------------------------
-- TRADING SIGNALS TABLE
-- ----------------------------------------------------------------------------
-- Stores trading signals generated for each portfolio

CREATE TABLE trading_signals (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    strategy_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT,
    action VARCHAR(50) NOT NULL,
    target_price DECIMAL(10, 4),
    amount DECIMAL(15, 2),
    confidence DECIMAL(5, 4),
    reason TEXT,
    yes_price DECIMAL(10, 4),
    no_price DECIMAL(10, 4),
    market_liquidity DECIMAL(15, 2),
    market_volume DECIMAL(15, 2),
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    trade_id VARCHAR(255),

    -- Foreign key constraint with CASCADE delete
    CONSTRAINT fk_trading_signals_portfolio
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
        ON DELETE CASCADE
);

-- Indexes for signal processing and portfolio filtering
CREATE INDEX idx_trading_signals_portfolio ON trading_signals(portfolio_id);
CREATE INDEX idx_trading_signals_portfolio_executed ON trading_signals(portfolio_id, executed);
CREATE INDEX idx_trading_signals_strategy ON trading_signals(strategy_type);

-- ----------------------------------------------------------------------------
-- PORTFOLIO HISTORY TABLE
-- ----------------------------------------------------------------------------
-- Daily snapshots of portfolio state for performance tracking

CREATE TABLE portfolio_history (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    open_positions INTEGER DEFAULT 0,
    trade_count INTEGER DEFAULT 0,

    -- Foreign key constraint with CASCADE delete
    CONSTRAINT fk_portfolio_history_portfolio
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
        ON DELETE CASCADE,

    -- Unique constraint to prevent duplicate snapshots
    UNIQUE(portfolio_id, snapshot_date)
);

-- Indexes for historical queries
CREATE INDEX idx_portfolio_history_portfolio_date ON portfolio_history(portfolio_id, snapshot_date);
CREATE INDEX idx_portfolio_history_portfolio_timestamp ON portfolio_history(portfolio_id, timestamp);

-- ============================================================================
-- SHARED TABLES (not portfolio-specific)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- EVENTS TABLE
-- ----------------------------------------------------------------------------
-- Stores Polymarket events (shared across all portfolios)

CREATE TABLE events (
    id VARCHAR(255) PRIMARY KEY,
    title TEXT,
    description TEXT,
    slug VARCHAR(255),
    end_date TIMESTAMP,
    active BOOLEAN,
    closed BOOLEAN,
    archived BOOLEAN,
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    markets_count INTEGER,
    is_filtered BOOLEAN DEFAULT FALSE,
    filter_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_events_active ON events(active);
CREATE INDEX idx_events_end_date ON events(end_date);
CREATE INDEX idx_events_is_filtered ON events(is_filtered);
CREATE INDEX idx_events_liquidity ON events(liquidity);
CREATE INDEX idx_events_volume ON events(volume);

-- ----------------------------------------------------------------------------
-- MARKETS TABLE
-- ----------------------------------------------------------------------------
-- Stores Polymarket markets (shared across all portfolios)

CREATE TABLE markets (
    id VARCHAR(255) PRIMARY KEY,
    question TEXT,
    event_id VARCHAR(255),
    event_title TEXT,
    description TEXT,
    end_date TIMESTAMP,
    yes_price DECIMAL(10, 4),
    no_price DECIMAL(10, 4),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    active BOOLEAN,
    closed BOOLEAN,
    market_conviction DECIMAL(5, 4),
    is_filtered BOOLEAN DEFAULT FALSE,
    filter_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_markets_active ON markets(active);
CREATE INDEX idx_markets_event_id ON markets(event_id);
CREATE INDEX idx_markets_end_date ON markets(end_date);
CREATE INDEX idx_markets_is_filtered ON markets(is_filtered);
CREATE INDEX idx_markets_liquidity ON markets(liquidity);
CREATE INDEX idx_markets_volume ON markets(volume);

-- ----------------------------------------------------------------------------
-- MARKET SNAPSHOTS TABLE
-- ----------------------------------------------------------------------------
-- Historical price data for markets (shared across portfolios)

CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    yes_price DECIMAL(10, 4),
    no_price DECIMAL(10, 4),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    market_conviction DECIMAL(5, 4)
);

CREATE INDEX idx_market_snapshots_market_id ON market_snapshots(market_id);
CREATE INDEX idx_market_snapshots_timestamp ON market_snapshots(timestamp);
CREATE INDEX idx_market_snapshots_market_timestamp ON market_snapshots(market_id, timestamp);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Portfolio Summary View
-- ----------------------------------------------------------------------------
-- Aggregated portfolio statistics for quick dashboard queries

CREATE VIEW portfolio_summary AS
SELECT
    p.portfolio_id,
    p.name,
    p.strategy_type,
    p.status,
    p.current_balance,
    p.total_invested,
    p.total_profit_loss,
    (p.current_balance + p.total_profit_loss) AS total_value,
    p.trade_count,
    p.created_at,
    p.last_updated,
    p.last_trade_at,
    COUNT(DISTINCT pos.id) FILTER (WHERE pos.status = 'open') AS open_positions_count,
    COALESCE(SUM(pos.current_pnl) FILTER (WHERE pos.status = 'open'), 0) AS unrealized_pnl,
    CASE
        WHEN p.total_trades_executed > 0
        THEN ROUND((p.total_winning_trades::DECIMAL / p.total_trades_executed) * 100, 2)
        ELSE 0
    END AS win_rate_pct,
    CASE
        WHEN p.initial_balance > 0
        THEN ROUND(((p.current_balance + p.total_profit_loss - p.initial_balance) / p.initial_balance) * 100, 2)
        ELSE 0
    END AS total_return_pct
FROM portfolios p
LEFT JOIN portfolio_positions pos ON p.portfolio_id = pos.portfolio_id
GROUP BY p.portfolio_id, p.name, p.strategy_type, p.status, p.current_balance,
         p.total_invested, p.total_profit_loss, p.trade_count, p.created_at,
         p.last_updated, p.last_trade_at, p.total_trades_executed, p.total_winning_trades, p.initial_balance;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE portfolios IS 'Core table managing multiple independent trading portfolios';
COMMENT ON TABLE portfolio_positions IS 'Positions for each portfolio with full isolation';
COMMENT ON TABLE trades IS 'All trades executed by each portfolio';
COMMENT ON TABLE trading_signals IS 'Trading signals generated for each portfolio by strategy controllers';
COMMENT ON TABLE portfolio_history IS 'Daily snapshots of portfolio state for performance tracking';

COMMENT ON COLUMN portfolios.strategy_type IS 'Strategy type: momentum, mean_reversion, arbitrage, hybrid, etc.';
COMMENT ON COLUMN portfolios.strategy_config IS 'JSONB field for flexible strategy-specific parameters';
COMMENT ON COLUMN portfolios.status IS 'Portfolio status: active, paused, or archived';

-- ============================================================================
-- SCHEMA VERSION
-- ============================================================================

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_version (version, description) VALUES
(2, 'Portfolio-centric architecture with multiple portfolio support');

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
