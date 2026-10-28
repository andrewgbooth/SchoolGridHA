"""Fixture data shaped like the real SchoolGrid API responses."""
from datetime import date, timedelta

ACCOUNTS = {
    "UserId": 1378505,
    "SchoolAccounts": [{
        "SchoolId": 3877, "SchoolName": "Menston Primary (Ickley)", "ClientId": 1,
        "CustomerAccounts": [{
            "Id": 1467173, "FirstName": "Theodore", "FullName": "Theodore Booth", "YearId": 1,
            "IsActive": True, "IsRemoved": False, "FoodBalance": 0.0,
        }],
    }],
}


def dish(i, name, allergens=(), sold_out=False, choice=False):
    return {"recipeId": i, "recipeName": name + " ", "soldOut": sold_out, "choiceRecipe": choice,
            "recipeAllergens": [{"name": a, "mayContain": False} for a in allergens]}


def day(d: date, holiday=False):
    if d.weekday() >= 5:
        return {"orderDay": f"{d}T00:00:00", "serviceMealOrderDay": [], "holiday": True}
    return {"orderDay": f"{d}T00:00:00", "holiday": holiday, "serviceMealOrderDay": [{
        "menuAssignmentId": 33123, "serviceId": 10, "serviceName": "Lunch", "courses": [
            {"courseName": "Mains", "preorderAvailable": True, "dishes": [
                dish(96771, "Baked Potato with Baked Beans"),
                dish(96662, "Baked Potato with Baked Beans & Cheese", ["Milk"]),
                dish(96775, "Cheese Roll with Nachos", ["Milk", "Wheat"], sold_out=True),
                dish(1, "Build your own wrap", choice=True),
            ]},
            {"courseName": "Accompaniments", "preorderAvailable": False, "dishes": [dish(98085, "Salad")]},
            {"courseName": "Desserts", "preorderAvailable": True, "dishes": [
                dish(98129, "Fresh Fruit"), dish(99369, "Strawberry Yogurt", ["Milk"]),
            ]},
        ]}]}


def menus(start: str, end: str):
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out = []
    d = s
    while d <= e:
        out.append(day(d, holiday=d <= date(2026, 10, 30)))  # half term
        d += timedelta(days=1)
    return out


ORDERS = [
    {"preorderId": 246364134, "mainCourseId": 96771, "dessertId": None, "mealDate": "2026-11-02T00:00:00"},
    {"preorderId": 246364275, "mainCourseId": 96771, "dessertId": 98129, "mealDate": "2026-11-03T00:00:00"},
]
