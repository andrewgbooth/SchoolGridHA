"""Pure parsing of SchoolGrid API data (no Home Assistant imports, so it is easy to test)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .const import STATUS_HOLIDAY, STATUS_NO_MENU, STATUS_NOT_ORDERED, STATUS_ORDERED, STATUS_PAST


@dataclass(frozen=True)
class Dish:
    recipe_id: int
    name: str
    allergens: tuple[str, ...]
    sold_out: bool
    needs_choice: bool  # has a sub-choice (e.g. filling) that this integration can't select


@dataclass
class Child:
    id: int
    name: str
    first_name: str
    school_id: int
    school_name: str
    client_id: int
    year_id: int
    balance: float


@dataclass
class DayInfo:
    date: date
    status: str
    main: str | None = None
    dessert: str | None = None
    order_id: int | None = None
    mains: list[Dish] = field(default_factory=list)
    desserts: list[Dish] = field(default_factory=list)
    menu_assignment_id: int | None = None
    service_id: int | None = None


def week_start(today: date) -> date:
    """Monday of the current week, or the coming Monday on Saturday/Sunday."""
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=7) if today.weekday() >= 5 else monday


def parse_children(accounts: dict) -> list[Child]:
    out = []
    for sa in accounts.get("SchoolAccounts", []):
        for c in sa.get("CustomerAccounts", []):
            if c.get("IsActive") and not c.get("IsRemoved"):
                out.append(
                    Child(
                        id=c["Id"], name=c["FullName"], first_name=c["FirstName"], school_id=sa["SchoolId"],
                        school_name=sa["SchoolName"], client_id=sa["ClientId"], year_id=c["YearId"],
                        balance=float(c.get("FoodBalance") or 0),
                    )
                )
    return out


def _dishes(course: dict) -> list[Dish]:
    return [
        Dish(
            recipe_id=d["recipeId"],
            name=d["recipeName"].strip(),
            allergens=tuple(sorted({a["name"] for a in d.get("recipeAllergens", [])})),
            sold_out=bool(d.get("soldOut")),
            needs_choice=bool(d.get("choiceRecipe")),
        )
        for d in course.get("dishes", [])
    ]


def parse_days(menus: list[dict], orders: list[dict], today: date) -> dict[date, DayInfo]:
    by_date = {o["mealDate"][:10]: o for o in orders}
    days: dict[date, DayInfo] = {}
    for day in menus:
        d = date.fromisoformat(day["orderDay"][:10])
        lunch = next((s for s in day.get("serviceMealOrderDay", []) if s.get("serviceName", "").lower() == "lunch"), None)
        mains: list[Dish] = []
        desserts: list[Dish] = []
        if lunch:
            for course in lunch.get("courses", []):
                if course.get("courseName") == "Mains" and course.get("preorderAvailable"):
                    mains = _dishes(course)
                elif course.get("courseName") == "Desserts" and course.get("preorderAvailable"):
                    desserts = _dishes(course)
        info = DayInfo(
            date=d, status=STATUS_NOT_ORDERED, mains=mains, desserts=desserts,
            menu_assignment_id=lunch.get("menuAssignmentId") if lunch else None,
            service_id=lunch.get("serviceId") if lunch else None,
        )
        order = by_date.get(d.isoformat())
        if order:
            names = {x.recipe_id: x.name for x in mains + desserts}
            info.status = STATUS_ORDERED
            info.order_id = order.get("preorderId")
            info.main = names.get(order.get("mainCourseId"), f"Recipe {order.get('mainCourseId')}")
            if order.get("dessertId"):
                info.dessert = names.get(order["dessertId"], f"Recipe {order['dessertId']}")
        elif day.get("holiday") or lunch is None or not mains:
            info.status = STATUS_HOLIDAY
        elif d < today:
            info.status = STATUS_PAST
        days[d] = info
    return days


def no_menu(d: date) -> DayInfo:
    return DayInfo(date=d, status=STATUS_NO_MENU)
