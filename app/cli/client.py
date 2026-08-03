"""HTTP client shared by Nutrition Tracker CLI commands."""

from dataclasses import dataclass
from typing import Any

import click
import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class APIClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, str]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=10,
            )
        except httpx.RequestError as exc:
            raise click.ClickException(
                f"Could not connect to {self.base_url}: {exc}"
            ) from exc

        if response.is_error:
            try:
                body = response.json()
                detail = body.get("detail", body) if isinstance(body, dict) else body
            except ValueError:
                detail = response.text or response.reason_phrase
            raise click.ClickException(
                f"API request failed ({response.status_code}): {detail}"
            )

        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise click.ClickException("API returned an invalid JSON response") from exc


@dataclass(frozen=True)
class CLIContext:
    client: APIClient
    json_output: bool = False
