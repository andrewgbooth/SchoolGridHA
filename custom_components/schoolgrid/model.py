"""Pure parsing of SchoolGrid API data (no Home Assistant imports, so it is easy to test)."""
from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import date

from .const import STATUS_HOLIDAY, STATUS_NO_MENU, STATUS_NOT_ORDERED, STATUS_ORDERED


@dataclass
class Child:
    id: int
    name: str
    first_name: str
    school_name: str
    balance: float


@dataclass
class DayInfo:
    date: date
    status: str
    main: str | None = None
    dessert: str | None = None
    main_allergens: str | None = None
    dessert_allergens: str | None = None

    @property
    def allergens(self) -> str | None:
        """Allergens of the main and dessert combined, e.g. "Milk, Wheat"."""
        found: list[str] = []
        for text in (self.main_allergens, self.dessert_allergens):
            for item in (text or "").split(","):
                item = item.strip()
                if item and item.lower() not in (f.lower() for f in found):
                    found.append(item)
        return ", ".join(found) or None


_TRAILING_BRACKETS = re.compile(r"\s*\(([^()]*)\)\s*$")


def split_allergens(name: str) -> tuple[str, str | None]:
    """Split "Cheese Roll (Milk, Wheat)" into ("Cheese Roll", "Milk, Wheat")."""
    name = name.strip()
    m = _TRAILING_BRACKETS.search(name)
    if not m or not m.start():
        return name, None
    return name[: m.start()].strip(), m.group(1).strip() or None


def parse_children(accounts: dict) -> list[Child]:
    return [
        Child(
            id=c["Id"], name=c["FullName"], first_name=c["FirstName"], school_name=sa["SchoolName"],
            balance=float(c.get("FoodBalance") or 0),
        )
        for sa in accounts.get("SchoolAccounts", [])
        for c in sa.get("CustomerAccounts", [])
        if c.get("IsActive") and not c.get("IsRemoved")
    ]


def parse_days(menus: list[dict], orders: list[dict]) -> dict[date, DayInfo]:
    """Status and ordered dishes for each day in the menu response."""
    by_date = {o["mealDate"][:10]: o for o in orders}
    days: dict[date, DayInfo] = {}
    for day in menus:
        d = date.fromisoformat(day["orderDay"][:10])
        lunch = next((s for s in day.get("serviceMealOrderDay", []) if s.get("serviceName", "").lower() == "lunch"), None)
        names: dict[int, tuple[str, str | None]] = {}
        has_mains = False
        for course in (lunch or {}).get("courses", []):
            if course.get("courseName") in ("Mains", "Desserts"):
                has_mains = has_mains or (course["courseName"] == "Mains" and bool(course.get("dishes")))
                names.update({x["recipeId"]: split_allergens(x["recipeName"]) for x in course.get("dishes", [])})
        order = by_date.get(d.isoformat())
        if order:
            main_id, dessert_id = order.get("mainCourseId"), order.get("dessertId")
            main, main_allergens = names.get(main_id, (f"Recipe {main_id}", None)) if main_id else (None, None)
            dessert, dessert_allergens = (
                names.get(dessert_id, (f"Recipe {dessert_id}", None)) if dessert_id else (None, None)
            )
            days[d] = DayInfo(d, STATUS_ORDERED, main, dessert, main_allergens, dessert_allergens)
        elif day.get("holiday") or d.weekday() >= 5 or lunch is None or not has_mains:
            days[d] = DayInfo(d, STATUS_HOLIDAY)
        else:
            days[d] = DayInfo(d, STATUS_NOT_ORDERED)
    return days


def no_menu(d: date) -> DayInfo:
    return DayInfo(date=d, status=STATUS_NO_MENU)
