# SchoolGrid School Lunches for Home Assistant

Shows what your child has ordered for school lunch **today** and **tomorrow**, and warns you when an
order is missing. **Read-only**: it never places, changes or cancels an order. It works with parent
accounts on app.schoolgrid.co.uk and uses the website's own (unofficial) API, so it could break if
SchoolGrid change their site.

## Install
- **HACS:** add `https://github.com/andrewgbooth/SchoolGridHA` as a custom repository (type *Integration*),
  install, restart Home Assistant.
- **Manual:** copy `custom_components/schoolgrid` into `/config/custom_components/`, restart.

Then *Settings → Devices & services → Add integration → SchoolGrid* and enter your SchoolGrid email
and password. The password is stored in Home Assistant's config entry (`.storage`), like any
integration that logs in. If SchoolGrid rejects it later, Home Assistant asks you to re-enter it.

## Entities (one device per child)
| Entity | State |
|---|---|
| `sensor.<child>_lunch_today` | the ordered main course, or `Not ordered` / `No school` |
| `sensor.<child>_lunch_tomorrow` | same, for tomorrow |
| `sensor.<child>_dessert_today` | the chosen dessert, or `No dessert` / `Not ordered` / `No school` |
| `sensor.<child>_dessert_tomorrow` | same, for tomorrow |
| `sensor.<child>_food_balance` | account balance (GBP) |
| `binary_sensor.<child>_lunch_orders_missing` | on if today or tomorrow is a school day with no order |

- `No school` is shown on weekends and school holidays. These never count as a missing order.
- The dessert has its own sensors so it shows on dashboards without opening attributes. The lunch sensors
  also carry it as the `dessert` attribute, plus `date` and `status` (`ordered`, `not_ordered`, `holiday`, `no_menu`).
- The missing-orders sensor lists the affected days in its `dates` attribute.
- Data refreshes every 30 minutes and again just after midnight, when "today" and "tomorrow" move on.

## Icon
The integration ships the SchoolGrid logo in `custom_components/schoolgrid/brand/`, so it shows in
*Devices & services* instead of "icon not available". Recent Home Assistant releases load brand images
from this folder; older ones ignore it and keep showing the placeholder. The logo is SchoolGrid's, used here
only to identify the service this integration connects to.

## Example: remind me in the evening
```yaml
triggers:
  - trigger: time
    at: "18:00"
conditions:
  - condition: state
    entity_id: binary_sensor.theodore_booth_lunch_orders_missing
    state: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: >
        School lunch not ordered for
        {{ state_attr('binary_sensor.theodore_booth_lunch_orders_missing', 'dates') | join(', ') }}
```

## Upgrading
**0.3** adds the dessert sensors and the logo; nothing to do.

**From 0.1:** 0.1 had per-weekday sensors and an ordering service. 0.2 replaces them with the entities above and no
longer has any ordering. Delete the old `sensor.*_lunch_this_*` / `*_lunch_next_*` entities after upgrading.

## Development
```
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python pytest-homeassistant-custom-component
.venv/bin/python -m pytest
```
