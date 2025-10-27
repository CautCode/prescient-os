# Events Controller - Fetches Polymarket events, filters for trading viability (liquidity, volume, time horizon), exports to JSON
# Main functions: get_active_events(), filter_trading_candidates_json(), export_all_active_events_json()
# Used by: trading_controller.py for event data pipeline

from fastapi import FastAPI, HTTPException, Query
from typing import Dict, List, Optional
import requests
import json
import csv
import os
from datetime import datetime, timedelta
import logging
import glob
import pandas as pd
import time

# Set up logging
import os
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# API Configuration
BASE_URL = "https://gamma-api.polymarket.com"
EVENTS_ENDPOINT = f"{BASE_URL}/events"

# Rate limiting configuration - delay between API requests to avoid throttling
API_REQUEST_DELAY = 0.5  # 500ms delay between requests

app = FastAPI(title="Polymarket Events API", version="1.0.0")

def apply_json_trading_filters(
    events_list: List[Dict],
    min_liquidity: Optional[float] = None,
    min_volume: Optional[float] = None,
    min_volume_24hr: Optional[float] = None,
    max_days_until_end: Optional[int] = None,
    min_days_until_end: Optional[int] = None
) -> List[Dict]:
    """
    Apply trading filters directly to JSON event objects
    
    Args:
        events_list: List of event JSON objects
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        max_days_until_end: Maximum days until event ends
        min_days_until_end: Minimum days until event ends
        
    Returns:
        Filtered list of event JSON objects with additional days_until_end field
    """
    logger.info(f"=== ENTERING APPLY_JSON_TRADING_FILTERS ===")
    logger.info(f"Input events count: {len(events_list)}")
    logger.info(f"Filter parameters: min_liquidity={min_liquidity}, min_volume={min_volume}, min_volume_24hr={min_volume_24hr}")
    logger.info(f"Time filters: max_days_until_end={max_days_until_end}, min_days_until_end={min_days_until_end}")
    
    filtered_events = []
    current_time = datetime.now()
    
    for event in events_list:
        try:
            # Copy event to avoid modifying original
            filtered_event = event.copy()
            
            # Filter by liquidity
            if min_liquidity is not None:
                liquidity = float(event.get('liquidity', 0))
                if liquidity < min_liquidity:
                    continue
            
            # Filter by total volume
            if min_volume is not None:
                volume = float(event.get('volume', 0))
                if volume < min_volume:
                    continue
            
            # Filter by 24hr volume
            if min_volume_24hr is not None:
                volume24hr = float(event.get('volume24hr', 0))
                if volume24hr < min_volume_24hr:
                    continue
            
            # Calculate and add days_until_end
            end_date_str = event.get('endDate')
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    days_diff = (end_date.replace(tzinfo=None) - current_time).days
                    filtered_event['days_until_end'] = days_diff
                except Exception as date_error:
                    logger.debug(f"Error calculating days for date '{end_date_str}': {date_error}")
                    filtered_event['days_until_end'] = None
            else:
                filtered_event['days_until_end'] = None
            
            # Apply time horizon filters
            if max_days_until_end is not None:
                days_until_end = filtered_event.get('days_until_end')
                if days_until_end is not None and days_until_end > max_days_until_end:
                    continue
            
            if min_days_until_end is not None:
                days_until_end = filtered_event.get('days_until_end')
                if days_until_end is not None and days_until_end < min_days_until_end:
                    continue
            
            # If we get here, event passed all filters
            filtered_events.append(filtered_event)
            
        except Exception as event_error:
            logger.warning(f"Error processing event {event.get('id', 'unknown')}: {event_error}")
            continue
    
    # Sort by volume descending for better trading candidates
    try:
        filtered_events.sort(key=lambda x: float(x.get('volume', 0)), reverse=True)
    except Exception as sort_error:
        logger.warning(f"Error sorting events by volume: {sort_error}")
    
    logger.info(f"=== EXITING APPLY_JSON_TRADING_FILTERS ===")
    logger.info(f"Final events count: {len(filtered_events)}")
    return filtered_events


