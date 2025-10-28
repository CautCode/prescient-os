# Market Controller - Extracts markets from filtered events, applies trading filters (liquidity, volume, time horizon), fetches detailed market data
# Main functions: export_filtered_markets_json(), get_current_filtered_markets(), apply_market_trading_filters()
# Used by: trading_strategy_controller.py for market analysis and signal generation
# Future Functionality: Add ability to see central limit order book data to add additional context to trades.

from fastapi import FastAPI, HTTPException
from typing import Dict, List, Optional
import requests
import json
import os
from datetime import datetime
import logging
import time

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# API Configuration
BASE_URL = "https://gamma-api.polymarket.com"
MARKETS_ENDPOINT = f"{BASE_URL}/markets"

# Rate limiting configuration - delay between API requests to avoid throttling
API_REQUEST_DELAY = 0.5  # 500ms delay between requests

app = FastAPI(title="Polymarket Markets API", version="1.0.0")

# Helper Functions
def ensure_data_directories():
    """
    Create necessary data directories if they don't exist
    """
    os.makedirs("data/markets", exist_ok=True)

def extract_markets_from_events(events_list: List[Dict]) -> List[Dict]:
    """
    Extract all market objects from filtered events
    
    Args:
        events_list: List of event JSON objects with markets
        
    Returns:
        List of market objects with event context
    """
    markets = []
    
    for event in events_list:
        event_markets = event.get('markets', [])
        for market in event_markets:
            # Add event context to market
            market_with_context = market.copy()
            market_with_context['event_id'] = event.get('id')
            market_with_context['event_title'] = event.get('title')
            market_with_context['event_end_date'] = event.get('endDate')
            markets.append(market_with_context)
    
    logger.info(f"Extracted {len(markets)} markets from {len(events_list)} events")
    return markets

def apply_market_trading_filters(
    markets_list: List[Dict],
    min_liquidity: Optional[float] = None,
    min_volume: Optional[float] = None,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = None,
    max_market_conviction: Optional[float] = None
) -> List[Dict]:
    """
    Apply trading filters directly to market objects (similar to events filtering)
    
    Args:
        markets_list: List of market objects from events
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        min_market_conviction: Minimum market conviction threshold (abs(yes_price - no_price))
        max_market_conviction: Maximum market conviction threshold (abs(yes_price - no_price))
        
    Returns:
        Filtered list of market objects
    """
    logger.info(f"=== ENTERING APPLY_MARKET_TRADING_FILTERS ===")
    logger.info(f"Input markets count: {len(markets_list)}")
    logger.info(f"Filter parameters: min_liquidity={min_liquidity}, min_volume={min_volume}, min_volume_24hr={min_volume_24hr}")
    logger.info(f"Conviction filters: min_market_conviction={min_market_conviction}, max_market_conviction={max_market_conviction}")
    
    filtered_markets = []
    
    for market in markets_list:
        try:
            # Copy market to avoid modifying original
            filtered_market = market.copy()
            
            # Filter by liquidity
            if min_liquidity is not None:
                liquidity = float(market.get('liquidity', 0))
                if liquidity < min_liquidity:
                    continue
            
            # Filter by total volume
            if min_volume is not None:
                volume = float(market.get('volume', 0))
                if volume < min_volume:
                    continue
            
            # Filter by 24hr volume
            if min_volume_24hr is not None:
                volume24hr = float(market.get('volume24hr', 0))
                if volume24hr < min_volume_24hr:
                    continue
            
            # Filter by market conviction (abs(yes_price - no_price))
            # Higher is more conviction.
            # For example, if the yes_price is 0.6 and the no_price is 0.4, the market_conviction is 0.2.
            # 0 Market conviction means that the market is perfectly balanced at 50/50.
            # 1 Market conviction means that the market is very biased towards one outcome.
            # 0.5 Market conviction means we have odds of 0.75 and 0.25 since 0.75 - 0.25 = 0.5.
            if min_market_conviction is not None or max_market_conviction is not None:
                outcome_prices_str = market.get('outcomePrices', '[]')
                try:
                    import ast
                    outcome_prices = ast.literal_eval(outcome_prices_str)
                    if outcome_prices and len(outcome_prices) >= 2:
                        yes_price = float(outcome_prices[0])
                        no_price = float(outcome_prices[1])
                        market_conviction = abs(yes_price - no_price)
                        filtered_market['yes_price'] = yes_price
                        filtered_market['no_price'] = no_price
                        filtered_market['market_conviction'] = market_conviction
                        if min_market_conviction is not None:
                            if market_conviction < min_market_conviction:
                                continue
                        if max_market_conviction is not None:
                            if market_conviction > max_market_conviction:
                                continue
                    else:
                        # If cannot parse prices, skip
                        continue
                except Exception as price_error:
                    logger.debug(f"Error parsing outcome prices for market {market.get('id', 'unknown')}: {price_error}")
                    continue
            
            # If we get here, market passed all filters
            filtered_markets.append(filtered_market)
            
        except Exception as market_error:
            logger.warning(f"Error processing market {market.get('id', 'unknown')}: {market_error}")
            continue
    
    # Sort by volume descending for better trading candidates
    try:
        filtered_markets.sort(key=lambda x: float(x.get('volume', 0)), reverse=True)
    except Exception as sort_error:
        logger.warning(f"Error sorting markets by volume: {sort_error}")
    
    logger.info(f"=== EXITING APPLY_MARKET_TRADING_FILTERS ===")
    logger.info(f"Final markets count: {len(filtered_markets)}")
    return filtered_markets

