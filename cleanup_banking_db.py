import os
import aiohttp
import asyncio
import logging
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')
ACCOUNTS_TABLE_ID = os.getenv('ACCOUNTS_TABLE_ID')

# Use the specific column ID for Discord User ID
DISCORD_USER_ID_COLUMN = "c-MxtkQv7d7g"  # Discord User ID column ID

# Track rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 0.5  # seconds between requests
RATE_LIMIT_DELAY = 60  # seconds to wait after hitting a rate limit

async def sleep_for_rate_limit():
    """Sleep to respect rate limits."""
    global last_request_time
    current_time = time.time()
    elapsed = current_time - last_request_time
    
    if elapsed < MIN_REQUEST_INTERVAL:
        delay = MIN_REQUEST_INTERVAL - elapsed
        await asyncio.sleep(delay)
    
    last_request_time = time.time()

async def coda_api_request(method, endpoint, params=None, data=None):
    """Make a request to the Coda API with rate limit handling."""
    if not CODA_API_TOKEN:
        logger.error("Coda API token not found")
        return None
            
    headers = {
        'Authorization': f'Bearer {CODA_API_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    url = f'https://coda.io/apis/v1/{endpoint}'
    
    # Respect rate limiting
    await sleep_for_rate_limit()
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:  # Rate limited
                            logger.warning(f"Rate limited by Coda API. Waiting {RATE_LIMIT_DELAY} seconds.")
                            await asyncio.sleep(RATE_LIMIT_DELAY)
                            retry_count += 1
                            continue
                        else:
                            logger.error(f"API request failed: {response.status} - {await response.text()}")
                            return None
                elif method == 'DELETE':
                    async with session.delete(url, headers=headers) as response:
                        # For DELETE, Coda may return 202 (Accepted) for asynchronous operations
                        if response.status in [200, 202, 204]:
                            response_text = await response.text()
                            logger.info(f"Delete request accepted with status {response.status}: {response_text}")
                            return True
                        elif response.status == 429:  # Rate limited
                            logger.warning(f"Rate limited by Coda API. Waiting {RATE_LIMIT_DELAY} seconds.")
                            await asyncio.sleep(RATE_LIMIT_DELAY)
                            retry_count += 1
                            continue
                        else:
                            logger.error(f"API request failed: {response.status} - {await response.text()}")
                            return None
            
            # If we get here, we didn't need to retry
            break
                
        except Exception as e:
            logger.error(f"Error making API request: {e}")
            return None
    
    return None  # Return None if we exhausted all retries

async def get_duplicate_accounts():
    """Get a list of duplicate account rows for the same Discord User ID."""
    endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
    
    # Try to get all rows - use multiple requests if needed
    all_rows = []
    next_page_token = None
    
    while True:
        params = {'limit': 100}
        if next_page_token:
            params['pageToken'] = next_page_token
            
        response = await coda_api_request('GET', endpoint, params=params)
        
        if not response or 'items' not in response:
            logger.error("Failed to retrieve account rows")
            break
            
        all_rows.extend(response['items'])
        
        # Check if there's another page
        if 'nextPageToken' in response and response['nextPageToken']:
            next_page_token = response['nextPageToken']
            logger.info(f"Fetching next page of rows. Total so far: {len(all_rows)}")
        else:
            break
    
    logger.info(f"Retrieved {len(all_rows)} total rows")
    
    # Check if we can get column info
    columns_endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/columns'
    columns_response = await coda_api_request('GET', columns_endpoint)
    
    if columns_response and 'items' in columns_response:
        logger.info(f"Found {len(columns_response['items'])} columns in the table")
        for column in columns_response['items']:
            logger.info(f"Column: {column.get('name', 'Unknown')} (ID: {column.get('id', 'Unknown')})")
    
    # Track accounts by Discord User ID
    accounts_by_id = {}
    
    # Group rows by Discord User ID
    for item in all_rows:
        if 'values' not in item:
            continue
            
        values = item['values']
        
        # Try to find the user ID using the column ID
        user_id = None
        for column_id, value in values.items():
            if column_id == DISCORD_USER_ID_COLUMN:
                user_id = value
                break
        
        if not user_id:
            logger.warning(f"Could not find Discord User ID in row {item.get('id', 'Unknown')}")
            continue
            
        if user_id not in accounts_by_id:
            accounts_by_id[user_id] = []
                
        accounts_by_id[user_id].append({
            'row_id': item['id'],
            'values': values
        })
    
    # Find accounts with duplicate rows
    duplicate_rows = []
    for user_id, rows in accounts_by_id.items():
        if len(rows) > 1:
            # Keep the first row, mark others for deletion
            logger.info(f"Found {len(rows)} duplicate rows for user ID {user_id}")
            for row in rows[1:]:
                duplicate_rows.append(row)
                
    logger.info(f"Found {len(duplicate_rows)} duplicate account rows in total")
    return duplicate_rows

async def delete_duplicate_rows(duplicate_rows, batch_size=10):
    """Delete duplicate rows from the accounts table in batches with rate limit handling."""
    total = len(duplicate_rows)
    deleted = 0
    failed = 0
    
    # Process in batches
    batches = [duplicate_rows[i:i + batch_size] for i in range(0, len(duplicate_rows), batch_size)]
    
    for batch_num, batch in enumerate(batches):
        logger.info(f"Processing batch {batch_num+1}/{len(batches)} ({len(batch)} rows)")
        
        for row in batch:
            row_id = row['row_id']
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows/{row_id}'
            
            logger.info(f"Deleting duplicate row {row_id} ({deleted+failed+1}/{total})")
            
            success = await coda_api_request('DELETE', endpoint)
            if success:
                logger.info(f"Successfully deleted row {row_id}")
                deleted += 1
            else:
                logger.error(f"Failed to delete row {row_id}")
                failed += 1
            
            # Small delay between requests even within a batch
            await asyncio.sleep(0.2)
        
        # Larger delay between batches
        if batch_num < len(batches) - 1:
            delay = 2.0
            logger.info(f"Batch complete. Waiting {delay} seconds before next batch...")
            await asyncio.sleep(delay)
    
    logger.info(f"Deletion complete. Successfully deleted: {deleted}, Failed: {failed}")
    return deleted, failed

async def main():
    """Main function to find and clean up duplicate account rows."""
    logger.info("Starting database cleanup")
    
    # Get duplicate account rows
    duplicate_rows = await get_duplicate_accounts()
    
    if duplicate_rows:
        # Ask for confirmation before deleting
        user_input = input(f"Found {len(duplicate_rows)} duplicate rows. Delete them? (y/n): ")
        
        if user_input.lower() == 'y':
            batch_size = 5
            logger.info(f"Deleting duplicate rows in batches of {batch_size}")
            
            # Delete duplicate rows
            deleted, failed = await delete_duplicate_rows(duplicate_rows, batch_size=batch_size)
            
            if failed > 0:
                logger.warning(f"{failed} rows failed to delete. You may need to run the script again.")
            
            logger.info("Cleanup completed")
        else:
            logger.info("Cleanup cancelled")
    else:
        logger.info("No duplicate rows found")

if __name__ == "__main__":
    asyncio.run(main())