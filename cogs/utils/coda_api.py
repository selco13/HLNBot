import aiohttp
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger('coda_api')
logger.setLevel(logging.DEBUG)

class CodaRateLimiter:
    """Handles rate limiting for Coda API requests based on global rate limits."""
    
    def __init__(self):
        self.global_rate_limit_reset = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Wait until the global rate limit has reset."""
        async with self.lock:
            now = time.time()
            if now < self.global_rate_limit_reset:
                wait_time = self.global_rate_limit_reset - now
                logger.warning(f"Global rate limit active. Sleeping for {wait_time:.2f} seconds.")
                await asyncio.sleep(wait_time)

    def update_limits(self, headers: Dict[str, str]):
        """Update rate limit info from response headers."""
        try:
            limit = headers.get('X-RateLimit-Limit')
            remaining = headers.get('X-RateLimit-Remaining')
            reset = headers.get('X-RateLimit-Reset')
            
            if reset:
                reset_time = float(reset)
                self.global_rate_limit_reset = reset_time
                logger.debug(f"Rate limit reset time updated to {datetime.fromtimestamp(reset_time)}")
            
            if remaining is not None:
                remaining = int(remaining)
                logger.debug(f"Rate limit remaining: {remaining}/{limit}")
                if remaining == 0 and reset:
                    logger.warning("Rate limit exhausted. Awaiting reset.")
        except Exception as e:
            logger.error(f"Error updating rate limits: {e}")

class CodaRequestError(Exception):
    """Custom exception for Coda API request errors."""
    pass

class CodaAPIClient:
    """Enhanced Coda API client with global rate limiting and robust error handling."""
    
    def __init__(self, api_token: str, base_url: str = "https://coda.io/apis/v1"):
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = CodaRateLimiter()
        self.session_lock = asyncio.Lock()

    async def ensure_session(self):
        async with self.session_lock:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Coda API session closed.")

    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        backoff_factor: float = 1.5
    ) -> Optional[Dict[str, Any]]:
        await self.ensure_session()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

        attempt = 0
        while attempt <= retries:
            try:
                await self.rate_limiter.acquire()

                async with self.session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=30
                ) as response:
                    self.rate_limiter.update_limits(response.headers)
                    response_text = await response.text()
                    
                    logger.debug(f"Request URL: {url}")
                    logger.debug(f"Request Method: {method.upper()}")
                    logger.debug(f"Request Params: {params}")
                    logger.debug(f"Request Data: {data}")
                    logger.debug(f"Response Status: {response.status}")
                    logger.debug(f"Response Headers: {dict(response.headers)}")
                    logger.debug(f"Response Text: {response_text}")

                    if response.status in (200, 201, 202):
                        if response.content_type == 'application/json':
                            return await response.json()
                        else:
                            logger.warning(f"Unexpected content type: {response.content_type}")
                            return {}
                    
                    elif response.status == 429:
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            wait_time = float(retry_after)
                            logger.warning(f"Rate limited by Coda API. Retrying after {wait_time}s.")
                            await asyncio.sleep(wait_time)
                        else:
                            wait_time = backoff_factor ** attempt
                            logger.warning(f"Rate limited by Coda API. Retrying after {wait_time}s.")
                            await asyncio.sleep(wait_time)
                        attempt += 1
                        continue

                    elif 500 <= response.status < 600:
                        if attempt < retries:
                            wait_time = backoff_factor ** attempt
                            logger.info(f"Server error ({response.status}). Retrying in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            attempt += 1
                            continue
                        else:
                            logger.error(f"Server error ({response.status}) after {retries} retries.")
                            raise CodaRequestError(f"Server error: {response.status} - {response_text}")
                    else:
                        logger.error(f"Coda API client error ({response.status}): {response_text}")
                        raise CodaRequestError(f"Client error: {response.status} - {response_text}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < retries:
                    wait_time = backoff_factor ** attempt
                    logger.error(f"Request error: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    attempt += 1
                    continue
                else:
                    logger.critical(f"Request failed after {retries} retries: {e}")
                    raise CodaRequestError(f"Request failed: {e}") from e

            except Exception as e:
                logger.critical(f"Unexpected error during Coda API request: {e}")
                raise CodaRequestError(f"Unexpected error: {e}") from e

        logger.error(f"Failed to make request to {url} after {retries} retries.")
        return None

    async def get_rows(
        self,
        doc_id: str,
        table_id: str,
        query: Optional[str] = None,
        use_column_names: bool = True,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        endpoint = f"docs/{doc_id}/tables/{table_id}/rows"
        params = {
            'useColumnNames': str(use_column_names).lower(),
        }
        if query:
            params['query'] = query
        if limit:
            params['limit'] = limit

        rows = []
        next_page_token = None

        while True:
            if next_page_token:
                params['pageToken'] = next_page_token

            response = await self.request('GET', endpoint, params=params)
            if not response:
                logger.error("Failed to retrieve rows from Coda.")
                break

            items = response.get('items', [])
            rows.extend(items)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        return rows
     
    async def update_row(
        self,
        doc_id: str,
        table_id: str,
        row_id: str,
        cells: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Update a row with cell data."""
        endpoint = f'docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        return await self.request('PUT', endpoint, data={'row': {'cells': cells}})
    
    async def update_row_with_name(
        self,
        doc_id: str,
        table_id: str,
        row_id: str,
        cells: List[Dict[str, Any]],
        new_name: str
    ) -> Optional[Dict[str, Any]]:
        """Update a row with cell data and change its name."""
        endpoint = f'docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        return await self.request(
            'PUT', 
            endpoint, 
            data={'row': {'cells': cells, 'name': new_name}}
        )
    
    async def get_row(
        self,
        doc_id: str,
        table_id: str,
        row_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single row by ID."""
        endpoint = f'docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        return await self.request('GET', endpoint)
    
    async def get_columns(
        self,
        doc_id: str,
        table_id: str
    ) -> List[Dict[str, Any]]:
        """Get all columns in a table."""
        endpoint = f'docs/{doc_id}/tables/{table_id}/columns'
        response = await self.request('GET', endpoint)
        if response and 'items' in response:
            return response['items']
        return []