def extract_market_ids_from_filtered_markets(markets_list: List[Dict]) -> List[str]:
    """
    Extract market IDs from filtered market objects
    
    Args:
        markets_list: List of filtered market objects
        
    Returns:
        List of unique market IDs
    """
    market_ids = []
    
    for market in markets_list:
        market_id = market.get('id')
        if market_id and market_id not in market_ids:
            market_ids.append(market_id)
    
    logger.info(f"Extracted {len(market_ids)} unique market IDs from filtered markets")
    return market_ids

def fetch_market_data_from_api(market_id: str, session: requests.Session = None) -> Optional[Dict]:
    """
    Fetch individual market data from Polymarket API
    
    Args:
        market_id: The ID of the market to fetch
        session: Optional requests session for connection reuse
        
    Returns:
        Market data dictionary or None if error
    """
    try:
        url = f"{MARKETS_ENDPOINT}/{market_id}"
        logger.debug(f"Fetching market data from: {url}")
        
        # Use provided session or default requests
        if session:
            response = session.get(url, timeout=30)
        else:
            response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Add delay to prevent API throttling
        time.sleep(API_REQUEST_DELAY)
        
        market_data = response.json()
        logger.debug(f"Successfully fetched data for market {market_id}")
        return market_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching market {market_id}: {e}")
        return None

def fetch_all_markets_data(market_ids: List[str]) -> List[Dict]:
    """
    Fetch data for all market IDs using batched API requests (batches of 10)
    
    Args:
        market_ids: List of market IDs to fetch
        
    Returns:
        List of market data dictionaries
    """
    if not market_ids:
        logger.warning("No market IDs provided for fetching")
        return []
    
    # Split market IDs into batches of 10
    batch_size = 10
    batches = [market_ids[i:i+batch_size] for i in range(0, len(market_ids), batch_size)]
    
    logger.info(f"Starting batched fetch for {len(market_ids)} markets in {len(batches)} batches of {batch_size}...")
    
    # Create session for connection reuse
    session = requests.Session()
    
    all_markets_data = []
    failed_batches = []
    
    for batch_num, batch_ids in enumerate(batches, 1):
        try:
            logger.info(f"Processing batch {batch_num}/{len(batches)} with {len(batch_ids)} markets...")
            
            # Build URL for this batch
            url = f"{MARKETS_ENDPOINT}"
            params = [f"id={market_id}" for market_id in batch_ids]  # Use id=X not id[]=X
            
            if params:
                url += "?" + "&".join(params)
            
            logger.debug(f"Batch {batch_num} URL: {url}")
            
            # Make request for this batch using session for connection reuse
            response = session.get(url, timeout=60)
            response.raise_for_status()
            
            # Add delay to prevent API throttling
            time.sleep(API_REQUEST_DELAY)
            
            batch_markets = response.json()
            
            if not isinstance(batch_markets, list):
                logger.error(f"Batch {batch_num}: Expected list response, got {type(batch_markets)}")
                failed_batches.append(batch_num)
                continue
            
            logger.info(f"✓ Batch {batch_num}: Successfully fetched {len(batch_markets)} markets")
            all_markets_data.extend(batch_markets)
            
            # Check for missing markets in this batch
            fetched_ids = {str(market.get('id')) for market in batch_markets if market.get('id')}
            requested_ids = set(batch_ids)
            missing_ids = requested_ids - fetched_ids
            
            if missing_ids:
                logger.warning(f"Batch {batch_num}: Missing {len(missing_ids)} markets: {list(missing_ids)}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Batch {batch_num} API request failed: {e}")
            failed_batches.append(batch_num)
            continue
            
        except Exception as e:
            logger.error(f"Batch {batch_num} unexpected error: {e}")
            failed_batches.append(batch_num)
            continue
    
    logger.info(f"✓ Completed batched fetch: {len(all_markets_data)} markets fetched from {len(batches)} batches")
    
    if failed_batches:
        logger.warning(f"Failed batches: {failed_batches}")
        
        # Retry failed batches individually as fallback
        logger.info("Retrying failed batches with individual calls...")
        for batch_num in failed_batches:
            batch_ids = batches[batch_num - 1]  # Convert to 0-based index
            individual_markets = fetch_markets_individually(batch_ids, session)
            all_markets_data.extend(individual_markets)
    
    # Close session
    session.close()
    
    # Final summary
    total_requested = len(market_ids)
    total_fetched = len(all_markets_data)
    logger.info(f"Final result: {total_fetched}/{total_requested} markets fetched successfully")
    
    return all_markets_data

