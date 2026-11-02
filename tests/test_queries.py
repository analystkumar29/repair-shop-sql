"""Every query runs against the generated data, and its answer passes a sanity check."""

from pathlib import Path

import pytest

import run_queries

ROOT = Path(__file__).resolve().parent.parent
SQL_FILES = sorted((ROOT / "sql").glob("*.sql"))


def run(db, name: str) -> list[dict]:
    """Run sql/<name>.sql and return its rows as dicts keyed by column name."""
    columns, rows = run_queries.run_query(db, ROOT / "sql" / f"{name}.sql")
    return [dict(zip(columns, row)) for row in rows]


def scalar(db, sql: str):
    return db.execute(sql).fetchone()[0]


def test_there_are_ten_numbered_queries():
    assert [p.name[:2] for p in SQL_FILES] == [f"{n:02d}" for n in range(1, 11)]


@pytest.mark.parametrize("sql_path", SQL_FILES, ids=lambda p: p.stem)
def test_query_runs_and_returns_rows(db, sql_path):
    columns, rows = run_queries.run_query(db, sql_path)
    assert columns
    assert rows, f"{sql_path.name} returned no rows"


@pytest.mark.parametrize("sql_path", SQL_FILES, ids=lambda p: p.stem)
def test_query_starts_with_its_business_question(sql_path):
    title, paragraphs = run_queries.read_header(sql_path.read_text(encoding="utf-8"))
    assert title.startswith(sql_path.name[:2])
    assert any(p.startswith("Question:") for p in paragraphs)


def test_readme_links_every_query_and_result():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for sql_path in SQL_FILES:
        assert f"sql/{sql_path.name}" in readme
        assert f"results/{sql_path.stem}.md" in readme


# Sanity checks on the answers, not just that the SQL runs.

def test_running_total_ends_at_total_revenue(db):
    months = run(db, "01_monthly_revenue")
    assert months[0]["previous_revenue"] is None
    assert months[-1]["running_total_revenue"] == scalar(
        db, "SELECT SUM(final_price) FROM bookings WHERE status = 'completed'")


def test_tier_columns_add_up_to_each_service_total(db):
    rows = run(db, "02_revenue_by_service_and_tier")
    for r in rows:
        assert r["value_revenue"] + r["recommended_revenue"] + r["premium_revenue"] == r["total_revenue"]
    assert sum(r["share_of_all_revenue_pct"] for r in rows) == pytest.approx(100, abs=0.5)


def test_every_city_gets_its_top_three(db):
    rows = run(db, "03_top_models_per_city")
    cities = {r["city_name"] for r in rows}
    assert len(cities) == scalar(db, "SELECT COUNT(*) FROM cities")
    assert all(sum(r["city_name"] == city for r in rows) >= 3 for city in cities)
    assert all(r["rank_in_city"] <= 3 for r in rows)


def test_funnel_adds_up(db):
    for month in run(db, "04_booking_funnel"):
        assert month["requested"] == month["completed"] + month["cancelled"] + month["still_open"]
        assert month["completed"] <= month["confirmed"] <= month["requested"]


def test_cohorts_count_each_customer_once(db):
    cohorts = run(db, "05_customer_retention")
    assert sum(c["new_customers"] for c in cohorts) == scalar(
        db, "SELECT COUNT(DISTINCT customer_id) FROM bookings WHERE status = 'completed'")
    assert cohorts[0]["back_within_365_days_pct"] is not None
    assert cohorts[-1]["back_within_90_days_pct"] is None  # the newest cohort is too young to measure


def test_utilisation_covers_every_technician(db):
    rows = run(db, "06_technician_utilisation")
    assert len(rows) == scalar(db, "SELECT COUNT(*) FROM technicians")
    assert all(0 < r["utilisation_pct"] < 100 for r in rows)


def test_route_day_areas_wait_longer(db):
    rows = run(db, "07_lead_time_by_city")
    assert all(r["p90_days"] >= r["median_days"] for r in rows)
    route_days = [r["median_days"] for r in rows if r["service_days"] != "Every day"]
    every_day = [r["median_days"] for r in rows if r["service_days"] == "Every day"]
    assert min(route_days) > max(every_day)


def test_cheaper_tiers_claim_more_often(db):
    rates = [r["claim_rate_pct"] for r in run(db, "08_warranty_claims_by_tier")]  # Value, Recommended, Premium
    assert rates == sorted(rates, reverse=True)


def test_only_technicians_with_30_reviews_are_ranked(db):
    ranked = run(db, "09_technician_ratings")
    assert all(r["reviews"] >= 30 for r in ranked)
    reviewed = scalar(db, "SELECT COUNT(DISTINCT b.technician_id) FROM reviews r "
                          "JOIN bookings b ON b.booking_id = r.booking_id")
    assert len(ranked) < reviewed, "the newest technician shouldn't have 30 reviews yet"


def test_data_quality_flags_only_the_planted_issues(db):
    flagged = {r["check_id"] for r in run(db, "10_data_quality_checks") if r["issues_found"] > 0}
    assert flagged == {1, 3}  # missing cash payments and duplicate customers


# The markdown writer

def test_long_results_are_cut_off_with_a_note():
    markdown = run_queries.to_markdown(["n"], [(i,) for i in range(50)], max_rows=40)
    assert sum(line.startswith("| ") for line in markdown.splitlines()) == 41  # header + 40 rows
    assert "Showing the first 40 of 50 rows" in markdown


def test_float_columns_share_their_decimals():
    markdown = run_queries.to_markdown(["avg"], [(4.5,), (4.58,), (None,)])
    assert "| 4.50 |" in markdown and "| 4.58 |" in markdown and "| NULL |" in markdown
