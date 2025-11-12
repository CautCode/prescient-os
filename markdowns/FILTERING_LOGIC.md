# Event and Market Filtering Flow

This document explains the multi-stage filtering process used to identify viable trading opportunities, starting from a wide universe of events and narrowing it down to a select list of markets for strategy execution.

## Orchestration

The entire filtering pipeline is orchestrated by the `trading_controller.py`. When a trading cycle is initiated (e.g., via `run_portfolio_trading_cycle`), it calls the `events_controller` and `market_controller` in sequence to perform the filtering.

The process can be broken down into two main stages:

1.  **Event-Level Filtering**: A broad filtering pass to identify interesting events.
2.  **Market-Level Filtering**: A more granular filtering pass to select specific markets for trading.

---

## Stage 1: Event Filtering (`events_controller.py`)

This stage is responsible for fetching all active events from the Polymarket API and applying the first layer of filters.

**Endpoint**: `/events/filter-trading-candidates-db`

### Process:

1.  **Data Ingestion**: The cycle begins by calling `/events/export-all-active-events-db`. This fetches all active (non-closed) events and their associated markets from the Polymarket API. The data is then stored in the `events` and `markets` tables in the database. Initially, no items are marked as "filtered."
2.  **Load Events**: The controller loads all events from the `events` table.
3.  **Apply Filters**: The `apply_json_trading_filters` function is called. It iterates through each event and applies filters based on the following criteria passed from the `trading_controller`:
    *   `min_liquidity`: The event's total liquidity must be above this threshold.
    *   `min_volume`: The event's total volume must be above this threshold.
    *   `min_volume_24hr`: The event's 24-hour volume must be above this threshold.
    *   `max_days_until_end`: The event must end before this many days.
    *   `min_days_until_end`: The event must end after this many days.
4.  **Mark Filtered Events**: Events that successfully pass all the above criteria are marked in the database by setting their `is_filtered` column to `true`.

**Outcome**: A subset of events in the `events` table are now marked as `is_filtered = true`.

---

## Stage 2: Market Filtering (`market_controller.py`)

This stage takes over to apply a second, more specific set of filters at the individual market level.

**Endpoint**: `/markets/export-filtered-markets-db`

### Process:

1.  **Load Markets**: The controller loads **all** markets from the `markets` table.
2.  **Apply Filters**: The `apply_market_trading_filters` function is called. It iterates through each market and applies a new set of filters:
    *   `min_liquidity`: The market's liquidity must be above this threshold.
    *   `min_volume`: The market's total volume must be above this threshold.
    *   `min_volume_24hr`: The market's 24-hour volume must be above this threshold.
    *   `min_market_conviction`: The absolute difference between the 'yes' and 'no' price (`abs(yes_price - no_price)`) must be above this value. This filters for markets with a clearer bias.
    *   `max_market_conviction`: The market conviction must be below this value. This filters out markets that are near-certainties.
3.  **Data Refresh**: For the markets that pass the filters, the controller fetches the latest, most detailed data from the Polymarket API using their market IDs.
4.  **Mark Filtered Markets**: These refreshed, filtered markets are updated in the `markets` table, and their `is_filtered` column is set to `true`. All other markets are marked as `is_filtered = false`.

**Outcome**: A final, refined list of markets in the `markets` table are marked as `is_filtered = true`. These are the markets that the `trading_strategy_controller` will analyze to generate trading signals.

---

## Analysis and Key Insight

There is a crucial detail in the current implementation:

**The two filtering stages are independent.**

The market filtering stage **does not** use the results from the event filtering stage. `market_controller.py` loads *all* markets from the database and applies its filters, regardless of whether the parent event was marked as `is_filtered = true`.

This means the event-level filtering currently serves as a preliminary analysis step, but its output (the `is_filtered` flag on events) does not constrain the input of the subsequent market-filtering stage. The final set of markets passed to the strategy controllers is determined exclusively by the criteria in the `market_controller`.

---

## Corrected Plan: Sequential ID-Based Filtering

This plan implements a stateless, in-memory filtering pipeline that precisely follows the desired sequential flow: filter events, then use those results to filter the relevant markets. The process relies exclusively on passing lists of IDs between services, with each service fetching the data it needs from the database.

#### **Phase 1: API & Database Changes (Corrected Flow)**

1.  **Database Schema:**
    *   Remove the `is_filtered` column from the `events` and `markets` tables.

2.  **API Redesign (Corrected):**

    *   **`events_controller.py`:**
        *   **New Endpoint:** `GET /events/filter`
        *   **Functionality:**
            1.  Accepts event filtering parameters (e.g., `min_liquidity`, `min_volume`) via query string.
            2.  Loads **all** events from the database into memory.
            3.  Applies the filtering logic to the in-memory list.
            4.  Returns a JSON response containing a list of the `event_ids` that passed the filter.

    *   **`market_controller.py`:**
        *   **New Endpoint:** `POST /markets/filter-by-event`
        *   **Functionality:**
            1.  Accepts a list of `event_ids` in the request body.
            2.  Accepts market filtering parameters (e.g., `min_market_conviction`) via query string.
            3.  Fetches **only the markets associated with the provided `event_ids`** from the database.
            4.  Applies its market-specific filtering logic to this subset of markets.
            5.  Returns a JSON response containing a list of the `market_ids` that passed the filter.

    *   **`trading_strategy_controller.py`:**
        *   **Modify Endpoint:** `POST /strategy/generate-signals`
        *   **Functionality:**
            1.  Accepts a list of `market_ids` in the request body and the `portfolio_id` as a query parameter.
            2.  Fetches the detailed data for these specific `market_ids` from the database.
            3.  Fetches the portfolio's strategy configuration from the database to get strategy-specific parameters (e.g., trade amount, confidence thresholds).
            4.  Applies its unique strategy logic to generate signals.
            5.  Inserts the generated signals into the database, linked to the `portfolio_id`.
            6.  Returns a summary of the operation (e.g., number of signals generated).

#### **Phase 2: Rework Orchestration (`trading_controller.py`)**

1.  **Update the Trading Cycle Workflow:**
    *   The `run_portfolio_trading_cycle` function will orchestrate the new sequential, ID-based pipeline.

    *   **New Sequential Workflow:**
        1.  **Filter Events:** Call `GET /events/filter` with the portfolio's specific event filter parameters. Receive the filtered list of `event_ids`.
        2.  **Filter Markets:** `POST` the list of filtered `event_ids` to the new `/markets/filter-by-event` endpoint, along with the portfolio's market filter parameters. Receive the final, filtered list of `market_ids`.
        3.  **Generate Signals:** `POST` the final list of `market_ids` to the `/strategy/generate-signals` endpoint (along with the `portfolio_id`).
        4.  **Execute Trades:** The rest of the cycle (executing newly inserted signals from the DB) proceeds as before.

#### **Phase 3: Data Population**

1.  **Daily Data Load:**
    *   The `export_all_active_events_db` function in `events_controller.py` remains responsible for the initial, daily population of the `events` and `markets` tables.

This corrected plan is more efficient, eliminates data redundancy between stages, and perfectly aligns with the sequential filtering logic.