def fetch_markets_individually(market_ids: List[str], session: requests.Session = None) -> List[Dict]:
    """
    Fallback function to fetch markets individually (original behavior)
    
    Args:
        market_ids: List of market IDs to fetch
        session: Optional requests session for connection reuse
        
    Returns:
        List of market data dictionaries
    """
    markets_data = []
    
    logger.info(f"Fetching {len(market_ids)} markets individually as fallback...")
    
    # Use provided session or create new one
    if session is None:
        session = requests.Session()
        close_session = True
    else:
        close_session = False
    
    for i, market_id in enumerate(market_ids, 1):
        logger.info(f"Fetching market {i}/{len(market_ids)}: {market_id}")
        
        market_data = fetch_market_data_from_api(market_id, session)
        if market_data:
            markets_data.append(market_data)
        else:
            logger.warning(f"Failed to fetch data for market {market_id}")
        
        # Add delay between individual requests to prevent API throttling
        if i < len(market_ids):  # Don't delay after the last request
            time.sleep(API_REQUEST_DELAY)
    
    # Close session if we created it
    if close_session:
        session.close()
    
    logger.info(f"Successfully fetched {len(markets_data)} out of {len(market_ids)} markets individually")
    return markets_data

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Markets API is running", "timestamp": datetime.now().isoformat()}