def fetch_events_from_api(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    order: Optional[str] = None,
    ascending: Optional[bool] = None,
    id: Optional[List[int]] = None,
    slug: Optional[List[str]] = None,
    tag_id: Optional[int] = None,
    exclude_tag_id: Optional[List[int]] = None,
    related_tags: Optional[bool] = None,
    featured: Optional[bool] = None,
    cyom: Optional[bool] = None,
    include_chat: Optional[bool] = None,
    include_template: Optional[bool] = None,
    recurrence: Optional[str] = None,
    closed: Optional[bool] = None,
    start_date_min: Optional[str] = None,
    start_date_max: Optional[str] = None,
    end_date_min: Optional[str] = None,
    end_date_max: Optional[str] = None,
    session: requests.Session = None,
    **kwargs
) -> Optional[Dict]:
    """
    Fetch events from Polymarket API
    
    Args:
        limit: Maximum number of events to return
        offset: Number of events to skip
        order: Comma-separated list of fields to order by
        ascending: Sort order (True for ascending, False for descending)
        id: List of event IDs to filter by
        slug: List of event slugs to filter by
        tag_id: Tag ID to filter by
        exclude_tag_id: List of tag IDs to exclude
        related_tags: Include related tags
        featured: Filter by featured status
        cyom: Filter by CYOM (Create Your Own Market) status
        include_chat: Include chat data
        include_template: Include template data
        recurrence: Filter by recurrence pattern
        closed: Filter by closed status
        start_date_min: Minimum start date (ISO format)
        start_date_max: Maximum start date (ISO format)
        end_date_min: Minimum end date (ISO format)
        end_date_max: Maximum end date (ISO format)
        session: Optional requests session for connection reuse
        **kwargs: Additional query parameters
    
    Returns:
        Raw API response or None if error
    """
    params = {}
    
    if limit is not None:
        params['limit'] = limit
    if offset is not None:
        params['offset'] = offset
    if order is not None:
        params['order'] = order
    if ascending is not None:
        params['ascending'] = ascending
    if id is not None:
        params['id'] = id
    if slug is not None:
        params['slug'] = slug
    if tag_id is not None:
        params['tag_id'] = tag_id
    if exclude_tag_id is not None:
        params['exclude_tag_id'] = exclude_tag_id
    if related_tags is not None:
        params['related_tags'] = related_tags
    if featured is not None:
        params['featured'] = featured
    if cyom is not None:
        params['cyom'] = cyom
    if include_chat is not None:
        params['include_chat'] = include_chat
    if include_template is not None:
        params['include_template'] = include_template
    if recurrence is not None:
        params['recurrence'] = recurrence
    if closed is not None:
        params['closed'] = closed
    if start_date_min is not None:
        params['start_date_min'] = start_date_min
    if start_date_max is not None:
        params['start_date_max'] = start_date_max
    if end_date_min is not None:
        params['end_date_min'] = end_date_min
    if end_date_max is not None:
        params['end_date_max'] = end_date_max
    
    # Add any additional parameters
    params.update(kwargs)
    
    try:
        logger.debug(f"Fetching events with params: {params}")
        
        # Use provided session or default requests
        if session:
            response = session.get(EVENTS_ENDPOINT, params=params, timeout=30)
        else:
            response = requests.get(EVENTS_ENDPOINT, params=params, timeout=30)
        response.raise_for_status()
        
        # Add delay to prevent API throttling
        time.sleep(API_REQUEST_DELAY)
        
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching events: {e}")
        return None

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Events API is running", "timestamp": datetime.now().isoformat()}

