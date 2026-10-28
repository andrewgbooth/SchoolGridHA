"""Home Assistant integration tests with the SchoolGrid API patched out."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.schoolgrid.api import AuthError
from custom_components.schoolgrid.const import DOMAIN

from . import data

NOW = "2026-10-28 12:00:00+00:00"  # Wednesday of half term
P = "custom_components.schoolgrid.api.SchoolGridApi"


@pytest.fixture
def api():
    with patch(f"{P}.accounts", AsyncMock(return_value=data.ACCOUNTS)) as acc, \
         patch(f"{P}.menus", AsyncMock(side_effect=lambda cid, s, e: data.menus(s, e))), \
         patch(f"{P}.orders", AsyncMock(side_effect=lambda cid, s, e: [o for o in data.ORDERS if s <= o["mealDate"][:10] <= e])) as orders, \
         patch(f"{P}.service_types", AsyncMock(return_value=[{"id": 3632, "clientServiceTypeId": 10}])), \
         patch(f"{P}.insert_order", AsyncMock(return_value={"orderId": 9, "isSoldOut": False})) as insert:
        yield type("Api", (), {"accounts": acc, "orders": orders, "insert": insert})


async def setup(hass, freezer):
    freezer.move_to(NOW)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1378505", data={"username": "me@x.com", "password": "pw"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_states(hass: HomeAssistant, freezer, api):
    entry = await setup(hass, freezer)
    assert entry.state is ConfigEntryState.LOADED
    s = lambda e: hass.states.get(f"sensor.theodore_booth_{e}")
    assert s("lunch_next_monday").state == "Baked Potato with Baked Beans"
    assert s("lunch_next_monday").attributes["date"] == "2026-11-02"
    assert s("lunch_next_tuesday").attributes["dessert"] == "Fresh Fruit"
    assert s("lunch_this_wednesday").state == "No school"          # half-term holiday flag
    assert s("lunch_next_wednesday").state == "Not ordered"
    assert s("lunch_next_wednesday").attributes["can_order"] is True
    # sold-out and sub-choice dishes are not offered
    assert s("lunch_next_wednesday").attributes["main_options"] == [
        "Baked Potato with Baked Beans", "Baked Potato with Baked Beans & Cheese"]
    assert s("food_balance").state == "0.0"
    b = hass.states.get("binary_sensor.theodore_booth_lunch_orders_missing")
    assert b.state == "on"
    assert b.attributes["dates"] == ["2026-11-04", "2026-11-05", "2026-11-06"]
    # 20 weekday sensors? 2 weeks x 5 = 10 day sensors + balance
    assert len([x for x in hass.states.async_entity_ids("sensor") if "lunch_" in x]) == 10


async def test_weekend_rolls_to_next_week(hass, freezer, api):
    freezer.move_to("2026-10-31 12:00:00+00:00")
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1378505", data={"username": "u", "password": "p"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.theodore_booth_lunch_this_monday").attributes["date"] == "2026-11-02"


async def test_place_order(hass, freezer, api):
    await setup(hass, freezer)
    await hass.services.async_call(
        DOMAIN, "place_order", {"entity_id": "sensor.theodore_booth_lunch_next_wednesday", "main": "beans & cheese", "dessert": "yogurt"},
        blocking=True)
    payload = api.insert.call_args.args[0]
    assert payload == {
        "id": 0, "customerId": 1467173, "mealDate": "2026-11-04T00:00:00", "mainCourseId": 96662, "dessertId": 99369,
        "customOrder": None, "menuAssignmentId": 33123, "isLocked": True, "schoolServiceTypeId": 3632,
        "schoolId": 3877, "yearId": 1}


@pytest.mark.parametrize("entity,main,msg", [
    ("lunch_next_monday", "Cheese Roll", "already has an order"),            # no changing orders
    ("lunch_this_wednesday", "Baked Potato with Baked Beans", "No lunch service"),
    ("lunch_next_wednesday", "Cheese Roll with Nachos", "sold out"),
    ("lunch_next_wednesday", "Build your own wrap", "sub-choice"),
    ("lunch_next_wednesday", "pizza", "not found"),
    ("lunch_next_wednesday", "baked potato", "ambiguous"),
])
async def test_place_order_refusals(hass, freezer, api, entity, main, msg):
    await setup(hass, freezer)
    with pytest.raises(ServiceValidationError, match=msg):
        await hass.services.async_call(
            DOMAIN, "place_order", {"entity_id": f"sensor.theodore_booth_{entity}", "main": main}, blocking=True)
    api.insert.assert_not_called()


async def test_refuses_if_ordered_elsewhere_since_last_poll(hass, freezer, api):
    await setup(hass, freezer)
    api.orders.side_effect = lambda *a: [{"preorderId": 1}]
    with pytest.raises(ServiceValidationError, match="already has an order"):
        await hass.services.async_call(
            DOMAIN, "place_order", {"entity_id": "sensor.theodore_booth_lunch_next_wednesday", "main": "Baked Potato with Baked Beans"},
            blocking=True)
    api.insert.assert_not_called()


async def test_auth_failure_starts_reauth(hass, freezer, api):
    api.accounts.side_effect = AuthError("bad")
    entry = await setup(hass, freezer)
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