@app.get("/markets/export-filtered-markets-db")
async def export_filtered_markets_db(
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = None,
    max_market_conviction: Optional[float] = None
):
    """
    Export filtered markets to database (Phase 4: Database version)

    Args:
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        min_market_conviction: Minimum market conviction threshold
        max_market_conviction: Maximum market conviction threshold

    Returns:
        JSON response with filtered market summary
    """
    from src.db.operations import get_events, upsert_markets, insert_market_snapshot, clear_filtered_markets

    try:
        logger.info("=== STARTING MARKET FILTERING (DATABASE version) ===")
        logger.info(f"Parameters: min_liquidity={min_liquidity}, min_volume={min_volume}")

        # Step 1: Read filtered events from database
        logger.info("Step 1: Loading filtered events from database...")
        events_data = get_events({'is_filtered': True})

        if not events_data:
            raise HTTPException(status_code=500, detail="No filtered events found in database. Please filter events first.")

        logger.info(f"Successfully loaded {len(events_data)} filtered events from database")

        # Step 2: Extract markets from events (same as before)
        logger.info("Step 2: Extracting markets from events...")
        all_markets = extract_markets_from_events(events_data)

        if not all_markets:
            raise HTTPException(status_code=404, detail="No markets found in filtered events")

        # Step 3: Apply market filters (same as before)
        logger.info("Step 3: Applying market trading filters...")
        filtered_markets = apply_market_trading_filters(
            markets_list=all_markets,
            min_liquidity=min_liquidity,
            min_volume=min_volume,
            min_volume_24hr=min_volume_24hr,
            min_market_conviction=min_market_conviction,
            max_market_conviction=max_market_conviction
        )
        logger.info(f"Successfully applied filters. Filtered markets count: {len(filtered_markets)}")

        # Step 4: Get market IDs for API fetching (same as before)
        logger.info("Step 4: Extracting market IDs for API fetching...")
        market_ids = extract_market_ids_from_filtered_markets(filtered_markets)

        if not market_ids:
            return {
                "message": "No markets passed the trading filters",
                "total_original_markets": len(all_markets),
                "filtered_markets": 0,
                "timestamp": datetime.now().isoformat()
            }

        # Step 5: Fetch detailed market data from API (same as before)
        logger.info("Step 5: Fetching detailed market data from API...")
        detailed_markets_data = fetch_all_markets_data(market_ids)

        if not detailed_markets_data:
            raise HTTPException(status_code=503, detail="Failed to fetch any detailed market data from API")

        # Step 6: Merge context and save to database instead of JSON
        logger.info("Step 6: Merging event context and saving filtered markets to database...")

        # Merge event context (event_id, event_title, event_end_date) and
        # computed pricing (yes_price, no_price, market_conviction) from
        # filtered_markets into detailed_markets_data by market id
        context_by_id = {}
        for m in filtered_markets:
            mid = m.get('id')
            if not mid:
                continue
            context_by_id[mid] = {
                'event_id': m.get('event_id'),
                'event_title': m.get('event_title'),
                'event_end_date': m.get('event_end_date'),
                'yes_price': m.get('yes_price'),
                'no_price': m.get('no_price'),
                'market_conviction': m.get('market_conviction')
            }

        for dm in detailed_markets_data:
            mid = dm.get('id')
            if not mid:
                continue
            ctx = context_by_id.get(mid)
            if ctx:
                # Only fill missing or null fields in detailed object
                for k, v in ctx.items():
                    if v is not None and (dm.get(k) is None):
                        dm[k] = v

        # If prices are still missing, try to compute from detailed response
        for dm in detailed_markets_data:
            if dm.get('yes_price') is None or dm.get('no_price') is None:
                op = dm.get('outcomePrices')
                try:
                    if isinstance(op, str):
                        import ast
                        op_list = ast.literal_eval(op)
                    else:
                        op_list = op
                    if op_list and len(op_list) >= 2:
                        yes = float(op_list[0])
                        no = float(op_list[1])
                        dm['yes_price'] = yes
                        dm['no_price'] = no
                        dm['market_conviction'] = abs(yes - no)
                except Exception:
                    pass

        # Ensure event_end_date is a datetime if it's still a string
        from datetime import datetime as _dt
        for dm in detailed_markets_data:
            eed = dm.get('event_end_date')
            if isinstance(eed, str):
                try:
                    dm['event_end_date'] = _dt.fromisoformat(eed.replace('Z', '+00:00'))
                except Exception:
                    # leave as-is if parsing fails
                    pass

        # Clear previous filtered flags
        clear_filtered_markets()

        # Mark as filtered
        for market in detailed_markets_data:
            market['is_filtered'] = True

        upsert_markets(detailed_markets_data)

        # Also save market snapshots for price history
        for market in detailed_markets_data:
            insert_market_snapshot(market['id'], {
                'yes_price': market.get('yes_price'),
                'no_price': market.get('no_price'),
                'liquidity': market.get('liquidity'),
                'volume': market.get('volume'),
                'volume24hr': market.get('volume24hr'),
                'market_conviction': market.get('market_conviction')
            })

        logger.info(f"Successfully saved {len(detailed_markets_data)} markets to database")

        # Step 7: Calculate summary statistics
        logger.info("Step 7: Calculating summary statistics...")
        total_filtered = len(detailed_markets_data)
        if total_filtered > 0:
            avg_liquidity = sum(float(m.get('liquidity', 0)) for m in detailed_markets_data) / total_filtered
            avg_volume = sum(float(m.get('volume', 0)) for m in detailed_markets_data) / total_filtered
        else:
            avg_liquidity = avg_volume = 0

        logger.info("=== MARKET FILTERING (DATABASE) COMPLETED ===")

        return {
            "message": "Market trading candidates filtered and saved to database successfully",
            "total_original_markets": len(all_markets),
            "filtered_markets": len(filtered_markets),
            "fetched_detailed_markets": len(detailed_markets_data),
            "filters_applied": {
                "min_liquidity": min_liquidity,
                "min_volume": min_volume,
                "min_volume_24hr": min_volume_24hr,
                "min_market_conviction": min_market_conviction,
                "max_market_conviction": max_market_conviction
            },
            "summary_stats": {
                "avg_liquidity": round(avg_liquidity, 2) if avg_liquidity else None,
                "avg_volume": round(avg_volume, 2) if avg_volume else None
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN MARKET FILTERING ===")
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/markets/current-filtered")
async def get_current_filtered_markets():
    """
    Get current filtered markets from database (Phase 4: Database version)

    Returns:
        Current filtered markets data
    """
    from src.db.operations import get_markets

    try:
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            raise HTTPException(status_code=404, detail="Filtered markets not found. Please filter trading candidates first.")

        return {
            "message": "Current filtered markets retrieved from database",
            "markets_count": len(markets_data),
            "markets": markets_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading filtered markets: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading filtered markets: {str(e)}")


@app.get("/markets/status")
async def get_market_status():
    """
    Get status of market data system
    
    Returns:
        Status information about filtered markets and files
    """
    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "filtered_markets_exists": False,
            "filtered_markets_count": 0,
            "filtered_markets_last_modified": None
        }
        
        # Check filtered markets
        filtered_markets_path = os.path.join("data", "markets", "filtered_markets.json")
        if os.path.exists(filtered_markets_path):
            status["filtered_markets_exists"] = True
            status["filtered_markets_last_modified"] = datetime.fromtimestamp(os.path.getmtime(filtered_markets_path)).isoformat()
            
            try:
                with open(filtered_markets_path, "r", encoding="utf-8") as f:
                    markets_data = json.load(f)
                    status["filtered_markets_count"] = len(markets_data)
            except:
                pass
        
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting market status: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
    # uvicorn src.market_controller:app --reload --port 8001