@app.get("/events/active")
async def get_active_events():
    """
    Get all active (non-closed) events from Polymarket
    
    Args:
    
    Returns:
        Raw API response with all active events
    """
    try:
        all_events = []
        offset = 0
        limit = 500
        batch_count = 0
        
        logger.info("Starting to fetch all active events...")
        
        # Create session for connection reuse across all batches
        session = requests.Session()
        
        try:
            while True:
                batch_count += 1
                logger.info(f"Fetching batch {batch_count} with offset {offset}, limit {limit}")
                
                # Fetch active events with current offset using session for connection reuse
                raw_response = fetch_events_from_api(
                    limit=limit,
                    offset=offset,
                    closed=False,
                    session=session
                )
                
                if raw_response is None:
                    logger.error(f"Failed to fetch events at batch {batch_count}")
                    raise HTTPException(status_code=503, detail="Failed to fetch events from Polymarket API")
                
                # Extract events from response (assuming they're in 'data' or direct array)
                events = raw_response if isinstance(raw_response, list) else raw_response.get('data', raw_response)
                
                if not events or len(events) == 0:
                    logger.info(f"No more events found at batch {batch_count}. Stopping.")
                    break
                    
                logger.info(f"Batch {batch_count}: Retrieved {len(events)} events")
                all_events.extend(events)
                
                # If we got less than the limit, we've reached the end
                if len(events) < limit:
                    logger.info(f"Batch {batch_count}: Got {len(events)} events (less than limit {limit}). Reached end.")
                    break
                    
                # Move to next batch
                offset += limit
                logger.info(f"Moving to next batch. Total events collected so far: {len(all_events)}")
                
                # Add delay between batches to prevent API throttling
                if len(events) == limit:  # Only delay if we're continuing to next batch
                    logger.debug(f"Adding {API_REQUEST_DELAY}s delay between batches")
                    time.sleep(API_REQUEST_DELAY)
        finally:
            # Always close session
            session.close()
        
        logger.info(f"Completed fetching all active events. Total: {len(all_events)} events across {batch_count} batches")
        
        # Return in same format as original API response
        if isinstance(raw_response, list):
            return all_events
        else:
            # Preserve original response structure but with all events
            result = raw_response.copy()
            result['data'] = all_events
            return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_active_events: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/events/export-all-active-events-json")
