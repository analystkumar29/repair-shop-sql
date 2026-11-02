"""The generated data should hang together like real booking data, and be reproducible."""

import datetime as dt

import pytest

import generate_data
from generate_data import SNAPSHOT, TABLE_ORDER

PRIMARY_KEYS = {
    "cities": ("city_id",),
    "price_tiers": ("tier_id",),
    "services": ("service_id",),
    "device_models": ("model_id",),
    "technicians": ("technician_id",),
    "technician_shifts": ("technician_id", "shift_date"),
    "customers": ("customer_id",),
    "bookings": ("booking_id",),
    "payments": ("payment_id",),
    "reviews": ("review_id",),
    "warranty_claims": ("claim_id",),
}

# (child table, column, parent table). Each foreign key column has the same name as the parent's key.
FOREIGN_KEYS = [
    ("technician_shifts", "technician_id", "technicians"),
    ("bookings", "customer_id", "customers"),
    ("bookings", "city_id", "cities"),
    ("bookings", "model_id", "device_models"),
    ("bookings", "service_id", "services"),
    ("bookings", "tier_id", "price_tiers"),
    ("bookings", "technician_id", "technicians"),
    ("payments", "booking_id", "bookings"),
    ("reviews", "booking_id", "bookings"),
    ("warranty_claims", "booking_id", "bookings"),
]


def test_same_seed_writes_identical_files(tmp_path):
    generate_data.write_csvs(generate_data.generate(seed=7), tmp_path / "first")
    generate_data.write_csvs(generate_data.generate(seed=7), tmp_path / "second")
    for name in TABLE_ORDER:
        first = (tmp_path / "first" / f"{name}.csv").read_bytes()
        second = (tmp_path / "second" / f"{name}.csv").read_bytes()
        assert first == second, f"{name}.csv differs between two runs with the same seed"


def test_a_different_seed_gives_different_bookings(tables):
    assert generate_data.generate(seed=generate_data.SEED + 1)["bookings"] != tables["bookings"]


def test_size_and_time_span(tables):
    bookings = tables["bookings"]
    assert 3_000 <= len(bookings) <= 6_000, "a few thousand bookings"
    first = min(b["created_at"] for b in bookings)
    last = max(b["created_at"] for b in bookings)
    assert first.date() >= generate_data.FIRST_DAY
    assert last <= SNAPSHOT
    assert (last - first).days >= 540, "about 18 months of history"


@pytest.mark.parametrize("table", TABLE_ORDER)
def test_primary_keys_are_unique(tables, table):
    keys = [tuple(row[column] for column in PRIMARY_KEYS[table]) for row in tables[table]]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("child, column, parent", FOREIGN_KEYS, ids=[f"{c}.{k}" for c, k, _ in FOREIGN_KEYS])
def test_foreign_keys_resolve(tables, child, column, parent):
    parent_keys = {row[column] for row in tables[parent]}
    missing = {row[column] for row in tables[child] if row[column] is not None} - parent_keys
    assert not missing, f"{child}.{column} values with no matching {parent} row: {sorted(missing)[:5]}"


def test_no_job_is_completed_before_it_was_requested(tables):
    for b in tables["bookings"]:
        if b["completed_at"] is not None:
            assert b["created_at"] < b["confirmed_at"] < b["scheduled_for"] < b["completed_at"], b["booking_id"]


def test_cancellations_come_after_the_request(tables):
    for b in tables["bookings"]:
        if b["cancelled_at"] is not None:
            assert b["cancelled_at"] > b["created_at"], b["booking_id"]


def test_completed_jobs_have_a_positive_final_price(tables):
    for b in tables["bookings"]:
        if b["status"] == "completed":
            assert b["final_price"] > 0 and b["technician_id"] is not None, b["booking_id"]
        else:
            assert b["final_price"] is None, b["booking_id"]


def test_status_matches_the_milestone_timestamps(tables):
    for b in tables["bookings"]:
        filled = tuple(b[c] is not None for c in ("confirmed_at", "completed_at", "cancelled_at"))
        if b["status"] == "requested":
            assert filled == (False, False, False), b["booking_id"]
        elif b["status"] == "confirmed":
            assert filled == (True, False, False), b["booking_id"]
        elif b["status"] == "completed":
            assert filled == (True, True, False), b["booking_id"]
        else:
            assert b["status"] == "cancelled" and filled[1:] == (False, True), b["booking_id"]


def test_open_bookings_are_recent(tables):
    for b in tables["bookings"]:
        if b["status"] in ("requested", "confirmed"):
            assert b["created_at"] > SNAPSHOT - dt.timedelta(days=30), b["booking_id"]


def test_nothing_is_recorded_after_the_snapshot(tables):
    stamps = [b[c] for b in tables["bookings"] for c in ("created_at", "confirmed_at", "completed_at", "cancelled_at")]
    stamps += [p["paid_at"] for p in tables["payments"]]
    stamps += [r["reviewed_at"] for r in tables["reviews"]]
    stamps += [w["claimed_at"] for w in tables["warranty_claims"]]
    assert max(s for s in stamps if s is not None) <= SNAPSHOT


def test_payments_reviews_and_claims_follow_a_completed_job(tables):
    bookings = {b["booking_id"]: b for b in tables["bookings"]}
    for table, column in [("payments", "paid_at"), ("reviews", "reviewed_at"), ("warranty_claims", "claimed_at")]:
        for row in tables[table]:
            job = bookings[row["booking_id"]]
            assert job["status"] == "completed" and row[column] > job["completed_at"], (table, row)


def test_jobs_happen_on_days_the_technician_worked(tables):
    worked = {(s["technician_id"], s["shift_date"]) for s in tables["technician_shifts"]}
    for b in tables["bookings"]:
        if b["status"] == "completed":
            assert (b["technician_id"], b["completed_at"].date()) in worked, b["booking_id"]


def test_customers_are_obviously_fake(tables):
    assert all(c["email"].lower().endswith("@example.com") for c in tables["customers"])


def test_planted_data_quality_issues_are_present(tables):
    emails = [c["email"].lower() for c in tables["customers"]]
    assert len(emails) > len(set(emails)), "expected a few duplicate customer records"
    paid = {p["booking_id"] for p in tables["payments"]}
    unpaid = [b for b in tables["bookings"] if b["status"] == "completed" and b["booking_id"] not in paid]
    assert unpaid, "expected a few completed jobs with no payment recorded"


def test_csv_headers_match_the_schema(db, data_dir):
    # COPY loads columns by position, so the CSV header must follow the table's column order.
    for table in TABLE_ORDER:
        header = (data_dir / f"{table}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        columns = [d[0] for d in db.execute(f"SELECT * FROM {table} LIMIT 0").description]
        assert header == columns, table
