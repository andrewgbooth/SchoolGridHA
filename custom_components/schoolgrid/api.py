"""Async client for the SchoolGrid parent web app (app.schoolgrid.co.uk).

The site is an ASP.NET WebForms login followed by an Angular SPA that uses a JSON API under /api.
There is deliberately no method for cancelling or changing an order.
"""
from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser
from typing import Any

import aiohttp

from .const import BASE_URL

LOGIN_PATH = "/login.aspx"
_FIELD = "ctl00$ctl00$bodyContent$bodyContent$"


class SchoolGridError(Exception):
    """Any failure talking to SchoolGrid."""


class AuthError(SchoolGridError):
    """Login rejected (bad credentials) or login page layout changed."""


class _HiddenFields(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "input" and a.get("type") == "hidden" and a.get("name"):
            self.fields[a["name"]] = a.get("value") or ""


class SchoolGridApi:
    """Logs in with username/password and keeps the session cookie alive."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session  # must have its own cookie jar
        self._username = username.strip()
        self._password = password
        self._lock = asyncio.Lock()
        self._logged_in = False

    async def login(self) -> None:
        async with self._lock:
            self._session.cookie_jar.clear()
            self._logged_in = False
            try:
                async with self._session.get(
                    BASE_URL + LOGIN_PATH, headers={"Accept": "text/html"}, allow_redirects=False
                ) as resp:
                    parser = _HiddenFields()
                    parser.feed(await resp.text())
                if "__VIEWSTATE" not in parser.fields:
                    raise AuthError("Login page layout changed (no __VIEWSTATE)")
                form = {
                    **parser.fields,
                    "__EVENTTARGET": _FIELD + "btnLogin",
                    "__EVENTARGUMENT": "",
                    _FIELD + "username": self._username,
                    _FIELD + "password": self._password,
                }
                async with self._session.post(
                    BASE_URL + LOGIN_PATH, data=form, headers={"Accept": "text/html"}, allow_redirects=False
                ) as resp:
                    status, location = resp.status, resp.headers.get("Location", "")
            except (aiohttp.ClientError, TimeoutError) as err:
                raise SchoolGridError(f"Cannot reach SchoolGrid: {err}") from err
            # Success is a redirect into the app; a 200 means the login page re-rendered with an error.
            if status not in (301, 302, 303) or "login.aspx" in location.lower():
                raise AuthError("SchoolGrid rejected the username or password")
            self._logged_in = True

    async def _request(self, method: str, path: str, *, body: Any = None, retry: bool = True) -> Any:
        if not self._logged_in:
            await self.login()
        try:
            async with self._session.request(
                method,
                BASE_URL + path,
                json=body,
                headers={"Accept": "application/json"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                expired = resp.status in (301, 302, 303, 401, 403) or "text/html" in resp.headers.get("Content-Type", "")
                if not expired:
                    resp.raise_for_status()
                    text = await resp.text()
                    return json.loads(text) if text else None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SchoolGridError(f"Request to SchoolGrid failed: {err}") from err
        # Session expired: log in again and retry once (nothing was processed, so POSTs are safe to repeat).
        if not retry:
            raise AuthError("SchoolGrid still rejects the session after logging in")
        await self.login()
        return await self._request(method, path, body=body, retry=False)

    async def accounts(self) -> dict:
        return await self._request("GET", "/api/Parent/GetCurrentUserAndAccounts")

    async def menus(self, customer_id: int, start: str, end: str) -> list[dict]:
        return await self._request("GET", f"/api/MealOrder/GetCustomerMenus/{customer_id}/{start}/{end}/true")

    async def orders(self, customer_id: int, start: str, end: str) -> list[dict]:
        return await self._request("GET", f"/api/MealOrder/GetCustomerMealOrders/{customer_id}/{start}/{end}")

    async def service_types(self, school_id: int, client_id: int) -> list[dict]:
        return await self._request(
            "GET", f"/api/MealServiceType/GetSchoolServiceTypesForSchoolAccountOrder/{school_id}/{client_id}"
        )

    async def insert_order(self, payload: dict) -> dict:
        return await self._request("POST", "/api/MealOrder/Insert", body=payload)
