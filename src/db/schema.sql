-- Portfolio Management
CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_snapshots_timestamp ON portfolio_snapshots(timestamp DESC);

-- Current portfolio state (single row, updated)
CREATE TABLE portfolio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    CONSTRAINT single_portfolio CHECK (id = 1)
);

-- Portfolio positions (open trades)
CREATE TABLE portfolio_positions (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL, -- 'buy_yes' or 'buy_no'
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    entry_timestamp TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'open', 'closed'
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    exit_price DECIMAL(10, 6),
    exit_timestamp TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_positions_market_id ON portfolio_positions(market_id);
CREATE INDEX idx_positions_status ON portfolio_positions(status);

-- Trade History (append-only)
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    status VARCHAR(50) NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_market_id ON trades(market_id);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_status ON trades(status);

-- Trading Signals
CREATE TABLE trading_signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    target_price DECIMAL(10, 6) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    yes_price DECIMAL(10, 6) NOT NULL,
    no_price DECIMAL(10, 6) NOT NULL,
    market_liquidity DECIMAL(15, 2),
    market_volume DECIMAL(15, 2),
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    trade_id VARCHAR(255) REFERENCES trades(trade_id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_market_id ON trading_signals(market_id);
CREATE INDEX idx_signals_timestamp ON trading_signals(timestamp DESC);
CREATE INDEX idx_signals_executed ON trading_signals(executed);

-- Signal Archives (monthly archives)
CREATE TABLE signal_archives (
    id SERIAL PRIMARY KEY,
    archived_at TIMESTAMP NOT NULL,
    archive_month VARCHAR(7) NOT NULL, -- 'YYYY-MM'
    signals_count INTEGER NOT NULL,
    signals_data JSONB NOT NULL, -- Store full signals array
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_archives_month ON signal_archives(archive_month);

-- Events (filtered events)
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    slug VARCHAR(500),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    days_until_end INTEGER,
    event_data JSONB NOT NULL, -- Store full event JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_event_id ON events(event_id);
CREATE INDEX idx_events_liquidity ON events(liquidity);
CREATE INDEX idx_events_volume ON events(volume);
CREATE INDEX idx_events_end_date ON events(end_date);

-- Markets (filtered markets)
CREATE TABLE markets (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) UNIQUE NOT NULL,
    question TEXT NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    market_conviction DECIMAL(10, 6),
    market_data JSONB NOT NULL, -- Store full market JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_markets_market_id ON markets(market_id);
CREATE INDEX idx_markets_event_id ON markets(event_id);
CREATE INDEX idx_markets_liquidity ON markets(liquidity);
CREATE INDEX idx_markets_volume ON markets(volume);

-- Market Snapshots (time-series market data)
CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    market_conviction DECIMAL(10, 6),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_snapshots_market_id ON market_snapshots(market_id);
CREATE INDEX idx_market_snapshots_timestamp ON market_snapshots(timestamp DESC);

-- Portfolio History (daily snapshots)
CREATE TABLE portfolio_history (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    open_positions INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_history_date ON portfolio_history(snapshot_date DESC);

-- System Metadata
CREATE TABLE system_metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Insert initial metadata
INSERT INTO system_metadata (key, value) VALUES
    ('schema_version', '1.0.0'),
    ('last_event_export', ''),
    ('last_market_filter', ''),
    ('last_signal_generation', ''),
    ('last_trade_execution', '');