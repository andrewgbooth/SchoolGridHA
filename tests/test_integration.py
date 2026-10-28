"""Home Assistant integration tests with the SchoolGrid API patched out."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.schoolgrid.api import AuthError
from custom_components.schoolgrid.const import DOMAIN

from . import data

P = "custom_components.schoolgrid.api.SchoolGridApi"


@pytest.fixture
def api():
    with patch(f"{P}.accounts", AsyncMock(return_value=data.ACCOUNTS)) as acc, \
         patch(f"{P}.menus", AsyncMock(side_effect=lambda cid, s, e: data.menus(s, e))) as menus, \
         patch(f"{P}.orders", AsyncMock(side_effect=lambda cid, s, e: [o for o in data.ORDERS if s <= o["mealDate"][:10] <= e])):
        yield type("Api", (), {"accounts": acc, "menus": menus})


async def setup(hass, freezer, now):
    freezer.move_to(now)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1378505", data={"username": "me@x.com", "password": "pw"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def read(hass):
    g = lambda e: hass.states.get(e)
    return (g("sensor.theodore_booth_lunch_today"), g("sensor.theodore_booth_lunch_tomorrow"),
            g("binary_sensor.theodore_booth_lunch_orders_missing"))


async def test_both_days_ordered_with_dessert(hass: HomeAssistant, freezer, api):
    entry = await setup(hass, freezer, "2026-11-02 12:00:00+00:00")  # Monday
    assert entry.state is ConfigEntryState.LOADED
    today, tomorrow, missing = read(hass)
    assert today.state == "Baked Potato with Baked Beans"
    assert today.attributes["dessert"] is None
    assert today.attributes["date"] == "2026-11-02"
    assert tomorrow.state == "Baked Potato with Baked Beans"
    assert tomorrow.attributes["dessert"] == "Fresh Fruit"
    assert missing.state == "off"
    assert hass.states.get("sensor.theodore_booth_food_balance").state == "0.0"
    # the dessert is its own entity, not just an attribute
    assert hass.states.get("sensor.theodore_booth_dessert_today").state == "No dessert"
    assert hass.states.get("sensor.theodore_booth_dessert_tomorrow").state == "Fresh Fruit"
    assert hass.states.get("sensor.theodore_booth_dessert_tomorrow").attributes["date"] == "2026-11-03"
    assert hass.states.get("sensor.theodore_booth_dessert_tomorrow").attributes["icon"] == "mdi:cupcake"


async def test_nothing_ordered_flags_today_and_tomorrow(hass, freezer, api):
    await setup(hass, freezer, "2026-11-04 12:00:00+00:00")  # Wednesday
    today, tomorrow, missing = read(hass)
    assert today.state == tomorrow.state == "Not ordered"
    assert hass.states.get("sensor.theodore_booth_dessert_today").state == "Not ordered"
    assert missing.state == "on"
    assert missing.attributes["dates"] == ["2026-11-04", "2026-11-05"]


async def test_friday_tomorrow_is_weekend(hass, freezer, api):
    await setup(hass, freezer, "2026-11-06 12:00:00+00:00")
    today, tomorrow, missing = read(hass)
    assert today.state == "Not ordered"
    assert tomorrow.state == "No school"
    assert missing.attributes["dates"] == ["2026-11-06"]       # the weekend never counts


async def test_weekend_is_no_school_and_not_missing(hass, freezer, api):
    await setup(hass, freezer, "2026-11-07 12:00:00+00:00")  # Saturday
    today, tomorrow, missing = read(hass)
    assert today.state == tomorrow.state == "No school"
    assert hass.states.get("sensor.theodore_booth_dessert_today").state == "No school"
    assert hass.states.get("sensor.theodore_booth_dessert_tomorrow").state == "No school"
    assert missing.state == "off"


async def test_weekend_is_no_school_even_if_api_has_a_menu(hass, freezer, api):
    api.menus.side_effect = lambda cid, s, e: [data.day(__import__("datetime").date.fromisoformat(s)),
                                                data.day(__import__("datetime").date.fromisoformat(e))]
    await setup(hass, freezer, "2026-11-07 12:00:00+00:00")
    today, tomorrow, _ = read(hass)
    assert today.state == tomorrow.state == "No school"


async def test_school_holiday(hass, freezer, api):
    await setup(hass, freezer, "2026-10-28 12:00:00+00:00")  # half term
    today, tomorrow, missing = read(hass)
    assert today.state == tomorrow.state == "No school"
    assert missing.state == "off"


async def test_rolls_over_at_midnight(hass, freezer, api):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    await setup(hass, freezer, "2026-11-02 12:00:00-08:00")
    assert read(hass)[0].attributes["date"] == "2026-11-02"
    from datetime import datetime
    local = datetime(2026, 11, 3, 0, 5, 0, tzinfo=dt_util.get_default_time_zone())  # refresh is at 00:05 local time
    freezer.move_to(local)
    async_fire_time_changed(hass, local)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert read(hass)[0].attributes["date"] == "2026-11-03"
    assert read(hass)[0].attributes["dessert"] == "Fresh Fruit"


async def test_no_services_registered(hass, freezer, api):
    await setup(hass, freezer, "2026-11-02 12:00:00+00:00")
    assert not hass.services.async_services_for_domain(DOMAIN)


async def test_auth_failure_starts_reauth(hass, freezer, api):
    api.accounts.side_effect = AuthError("bad")
    entry = await setup(hass, freezer, "2026-11-02 12:00:00+00:00")
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_config_flow(hass, api):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] is FlowResultType.FORM
    api.accounts.side_effect = AuthError("nope")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"username": " me@x.com ", "password": "bad"})
    assert r["errors"] == {"base": "invalid_auth"}
    api.accounts.side_effect = None
    api.accounts.return_value = data.ACCOUNTS
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"username": " me@x.com ", "password": "good"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"username": "me@x.com", "password": "good"}
    assert r["result"].unique_id == "1378505"


def test_brand_images_ship_with_the_integration():
    """HA serves custom-integration brand images from <integration>/brand/ (icon + logo, with @2x)."""
    from pathlib import Path
    from PIL import Image
    brand = Path(__file__).parent.parent / "custom_components" / "schoolgrid" / "brand"
    sizes = {"icon.png": (256, 256), "icon@2x.png": (512, 512)}
    for name, size in sizes.items():
        assert Image.open(brand / name).size == size
    for name, height in (("logo.png", 256), ("logo@2x.png", 512)):
        assert Image.open(brand / name).height == height
    assert all(Image.open(brand / n).mode == "RGBA" for n in (*sizes, "logo.png", "logo@2x.png"))
