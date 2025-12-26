"""WHOOP API client with automatic token refresh."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv, set_key

from whoop_mcp.models import Recovery, Sleep, Cycle, Workout

# Find .env file (check multiple locations)
def find_env_file() -> Path:
    """Find the .env file, checking multiple locations."""
    locations = [
        Path(__file__).parent.parent.parent / ".env",  # Project root
        Path.cwd() / ".env",  # Current directory
    ]
    for path in locations:
        if path.exists():
            return path
    return locations[0]  # Default to project root


ENV_PATH = find_env_file()
load_dotenv(ENV_PATH)


class WhoopAuthError(Exception):
    """Authentication error with WHOOP API."""
    pass


class WhoopAPIError(Exception):
    """General WHOOP API error."""
    pass


class WhoopClient:
    """Async client for WHOOP API with automatic token refresh."""

    BASE_URL = "https://api.prod.whoop.com/developer"
    TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

    def __init__(self):
        """Initialize the client with tokens from environment."""
        self.client_id = os.getenv("WHOOP_CLIENT_ID")
        self.client_secret = os.getenv("WHOOP_CLIENT_SECRET")
        self.access_token = os.getenv("WHOOP_ACCESS_TOKEN")
        self.refresh_token = os.getenv("WHOOP_REFRESH_TOKEN")

        if not self.access_token:
            raise WhoopAuthError(
                "No access token found. Run 'uv run python scripts/get_tokens.py' first."
            )

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            raise WhoopAuthError("No refresh token available. Re-run get_tokens.py")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "scope": "offline",
                },
            )

            if response.status_code != 200:
                raise WhoopAuthError(f"Token refresh failed: {response.text}")

            tokens = response.json()
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens.get("refresh_token", self.refresh_token)

            # Save new tokens to .env
            set_key(str(ENV_PATH), "WHOOP_ACCESS_TOKEN", self.access_token)
            if tokens.get("refresh_token"):
                set_key(str(ENV_PATH), "WHOOP_REFRESH_TOKEN", self.refresh_token)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        retry_on_401: bool = True,
    ) -> dict:
        """Make an authenticated request to the WHOOP API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, params=params)

            # Handle token expiration
            if response.status_code == 401 and retry_on_401:
                await self._refresh_access_token()
                return await self._request(method, endpoint, params, retry_on_401=False)

            if response.status_code == 429:
                raise WhoopAPIError("Rate limit exceeded. Try again later.")

            if response.status_code != 200:
                raise WhoopAPIError(f"API error {response.status_code}: {response.text}")

            return response.json()

    async def _paginated_request(
        self,
        endpoint: str,
        limit: int,
        max_per_page: int = 25,
    ) -> list[dict]:
        """Fetch paginated results up to the requested limit."""
        all_records = []
        next_token = None

        while len(all_records) < limit:
            page_limit = min(max_per_page, limit - len(all_records))
            params = {"limit": page_limit}
            if next_token:
                params["nextToken"] = next_token

            data = await self._request("GET", endpoint, params=params)
            records = data.get("records", [])
            all_records.extend(records)

            next_token = data.get("next_token")
            if not next_token or not records:
                break

        return all_records[:limit]

    async def get_recovery(self, limit: int = 1) -> list[Recovery]:
        """Get recent recovery records (supports up to 30 days via pagination)."""
        records = await self._paginated_request("/v2/recovery", limit)
        return [Recovery.model_validate(record) for record in records]

    async def get_today_recovery(self) -> Optional[Recovery]:
        """Get today's recovery data."""
        records = await self.get_recovery(limit=1)
        return records[0] if records else None

    async def get_sleep(self, limit: int = 1) -> list[Sleep]:
        """Get recent sleep records (supports up to 30 days via pagination)."""
        records = await self._paginated_request("/v2/activity/sleep", limit)
        return [Sleep.model_validate(record) for record in records]

    async def get_last_sleep(self) -> Optional[Sleep]:
        """Get the most recent sleep record (main sleep, not nap)."""
        # Get more records to find main sleep
        records = await self.get_sleep(limit=5)
        for record in records:
            if not record.nap:
                return record
        return records[0] if records else None

    async def get_cycles(self, limit: int = 7) -> list[Cycle]:
        """Get recent physiological cycles (for strain data)."""
        data = await self._request("GET", "/v2/cycle", params={"limit": limit})
        return [Cycle.model_validate(record) for record in data.get("records", [])]

    async def get_recovery_trend(self, days: int = 7) -> list[Recovery]:
        """Get recovery trend for the last N days."""
        return await self.get_recovery(limit=days)

    async def get_workouts(self, limit: int = 10) -> list[Workout]:
        """Get recent workout records."""
        data = await self._request("GET", "/v2/activity/workout", params={"limit": limit})
        return [Workout.model_validate(record) for record in data.get("records", [])]
