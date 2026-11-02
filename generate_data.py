"""Generate the synthetic dataset that the SQL in this repository runs on.

Nothing in it is real. The tables are modelled on the kind of data a doorstep
phone and laptop repair business keeps (bookings, technicians, payments,
reviews, warranty claims), but every customer, job and price is invented by
this script. Customer emails use the reserved example.com domain.

The random number generator is seeded, so the same seed always produces the
same CSV files, byte for byte:

    python generate_data.py                        # default seed, writes data/*.csv
    python generate_data.py --seed 7 --out /tmp/x  # another seed, another folder
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import heapq
import math
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

SEED = 42
FIRST_DAY = dt.date(2025, 5, 1)
LAST_DAY = dt.date(2026, 10, 31)
# The moment the data was "exported". Anything that would happen after it
# (a future appointment, a review not written yet) is left out.
SNAPSHOT = dt.datetime(2026, 10, 31, 23, 59)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# (city_id, name, travel fee in $, relative demand, weekdays we visit or None for every day)
# Weekdays use ISO numbers: 1 = Monday ... 7 = Sunday. The three outer areas are
# only visited on route days, so customers there wait longer for a slot.
CITIES = [
    (1, "Burnaby", 0, 1.20, None),
    (2, "Vancouver", 0, 1.70, None),
    (3, "New Westminster", 0, 0.45, None),
    (4, "Richmond", 10, 0.90, None),
    (5, "Coquitlam", 10, 0.70, None),
    (6, "North Vancouver", 15, 0.60, None),
    (7, "Port Coquitlam", 15, 0.30, None),
    (8, "Surrey", 15, 1.30, None),
    (9, "Delta", 20, 0.40, None),
    (10, "Langley", 25, 0.50, (2, 4, 6)),
    (11, "Maple Ridge", 25, 0.35, (3, 6)),
    (12, "Abbotsford", 35, 0.40, (2, 5)),
]

# (tier_id, name, price multiplier, warranty months)
PRICE_TIERS = [
    (1, "Value", Decimal("0.85"), 3),
    (2, "Recommended", Decimal("1.00"), 6),
    (3, "Premium", Decimal("1.25"), 12),
]

# (service_id, name, device type, base price $, hands-on minutes, relative demand, claim risk)
# The last two columns only steer the simulation; they are not written to the CSVs.
SERVICES = [
    (1, "Screen replacement", "phone", 149, 50, 0.48, 1.2),
    (2, "Battery replacement", "phone", 89, 35, 0.25, 0.7),
    (3, "Charging port repair", "phone", 99, 40, 0.12, 1.3),
    (4, "Back glass replacement", "phone", 129, 75, 0.08, 0.9),
    (5, "Camera repair", "phone", 119, 40, 0.07, 1.0),
    (6, "Screen replacement", "laptop", 379, 90, 0.35, 1.0),
    (7, "Battery replacement", "laptop", 199, 60, 0.40, 0.6),
    (8, "Keyboard replacement", "laptop", 259, 100, 0.25, 1.1),
]

# (model_id, brand, model, device type, release year, price factor, relative popularity)
DEVICE_MODELS = [
    (1, "Apple", "iPhone 11", "phone", 2019, 0.80, 0.60),
    (2, "Apple", "iPhone 12", "phone", 2020, 0.90, 1.00),
    (3, "Apple", "iPhone 13", "phone", 2021, 1.00, 1.30),
    (4, "Apple", "iPhone 13 Pro", "phone", 2021, 1.15, 0.70),
    (5, "Apple", "iPhone 14", "phone", 2022, 1.10, 1.20),
    (6, "Apple", "iPhone 14 Pro", "phone", 2022, 1.30, 0.80),
    (7, "Apple", "iPhone 15", "phone", 2023, 1.20, 1.00),
    (8, "Apple", "iPhone 15 Pro Max", "phone", 2023, 1.55, 0.60),
    (9, "Apple", "iPhone 16", "phone", 2024, 1.30, 0.55),
    (10, "Apple", "iPhone 16 Pro", "phone", 2024, 1.55, 0.40),
    (11, "Samsung", "Galaxy S22", "phone", 2022, 1.05, 0.50),
    (12, "Samsung", "Galaxy S23", "phone", 2023, 1.15, 0.55),
    (13, "Samsung", "Galaxy S24 Ultra", "phone", 2024, 1.60, 0.35),
    (14, "Samsung", "Galaxy A54", "phone", 2023, 0.75, 0.45),
    (15, "Google", "Pixel 7", "phone", 2022, 0.95, 0.35),
    (16, "Google", "Pixel 8", "phone", 2023, 1.05, 0.30),
    (17, "Apple", "MacBook Air M1", "laptop", 2020, 0.90, 0.50),
    (18, "Apple", "MacBook Air M2", "laptop", 2022, 1.05, 0.45),
    (19, "Apple", "MacBook Pro 14 M3", "laptop", 2023, 1.35, 0.25),
]

# (technician_id, name, hired, left or None, shift hours, weekdays worked, review quality)
# Review quality is the average score customers lean towards; it only steers the simulation.
TECHNICIANS = [
    (1, "Arjun", dt.date(2025, 5, 1), None, 8, (1, 2, 3, 4, 5), 4.70),
    (2, "Mei", dt.date(2025, 5, 1), None, 8, (3, 4, 5, 6, 7), 4.80),
    (3, "Daniel", dt.date(2025, 5, 1), dt.date(2026, 4, 30), 6, (5, 6, 7), 4.50),
    (4, "Simran", dt.date(2025, 9, 2), None, 8, (1, 2, 3, 4, 5), 4.75),
    (5, "Reza", dt.date(2026, 3, 2), None, 8, (1, 4, 5, 6, 7), 4.60),
    (6, "Grace", dt.date(2026, 9, 14), None, 8, (2, 3, 4, 5, 6), 4.95),
]

HOLIDAYS = {dt.date(2025, 12, 25), dt.date(2025, 12, 26), dt.date(2026, 1, 1)}

# Appointment start times. An 8-hour shift runs 10:00-18:00, a 6-hour shift 12:00-18:00,
# and each two-hour window holds one job including travel.
SLOT_HOURS = {8: (10, 12, 14, 16), 6: (12, 14, 16)}
SLOT_POPULARITY = {10: 2, 12: 2, 14: 3, 16: 4}  # after-work slots are asked for most

# ---------------------------------------------------------------------------
# Demand and behaviour assumptions
# ---------------------------------------------------------------------------

NEW_CUSTOMER_BOOKINGS_PER_DAY = 5.0  # at the start, before growth and seasonality
MONTHLY_GROWTH = 0.03
SEASONALITY = {1: 1.05, 2: 0.90, 3: 0.95, 4: 0.95, 5: 1.00, 6: 1.10,
               7: 1.20, 8: 1.15, 9: 1.05, 10: 0.95, 11: 1.00, 12: 1.10}
WEEKDAY_FACTOR = {1: 1.25, 2: 1.10, 3: 1.00, 4: 0.95, 5: 0.90, 6: 0.95, 7: 0.85}
BOOKING_HOUR_WEIGHTS = {7: 2, 8: 4, 9: 6, 10: 7, 11: 7, 12: 8, 13: 7, 14: 6, 15: 6,
                        16: 6, 17: 7, 18: 8, 19: 9, 20: 9, 21: 7, 22: 4, 23: 2}
LEAD_DAYS = [0, 1, 2, 3, 4, 5, 7, 10, 14]  # how far ahead customers ask for
LEAD_DAY_WEIGHTS = [22, 36, 15, 10, 6, 4, 3, 2, 2]

CONFIRM_RATE = 0.92            # the rest never reply to our confirmation text
REVIEW_RATE = 0.35             # share of completed jobs that get a review
RETURN_RATE = 0.25             # chance a happy customer books again later
DUPLICATE_CUSTOMER_RATE = 0.03  # returning customers who re-register (planted data-quality issue)
MISSING_CASH_PAYMENT_RATE = 0.04  # cash jobs never entered (planted data-quality issue)
DEFECT_RATE_BY_TIER = {1: 0.12, 2: 0.06, 3: 0.025}  # chance the part fails, before service risk

CLAIM_REASONS = {
    1: ["Touch not responding", "Display flicker or lines", "Screen lifting"],
    2: ["Battery draining fast", "Battery health warning"],
    3: ["Not charging", "Loose cable connection"],
    4: ["Back glass lifting"],
    5: ["Camera not focusing", "Blurry photos"],
    6: ["Display flicker or lines", "Dead pixels"],
    7: ["Battery draining fast", "Not holding charge"],
    8: ["Keys not registering", "Sticky keys"],
}

FIRST_NAMES = [
    "Aarav", "Aisha", "Alex", "Amir", "Ana", "Andre", "Anika", "Ben", "Carlos", "Chloe",
    "Diego", "Elena", "Emily", "Ethan", "Fatima", "Gurpreet", "Hana", "Harjit", "Ian",
    "Jasmine", "Jason", "Ji-woo", "Kavya", "Kevin", "Laila", "Liam", "Lucas", "Maria",
    "Maya", "Mohammed", "Nadia", "Noah", "Olivia", "Omar", "Parveen", "Priya", "Rahul",
    "Rosa", "Ryan", "Sara", "Sofia", "Tara", "Tyler", "Vikram", "Wei", "Yuki", "Zara", "Zoe",
]
LAST_NAMES = [
    "Ahmed", "Anderson", "Bains", "Brar", "Brown", "Chan", "Chen", "Dhillon", "Fernandez",
    "Garcia", "Gill", "Grewal", "Gupta", "Ho", "Huang", "Jackson", "Johal", "Khan", "Kim",
    "Lam", "Lee", "Li", "Lin", "MacDonald", "Martin", "Mehta", "Morales", "Nguyen", "Park",
    "Patel", "Reyes", "Robinson", "Sandhu", "Santos", "Sharma", "Sidhu", "Singh", "Smith",
    "Tan", "Taylor", "Thompson", "Tran", "Wang", "Williams", "Wilson", "Wong", "Wu", "Zhang",
]

WEEKDAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

# Load order: every table comes after the tables it references.
TABLE_ORDER = [
    "cities", "price_tiers", "services", "device_models", "technicians",
    "technician_shifts", "customers", "bookings", "payments", "reviews", "warranty_claims",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def minutes(n: float) -> dt.timedelta:
    """A whole number of minutes, at least one, so timestamps stay in order."""
    return dt.timedelta(minutes=max(1, round(n)))


def money(amount: float) -> Decimal:
    return Decimal(amount).quantize(Decimal("0.01"))


def add_months(moment: dt.datetime, months: int) -> dt.datetime:
    """Same day-of-month `months` later, clamped to the end of shorter months."""
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    next_month = dt.date(year + month // 12, month % 12 + 1, 1)
    last_day = (next_month - dt.timedelta(days=1)).day
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def poisson(rng: random.Random, mean: float) -> int:
    """Number of events in a period with the given average (Knuth's method)."""
    limit, count, product = math.exp(-mean), 0, rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def daterange(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------

class RepairShopSimulation:
    """Walks through every day in the period and records what happens to each booking."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.services = {row[0]: row for row in SERVICES}
        self.models = {row[0]: row for row in DEVICE_MODELS}
        self.cities = {row[0]: row for row in CITIES}
        self.technicians = {row[0]: row for row in TECHNICIANS}

        self.shifts = self._build_shifts()
        self.techs_by_day: dict[dt.date, list[tuple[int, int]]] = defaultdict(list)
        for (tech_id, day), hours in self.shifts.items():
            self.techs_by_day[day].append((tech_id, hours))
        self.booked_hours: dict[tuple[int, dt.date], set[int]] = defaultdict(set)

        # Each city gets its own slight twist on device popularity, so the
        # "top models per city" question has something to find.
        self.city_model_bias = {
            (city_id, model_id): math.exp(self.rng.gauss(0, 0.25))
            for city_id in self.cities for model_id in self.models
        }

        self.customers: list[dict] = []
        self.bookings: list[dict] = []
        self.payments: list[dict] = []
        self.reviews: list[dict] = []
        self.claims: list[dict] = []
        self.returning: list[tuple] = []  # heap of future repeat bookings
        self.sequence = 0                 # tie-breaker so heap entries never compare dicts

    # -- staff ---------------------------------------------------------------

    def _build_shifts(self) -> dict[tuple[int, dt.date], int]:
        """Days each technician works: their usual weekdays minus holidays and ~5% days off.

        Shifts run two months past the snapshot so late-October bookings can be
        scheduled into November; only days up to LAST_DAY are written out.
        """
        shifts = {}
        for day in daterange(FIRST_DAY, LAST_DAY + dt.timedelta(days=60)):
            if day in HOLIDAYS:
                continue
            for tech_id, _, hired, left, hours, weekdays, _ in TECHNICIANS:
                employed = hired <= day and (left is None or day <= left)
                if employed and day.isoweekday() in weekdays and self.rng.random() > 0.05:
                    shifts[(tech_id, day)] = hours
        return shifts

    def _find_slot(self, wanted: dt.datetime, visit_days) -> tuple[int, dt.datetime]:
        """Earliest free (technician, start time) at or after `wanted` on a day we serve the city."""
        day, earliest_hour = wanted.date(), wanted.hour
        for _ in range(45):
            if visit_days is None or day.isoweekday() in visit_days:
                best = None
                for tech_id, hours in self.techs_by_day.get(day, []):
                    taken = self.booked_hours[(tech_id, day)]
                    free = [h for h in SLOT_HOURS[hours] if h >= earliest_hour and h not in taken]
                    if free:
                        # Earliest start first; on a tie, the technician with the lighter day.
                        candidate = (free[0], len(taken), tech_id)
                        best = candidate if best is None else min(best, candidate)
                if best:
                    hour, _, tech_id = best
                    self.booked_hours[(tech_id, day)].add(hour)
                    return tech_id, dt.datetime.combine(day, dt.time(hour))
            day += dt.timedelta(days=1)
            earliest_hour = 0
        raise RuntimeError(f"No free slot within 45 days of {wanted}")

    # -- customers and devices -------------------------------------------------

    def _new_customer(self, created_at: dt.datetime) -> int:
        customer_id = len(self.customers) + 1
        first, last = self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)
        email = f"{first}.{last}{customer_id}@example.com".lower().replace("-", "")
        self.customers.append({"customer_id": customer_id, "full_name": f"{first} {last}",
                               "email": email, "created_at": created_at})
        return customer_id

    def _duplicate_customer(self, customer_id: int, created_at: dt.datetime) -> int:
        """A returning customer who fills in the form again: same person, new customer_id."""
        original = self.customers[customer_id - 1]
        duplicate_id = len(self.customers) + 1
        self.customers.append({"customer_id": duplicate_id, "full_name": original["full_name"],
                               "email": original["email"].capitalize(), "created_at": created_at})
        return duplicate_id

    def _pick_city(self) -> int:
        return self.rng.choices([c[0] for c in CITIES], [c[3] for c in CITIES])[0]

    def _pick_model(self, city_id: int, day: dt.date) -> int:
        progress = (day - FIRST_DAY).days / (LAST_DAY - FIRST_DAY).days
        weights = []
        for model_id, _, _, _, year, _, popularity in DEVICE_MODELS:
            weight = popularity * self.city_model_bias[(city_id, model_id)]
            if year >= 2024:
                weight *= 1 + progress        # newer phones show up more as they age
            elif year <= 2020:
                weight *= 1 - 0.4 * progress  # the oldest models fade out
            weights.append(weight)
        return self.rng.choices([m[0] for m in DEVICE_MODELS], weights)[0]

    def _pick_service(self, device_type: str) -> int:
        options = [s for s in SERVICES if s[2] == device_type]
        return self.rng.choices([s[0] for s in options], [s[5] for s in options])[0]

    def _pick_tier(self, model) -> int:
        _, _, _, device_type, year, _, _ = model
        value, premium = (0.15, 0.35) if device_type == "laptop" else (0.27, 0.23)
        if year >= 2023:
            value, premium = value - 0.08, premium + 0.08  # newer devices: people pay for better parts
        elif year <= 2020:
            value, premium = value + 0.10, premium - 0.10  # older devices: cheapest fix wins
        return self.rng.choices([1, 2, 3], [value, 1 - value - premium, premium])[0]

    def _quote(self, service, model, tier_id: int, city) -> Decimal:
        multiplier = float(PRICE_TIERS[tier_id - 1][2])
        raw = service[3] * model[5] * multiplier
        repair_price = round(raw / 10) * 10 - 1  # price-list style: 149, 239, ...
        return money(repair_price + city[2])

    # -- timing ----------------------------------------------------------------

    def _requested_time(self, created_at: dt.datetime, visit_days) -> dt.datetime:
        lead = self.rng.choices(LEAD_DAYS, LEAD_DAY_WEIGHTS)[0]
        day = created_at.date() + dt.timedelta(days=lead)
        hours = list(SLOT_POPULARITY)
        if lead == 0:
            hours = [h for h in hours if h >= created_at.hour + 2]  # same day needs 2 hours' notice
            if not hours:
                day += dt.timedelta(days=1)
                hours = list(SLOT_POPULARITY)
        hour = self.rng.choices(hours, [SLOT_POPULARITY[h] for h in hours])[0]
        while visit_days is not None and day.isoweekday() not in visit_days:
            day += dt.timedelta(days=1)
        return dt.datetime.combine(day, dt.time(hour))

    def _confirmation_time(self, created_at: dt.datetime, appointment: dt.datetime) -> dt.datetime:
        """We confirm by text between 8:00 and 21:00, usually within the hour."""
        moment = created_at + minutes(3 + self.rng.expovariate(1 / 40))
        if moment.hour >= 21:
            next_morning = dt.datetime.combine(moment.date() + dt.timedelta(days=1), dt.time(8))
            moment = next_morning + minutes(self.rng.uniform(0, 90))
        elif moment.hour < 8:
            moment = dt.datetime.combine(moment.date(), dt.time(8)) + minutes(self.rng.uniform(0, 90))
        latest = appointment - dt.timedelta(minutes=30)
        if moment > latest:
            moment = created_at + (latest - created_at) / 2
        return moment.replace(second=0, microsecond=0)

    def _rating(self, tech, lead_days: int, final_price: Decimal, quoted_price: Decimal, tier_id: int) -> int:
        unhappy_chance = 0.03 + (0.05 if lead_days >= 5 else 0) + (0.06 if final_price > quoted_price else 0)
        if self.rng.random() < unhappy_chance:
            return self.rng.choice([1, 1, 2])
        score = tech[6] + (0.1 if tier_id == 3 else 0) + self.rng.gauss(0, 0.6)
        return max(1, min(5, math.floor(score + 0.5)))

    # -- one booking from request to outcome -----------------------------------

    def _book(self, created_at: dt.datetime, customer_id: int | None, city_id: int | None,
              model_id: int | None) -> None:
        rng = self.rng
        if customer_id is None:
            customer_id = self._new_customer(created_at)
        elif rng.random() < DUPLICATE_CUSTOMER_RATE:
            customer_id = self._duplicate_customer(customer_id, created_at)

        city = self.cities[city_id or self._pick_city()]
        model = self.models[model_id or self._pick_model(city[0], created_at.date())]
        service = self.services[self._pick_service(model[3])]
        tier_id = self._pick_tier(model)
        quoted_price = self._quote(service, model, tier_id, city)

        booking = {
            "booking_id": len(self.bookings) + 1, "customer_id": customer_id, "city_id": city[0],
            "model_id": model[0], "service_id": service[0], "tier_id": tier_id,
            "technician_id": None, "status": None, "created_at": created_at,
            "confirmed_at": None, "scheduled_for": None, "completed_at": None,
            "cancelled_at": None, "quoted_price": quoted_price, "final_price": None,
        }
        self.bookings.append(booking)

        wanted = self._requested_time(created_at, city[4])
        booking["scheduled_for"] = wanted

        # 1. Some requests are never confirmed: we close them after a day or two.
        if rng.random() >= CONFIRM_RATE:
            cancelled_at = created_at + minutes(rng.uniform(60, 48 * 60))
            if cancelled_at <= SNAPSHOT:
                booking.update(status="cancelled", cancelled_at=cancelled_at)
            else:
                booking["status"] = "requested"
            return

        confirmed_at = self._confirmation_time(created_at, wanted)
        if confirmed_at > SNAPSHOT:  # created late on the last evening: not confirmed yet
            booking["status"] = "requested"
            return

        # 2. Confirmed: book the earliest free technician slot at or after the requested time.
        tech_id, scheduled_for = self._find_slot(wanted, city[4])
        tech = self.technicians[tech_id]
        lead_days = (scheduled_for.date() - created_at.date()).days
        booking.update(status="confirmed", technician_id=tech_id,
                       confirmed_at=confirmed_at, scheduled_for=scheduled_for)

        # 3. Longer waits mean more cancellations; a few are no-shows at the door.
        if rng.random() < min(0.30, 0.06 + 0.015 * lead_days):
            if rng.random() < 0.2:
                cancelled_at = scheduled_for + minutes(rng.uniform(20, 40))
            else:
                window = (scheduled_for - dt.timedelta(minutes=15) - confirmed_at).total_seconds() / 60
                cancelled_at = confirmed_at + minutes(rng.uniform(1, max(1.0, window)))
            if cancelled_at <= SNAPSHOT:
                booking.update(status="cancelled", cancelled_at=cancelled_at)
            return

        # 4. The repair happens.
        hands_on = service[4] * rng.uniform(0.85, 1.35)
        completed_at = scheduled_for + minutes(rng.uniform(5, 25)) + minutes(hands_on)
        if completed_at > SNAPSHOT:  # appointment is after the export: still open
            return

        adjustment = rng.random()
        if adjustment < 0.08:    # repeat-customer discount or price match
            final_price = quoted_price - rng.choice([10, 15, 20])
        elif adjustment < 0.16:  # an extra part was needed on the day
            final_price = quoted_price + rng.choice([20, 30, 40, 60])
        else:
            final_price = quoted_price
        booking.update(status="completed", completed_at=completed_at, final_price=money(final_price))

        method = rng.choices(["card", "e-transfer", "cash"], [68, 20, 12])[0]
        if not (method == "cash" and rng.random() < MISSING_CASH_PAYMENT_RATE):
            self.payments.append({"booking_id": booking["booking_id"],
                                  "paid_at": completed_at + minutes(rng.uniform(1, 15)),
                                  "amount": booking["final_price"], "method": method})

        rating = None
        if rng.random() < REVIEW_RATE:
            reviewed_at = completed_at + minutes(60 + rng.expovariate(1 / (36 * 60)))
            rating = self._rating(tech, lead_days, booking["final_price"], quoted_price, tier_id)
            if reviewed_at <= SNAPSHOT:
                self.reviews.append({"booking_id": booking["booking_id"],
                                     "rating": rating, "reviewed_at": reviewed_at})

        # 5. Warranty: cheaper parts fail more often. Most failures show up in the first few months.
        claim_outcome = None
        if rng.random() < DEFECT_RATE_BY_TIER[tier_id] * service[6]:
            claimed_at = completed_at + dt.timedelta(days=rng.expovariate(1 / 45)) + minutes(rng.uniform(0, 600))
            warranty_ends = add_months(completed_at, PRICE_TIERS[tier_id - 1][3])
            if claimed_at <= warranty_ends:
                claim_outcome = "approved" if rng.random() < 0.88 else "rejected"  # rejected: new damage
            elif rng.random() < 0.4:
                claim_outcome = "rejected"  # asked after the warranty ran out
            if claim_outcome and claimed_at <= SNAPSHOT:
                self.claims.append({"booking_id": booking["booking_id"],
                                    "claimed_at": claimed_at.replace(second=0, microsecond=0),
                                    "reason": rng.choice(CLAIM_REASONS[service[0]]),
                                    "outcome": claim_outcome})

        # 6. Some customers come back months later, for another device or another fix.
        return_chance = RETURN_RATE
        if (rating is not None and rating <= 2) or claim_outcome == "rejected":
            return_chance = 0.04
        if rng.random() < return_chance:
            when = completed_at + dt.timedelta(days=20 + rng.expovariate(1 / 140))
            when = dt.datetime.combine(when.date(), dt.time(self._booking_hour(), rng.randint(0, 59)))
            same_city = city[0] if rng.random() < 0.85 else None
            same_model = model[0] if rng.random() < 0.3 else None
            self.sequence += 1
            heapq.heappush(self.returning, (when, self.sequence, customer_id, same_city, same_model))

    def _booking_hour(self) -> int:
        return self.rng.choices(list(BOOKING_HOUR_WEIGHTS), list(BOOKING_HOUR_WEIGHTS.values()))[0]

    # -- main loop ---------------------------------------------------------------

    def run(self) -> None:
        for day in daterange(FIRST_DAY, LAST_DAY):
            months_in = (day - FIRST_DAY).days / 30.44
            expected = (NEW_CUSTOMER_BOOKINGS_PER_DAY * (1 + MONTHLY_GROWTH) ** months_in
                        * SEASONALITY[day.month] * WEEKDAY_FACTOR[day.isoweekday()])

            requests = []  # (created_at, tie-breaker, customer_id, city_id, model_id)
            for _ in range(poisson(self.rng, expected)):
                created_at = dt.datetime.combine(day, dt.time(self._booking_hour(), self.rng.randint(0, 59)))
                self.sequence += 1
                requests.append((created_at, self.sequence, None, None, None))
            while self.returning and self.returning[0][0].date() <= day:
                requests.append(heapq.heappop(self.returning))

            for created_at, _, customer_id, city_id, model_id in sorted(requests):
                self._book(created_at, customer_id, city_id, model_id)

    # -- output ------------------------------------------------------------------

    def tables(self) -> dict[str, list[dict]]:
        def numbered(rows, id_column, time_column):
            ordered = sorted(rows, key=lambda r: (r[time_column], r["booking_id"]))
            return [{id_column: i, **row} for i, row in enumerate(ordered, start=1)]

        return {
            "cities": [
                {"city_id": c[0], "city_name": c[1], "travel_fee": money(c[2]),
                 "service_days": "Every day" if c[4] is None else ", ".join(WEEKDAY_NAMES[d] for d in c[4])}
                for c in CITIES
            ],
            "price_tiers": [
                {"tier_id": t[0], "tier_name": t[1], "price_multiplier": t[2], "warranty_months": t[3]}
                for t in PRICE_TIERS
            ],
            "services": [
                {"service_id": s[0], "service_name": s[1], "device_type": s[2],
                 "base_price": money(s[3]), "duration_minutes": s[4]}
                for s in SERVICES
            ],
            "device_models": [
                {"model_id": m[0], "brand": m[1], "model_name": m[2], "device_type": m[3], "release_year": m[4]}
                for m in DEVICE_MODELS
            ],
            "technicians": [
                {"technician_id": t[0], "technician_name": t[1], "hired_on": t[2], "left_on": t[3],
                 "employment_type": "full-time" if t[4] == 8 else "part-time"}
                for t in TECHNICIANS
            ],
            "technician_shifts": [
                {"technician_id": tech_id, "shift_date": day, "shift_hours": hours}
                for (tech_id, day), hours in sorted(self.shifts.items(), key=lambda kv: (kv[0][1], kv[0][0]))
                if day <= LAST_DAY
            ],
            "customers": self.customers,
            "bookings": self.bookings,
            "payments": numbered(self.payments, "payment_id", "paid_at"),
            "reviews": numbered(self.reviews, "review_id", "reviewed_at"),
            "warranty_claims": numbered(self.claims, "claim_id", "claimed_at"),
        }


def generate(seed: int = SEED) -> dict[str, list[dict]]:
    """Run the simulation and return every table as a list of row dicts."""
    simulation = RepairShopSimulation(seed)
    simulation.run()
    return simulation.tables()


def to_csv_value(value) -> str:
    if value is None:
        return ""  # an empty field loads as NULL
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def write_csvs(tables: dict[str, list[dict]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in TABLE_ORDER:
        rows = tables[name]
        with open(out_dir / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(to_csv_value(v) for v in row.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, default=SEED, help=f"random seed (default {SEED})")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data",
                        help="folder to write the CSV files to (default: data/)")
    args = parser.parse_args()

    tables = generate(args.seed)
    write_csvs(tables, args.out)
    total_bytes = sum((args.out / f"{name}.csv").stat().st_size for name in TABLE_ORDER)
    for name in TABLE_ORDER:
        print(f"{name:<18} {len(tables[name]):>6} rows")
    print(f"Wrote {len(TABLE_ORDER)} CSV files ({total_bytes / 1024:.0f} KB) to {args.out}")


if __name__ == "__main__":
    main()