async def export_all_active_events_json():
    """
    Export all active events as a json called raw_events_backup.json 
    in the ../data/events directory.

    Returns:
        JSON response with file path and summary info
    """
    try:
        logger.info("Starting JSON export of all active events...")

        # Reuse the existing get_active_events logic
        active_events_response = await get_active_events()

        # Extract events from response
        all_events = active_events_response if isinstance(active_events_response, list) else active_events_response.get('data', active_events_response)

        logger.info(f"Retrieved {len(all_events)} events for JSON export")

        # Prepare directory and file path
        events_dir = os.path.join("data", "events")
        os.makedirs(events_dir, exist_ok=True)
        file_path = os.path.join(events_dir, "raw_events_backup.json")

        # Save the full list of event jsons to disk
        with open(file_path, "w", encoding="utf-8") as outfile:
            json.dump(all_events, outfile, indent=2, ensure_ascii=False)

        logger.info(f"Successfully exported {len(all_events)} events to {file_path}")

        return {
            "message": "All active events exported to JSON successfully",
            "file_path": file_path,
            "total_events": len(all_events),
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in export_all_active_events_json: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/events/summary")
async def get_event_summary(event_id: int):
    """
    Get summary for a specific event by its ID
    
    Args:
        event_id: The ID of the event to get summary for (query parameter)
    
    Returns:
        Raw API response for the specific event
    """
    try:
        # Create session for connection reuse
        session = requests.Session()
        
        try:
            # Fetch specific event
            raw_response = fetch_events_from_api(id=[event_id], session=session)
            
            if raw_response is None or not raw_response:
                raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
            
            return raw_response
        finally:
            session.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_event_summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/events/by-id")
async def get_event_by_id(event_id: int):
    """
    Get a specific event by its ID
    
    Args:
        event_id: The ID of the event to retrieve (query parameter)
    
    Returns:
        Raw API response for the event
    """
    try:
        # Create session for connection reuse
        session = requests.Session()
        
        try:
            # Fetch events and filter by ID
            raw_response = fetch_events_from_api(id=[event_id], session=session)
            
            if raw_response is None or not raw_response:
                raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
            
            return raw_response
        finally:
            session.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_event_by_id: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/events/filter-trading-candidates-json")
async def filter_trading_candidates_json(
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    max_days_until_end: int = 90,
    min_days_until_end: int = 1
):
    """
    Filter events from the latest JSON export to create trading candidates

    Args:
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        max_days_until_end: Maximum days until event ends
        min_days_until_end: Minimum days until event ends

    Returns:
        JSON response with filtered trading candidates JSON file path and summary
    """
    try:
        logger.info("=== STARTING TRADING CANDIDATES FILTERING (JSON version) ===")
        logger.info(f"Parameters received: min_liquidity={min_liquidity}, min_volume={min_volume}, min_volume_24hr={min_volume_24hr}, max_days_until_end={max_days_until_end}, min_days_until_end={min_days_until_end}")

        # Step 1: Read raw events from JSON file
        events_path = os.path.join("data", "events", "raw_events_backup.json")
        logger.info(f"Reading raw events from: {events_path}")
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                events_data = json.load(f)
            logger.info(f"✓ Successfully loaded {len(events_data)} events from JSON")
        except Exception as read_error:
            logger.error(f"✗ Error reading JSON file: {read_error}")
            raise HTTPException(status_code=500, detail=f"Error reading JSON file: {str(read_error)}")

        # Step 2: Apply JSON filters directly (no DataFrame conversion needed)
        logger.info("Step 2: Applying JSON trading filters...")
        try:
            filtered_events = apply_json_trading_filters(
                events_list=events_data,
                min_liquidity=min_liquidity,
                min_volume=min_volume,
                min_volume_24hr=min_volume_24hr,
                max_days_until_end=max_days_until_end,
                min_days_until_end=min_days_until_end
            )
            logger.info(f"✓ Successfully applied filters. Filtered events count: {len(filtered_events)}")
        except Exception as filter_error:
            logger.error(f"✗ Error applying filters: {filter_error}")
            import traceback
            logger.error(f"Filter error traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Error applying filters: {str(filter_error)}")

        # Step 3: Export filtered trading candidates to JSON
        logger.info("Step 3: Exporting filtered trading candidates to JSON...")
        try:
            # Save to fixed filename for trading system consumption (OVERWRITE as per data persistence strategy)
            output_filename = "filtered_events.json"
            output_dir = os.path.join("data", "events")
            output_path = os.path.join(output_dir, output_filename)
            with open(output_path, "w", encoding="utf-8") as fout:
                json.dump(filtered_events, fout, ensure_ascii=False, indent=2)
            logger.info(f"✓ Successfully exported JSON to: {output_path}")
        except Exception as export_error:
            logger.error(f"✗ Error exporting JSON: {export_error}")
            raise HTTPException(status_code=500, detail=f"Error exporting JSON: {str(export_error)}")

        # Step 4: Calculate summary statistics
        logger.info("Step 4: Calculating summary statistics...")
        try:
            total_candidates = len(filtered_events)
            logger.info(f"Total candidates: {total_candidates}")

            if total_candidates > 0:
                avg_liquidity = sum(float(event.get('liquidity', 0)) for event in filtered_events) / total_candidates
                avg_volume = sum(float(event.get('volume', 0)) for event in filtered_events) / total_candidates
                avg_days_until_end = sum(event.get('days_until_end', 0) or 0 for event in filtered_events if event.get('days_until_end') is not None) / len([e for e in filtered_events if e.get('days_until_end') is not None]) if any(e.get('days_until_end') is not None for e in filtered_events) else 0
                logger.info(f"✓ Calculated stats - avg_liquidity: {avg_liquidity}, avg_volume: {avg_volume}, avg_days_until_end: {avg_days_until_end}")
            else:
                avg_liquidity = avg_volume = avg_days_until_end = 0
                logger.info("No candidates found - all stats set to 0")
        except Exception as stats_error:
            logger.error(f"✗ Error calculating stats: {stats_error}")
            avg_liquidity = avg_volume = avg_days_until_end = 0

        logger.info("=== TRADING CANDIDATES FILTERING (JSON) COMPLETED SUCCESSFULLY ===")

        return {
            "message": "Trading candidates filtered and exported successfully",
            "source_file": events_path,
            "output_file": output_path,
            "total_candidates": total_candidates,
            "total_original_events": len(events_data),
            "filters_applied": {
                "min_liquidity": min_liquidity,
                "min_volume": min_volume,
                "min_volume_24hr": min_volume_24hr,
                "max_days_until_end": max_days_until_end,
                "min_days_until_end": min_days_until_end
            },
            "summary_stats": {
                "avg_liquidity": round(avg_liquidity, 2) if avg_liquidity else None,
                "avg_volume": round(avg_volume, 2) if avg_volume else None,
                "avg_days_until_end": round(avg_days_until_end, 1) if avg_days_until_end else None
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        logger.error("Re-raising HTTPException")
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN FILTER_TRADING_CANDIDATES_JSON ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # uvicorn src.events_controller:app --reload