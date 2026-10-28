# SchoolGrid School Lunches for Home Assistant

Shows what your child has ordered for school lunch, day by day, and lets you place orders from
Home Assistant. Works with parent accounts on app.schoolgrid.co.uk. It uses the website's own
(unofficial) API, so it could break if SchoolGrid changes their site.

## Install
- **HACS:** add this repo as a custom repository (type *Integration*), install, restart.
- **Manual:** copy `custom_components/schoolgrid` into `/config/custom_components/`, restart.

Then *Settings → Devices & services → Add integration → SchoolGrid* and enter your SchoolGrid
email and password. The password is stored in Home Assistant's config entry (`.storage`), like any
integration that logs in. If it is ever rejected, HA asks you to re-enter it.

## Entities (per child, one device each)
| Entity | State |
|---|---|
| `sensor.<child>_lunch_this_monday` … `_friday` | the ordered main, or `Not ordered` / `No order` (past) / `No school` / `No menu yet` |
| `sensor.<child>_lunch_next_monday` … `_friday` | same, for next week (*Configure* → weeks 1-4; +2w, +3w for later weeks) |
| `sensor.<child>_food_balance` | account balance (GBP) |
| `binary_sensor.<child>_lunch_orders_missing` | on if any *future* school day with a menu has no order |

"This week" rolls to the following week on Saturday. Day sensor attributes: `date`, `status`,
`dessert`, `order_id`, `can_order`, `main_options`, `dessert_options`. Data refreshes every 30 minutes
and just after midnight.

## Placing an order
Service `schoolgrid.place_order`, targeted at a day sensor. `main` (and optional `dessert`) match a
name from `main_options` / `dessert_options`, or part of one. Main and dessert must be ordered
together. **It can only place orders: it refuses if the day already has one, and there is no way to
change or cancel from Home Assistant** (do that on the website). Sold-out dishes and dishes that need a
sub-choice are refused.

```yaml
action: schoolgrid.place_order
target:
  entity_id: sensor.theodore_booth_lunch_next_wednesday
data:
  main: Baked Potato with Baked Beans
  dessert: Fresh Fruit
```

## Example: Sunday reminder
```yaml
triggers:
  - trigger: time
    at: "18:00"
conditions:
  - condition: time
    weekday: [sun]
  - condition: state
    entity_id: binary_sensor.theodore_booth_lunch_orders_missing
    state: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: "School lunches not ordered for {{ state_attr('binary_sensor.theodore_booth_lunch_orders_missing','dates') | join(', ') }}"
```

## Development
`uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python pytest-homeassistant-custom-component && .venv/bin/python -m pytest`
