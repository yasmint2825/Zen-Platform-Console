"""
daily_intelligence.py — Intelligence agent's proactive, daily findings.

Distinct from generate_insights (a manually-triggered, single-snapshot
Claude call for narrative suggestions) and from train_and_score.py (the
weekly model retrain). This script computes four genuinely different,
deterministic findings from real transaction data every day:

  1. Anomaly detection   — does this week's activity deviate from the
                            business's own learned weekly baseline?
  2. Cohort trend shift   — is one segment (boy/girl) drifting away from
                            the other over the last 60 days vs the 60
                            before that?
  3. Stylist patterns     — surfaced from the EXISTING weekly snapshot
                            (mw_stylist_performance_snapshot, written by
                            train_and_score.py) rather than recomputed
                            here — that data is only actually refreshed
                            weekly, so re-deriving it daily would create
                            a false impression of daily freshness for
                            something that hasn't actually changed.
  4. Revenue pacing       — where this month is actually heading, based
                            on the real days-elapsed pace so far.

Every finding is a real, computed number — no fabricated insights, and
anything that can't be computed honestly (too little data, no variance
to compare against) is simply omitted rather than guessed at.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:port/dbname"
    export TENANT_ID="minicuts"
    python3 daily_intelligence.py
"""
import os
import sys
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

TENANT_ID = os.environ.get("TENANT_ID", "minicuts")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: set DATABASE_URL (your Supabase connection string).", file=sys.stderr)
    sys.exit(1)

MIN_WEEKS_FOR_ANOMALY = 6       # need real history before flagging a deviation as genuine, not noise
MIN_TX_PER_COHORT = 15          # each segment needs enough transactions for a comparison to mean anything
DATA_RELIABLE_FROM = pd.Timestamp("2026-06-09")  # data before this was bulk-uploaded via Excel and isn't reliable for pattern comparisons - anything looking back further than this gets clipped to it
ANOMALY_STDDEV_THRESHOLD = 1.5  # how far from the mean counts as "worth flagging", not every minor wobble
COHORT_DELTA_THRESHOLD_PCT = 15 # minimum % swing to call a cohort shift real rather than everyday noise


def load_transactions(engine) -> pd.DataFrame:
    query = """
        select customer_key, customer_mobile, transaction_date, amount
        from mw_transactions
        where tenant_id = %(tenant_id)s and customer_key is not null
        order by transaction_date asc
    """
    df = pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def load_all_revenue(engine) -> pd.DataFrame:
    """Same table, deliberately WITHOUT the customer_key filter
    load_transactions() uses - that filter is correct for the ML model
    (which needs a resolved customer identity to build features), but
    wrong for a plain revenue total, where a transaction that hasn't
    been matched to a customer yet is still real money that came in.
    Excluding it was silently undercounting actual revenue."""
    query = """
        select transaction_date, amount
        from mw_transactions
        where tenant_id = %(tenant_id)s
        order by transaction_date asc
    """
    df = pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def load_profiles(engine) -> pd.DataFrame:
    query = "select customer_key, segment from mw_customer_profile where tenant_id = %(tenant_id)s"
    return pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})


def diagnose_queue_revenue(engine, as_of: pd.Timestamp) -> None:
    """Purely informational - finds and prints whatever the real
    'queue' table actually is, using Postgres's own metadata rather
    than guessing at a table/column name. Not wired into any actual
    finding yet - this log output is what determines the real fix,
    rather than another guess."""
    print("\n  --- Queue table diagnostic ---")
    tables_df = pd.read_sql(
        "select table_name from information_schema.tables where table_name ilike %(pattern)s",
        engine, params={"pattern": "%queue%"},
    )
    if tables_df.empty:
        print("  No table matching '%queue%' found in this database.")
        return
    for table_name in tables_df["table_name"]:
        print(f"  Found table: {table_name}")
        cols_df = pd.read_sql(
            "select column_name, data_type from information_schema.columns where table_name = %(t)s order by ordinal_position",
            engine, params={"t": table_name},
        )
        print(f"    Columns: {list(zip(cols_df['column_name'], cols_df['data_type']))}")
        if "service_value" not in cols_df["column_name"].values:
            print(f"    (no service_value column on this table - may not be the right one)")
            continue
        date_cols = [c for c in cols_df["column_name"] if "date" in c.lower() or "created" in c.lower() or "time" in c.lower()]
        tenant_cols = [c for c in cols_df["column_name"] if "tenant" in c.lower()]
        print(f"    Candidate date columns: {date_cols}")
        print(f"    Candidate tenant columns: {tenant_cols}")
        try:
            total_row = pd.read_sql(f'select count(*) as n, sum(service_value) as total from "{table_name}"', engine)
            print(f"    Total rows: {int(total_row['n'][0])}, sum(service_value) across ALL rows/tenants: {total_row['total'][0]}")
        except Exception as e:
            print(f"    Could not sum service_value: {e}")
    print("  --- End diagnostic ---\n")


# ─────────────────────────────────────────────────────────────────
# 1. Anomaly detection — is this week genuinely unusual?
# ─────────────────────────────────────────────────────────────────
def detect_anomaly(tx: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    """Compares this week's visit count SO FAR against the same
    Monday-through-same-relative-day window in the business's own prior
    weeks - genuinely like-to-like, not a partial in-progress week
    against full completed weeks (which would always look artificially
    low simply because fewer days have elapsed). Uses through yesterday,
    not today, since today's data may still be incomplete. Returns None
    if there isn't enough history, or if nothing's actually unusual."""
    yesterday = as_of - pd.Timedelta(days=1)
    this_monday = yesterday - pd.Timedelta(days=yesterday.weekday())  # weekday(): Monday=0
    days_elapsed = (yesterday - this_monday).days + 1  # e.g. Monday=1, Tuesday=2, ... Sunday=7
    if days_elapsed < 2:
        return None  # too early in the week for a same-day-range comparison to mean anything
    if this_monday - pd.Timedelta(weeks=MIN_WEEKS_FOR_ANOMALY) < DATA_RELIABLE_FROM:
        return None  # the baseline would reach back into the unreliable, Excel-uploaded period - not an honest comparison yet

    daily = tx.set_index("transaction_date").resample("D").size()

    def visits_in_range(start: pd.Timestamp, end: pd.Timestamp) -> int:
        return int(daily[(daily.index >= start) & (daily.index <= end)].sum())

    this_week_count = visits_in_range(this_monday, yesterday)

    baseline_counts = []
    for weeks_back in range(1, MIN_WEEKS_FOR_ANOMALY + 1):
        prior_monday = this_monday - pd.Timedelta(weeks=weeks_back)
        prior_end = prior_monday + pd.Timedelta(days=days_elapsed - 1)  # same elapsed-day count, not the full week
        baseline_counts.append(visits_in_range(prior_monday, prior_end))

    if daily.index.min() > this_monday - pd.Timedelta(weeks=MIN_WEEKS_FOR_ANOMALY):
        return None  # not enough real history yet to know what "normal" looks like

    baseline = pd.Series(baseline_counts)
    mean, std = baseline.mean(), baseline.std()
    if std == 0 or pd.isna(std):
        return None  # no variance to compare against - can't call anything an outlier

    z = (this_week_count - mean) / std
    if abs(z) < ANOMALY_STDDEV_THRESHOLD:
        return None  # within normal range - not a finding

    direction = "positive" if z > 0 else "negative"
    pct_diff = round(((this_week_count - mean) / mean) * 100) if mean > 0 else 0
    verb = "above" if z > 0 else "below"
    return {
        "insight_type": "anomaly",
        "title": f"This week's visits are {abs(pct_diff)}% {verb} the usual pattern",
        "detail": f"{this_week_count} visits Monday through yesterday vs a typical {round(mean)} over the same {days_elapsed} days in the last {MIN_WEEKS_FOR_ANOMALY} weeks - a genuine deviation, not normal week-to-week noise.",
        "direction": direction,
        "metric_value": float(this_week_count),
    }


# ─────────────────────────────────────────────────────────────────
# 2. Cohort trend shift — is one segment drifting from the other?
# ─────────────────────────────────────────────────────────────────
def detect_cohort_shift(tx: pd.DataFrame, profiles: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    """Compares each segment's visit volume over the last 60 days
    against the 60 days before that. Flags a segment whose share of
    total visits has shifted meaningfully - a genuine drift, not the
    at-risk score (which flags individuals, not group trends)."""
    merged = tx.merge(profiles, on="customer_key", how="left")
    merged = merged.dropna(subset=["segment"])
    if merged.empty:
        return None
    if as_of - pd.Timedelta(days=120) < DATA_RELIABLE_FROM:
        return None  # the "60 days before that" window would reach back into the unreliable, Excel-uploaded period - not an honest comparison yet

    recent_start, recent_end = as_of - pd.Timedelta(days=60), as_of
    prior_start, prior_end = as_of - pd.Timedelta(days=120), as_of - pd.Timedelta(days=60)

    recent = merged[(merged["transaction_date"] > recent_start) & (merged["transaction_date"] <= recent_end)]
    prior = merged[(merged["transaction_date"] > prior_start) & (merged["transaction_date"] <= prior_end)]
    if len(recent) < MIN_TX_PER_COHORT or len(prior) < MIN_TX_PER_COHORT:
        return None  # not enough transactions in one of the windows to compare honestly

    recent_share = recent["segment"].value_counts(normalize=True)
    prior_share = prior["segment"].value_counts(normalize=True)

    biggest_shift, biggest_segment = 0, None
    for segment in recent_share.index:
        if segment not in prior_share.index:
            continue
        delta_pct = (recent_share[segment] - prior_share[segment]) * 100
        if abs(delta_pct) > abs(biggest_shift):
            biggest_shift, biggest_segment = delta_pct, segment

    if biggest_segment is None or abs(biggest_shift) < COHORT_DELTA_THRESHOLD_PCT:
        return None

    direction = "positive" if biggest_shift > 0 else "negative"
    other_segment = "girl" if biggest_segment == "boy" else "boy"
    recent_count = int(recent["segment"].eq(biggest_segment).sum())
    prior_count = int(prior["segment"].eq(biggest_segment).sum())
    # Plain language, not statistics jargon - "share" and "points" mean
    # nothing to a shop owner scanning this quickly. Says directly
    # whether one group is visiting more or less than they used to, in
    # real visit counts, plus why this is actually worth their
    # attention rather than just a number.
    if direction == "negative":
        title = f"Fewer {biggest_segment} customers coming in lately, more {other_segment}"
        why = f"Two months ago, {biggest_segment} and {other_segment} customers were closer to even. Now {other_segment} customers make up more of your visits. Worth checking if a recent promotion, stylist change, or seasonal reason (school terms, holidays) explains it - or if it's a real gap forming with {biggest_segment} families that's worth addressing directly."
    else:
        title = f"More {biggest_segment} customers coming in lately, compared to {other_segment}"
        why = f"{biggest_segment.capitalize()} customers have become a bigger part of your business over the last 2 months. Good to know if you're planning promotions or stock - and worth understanding what's driving it, so you can keep it going."
    return {
        "insight_type": "cohort",
        "title": title,
        "detail": f"{recent_count} {biggest_segment} visits in the last 60 days ({round(recent_share[biggest_segment]*100)}% of all visits), vs {prior_count} in the 60 days before that ({round(prior_share[biggest_segment]*100)}%). {why}",
        "direction": direction,
        "metric_value": float(biggest_shift),
    }


# ─────────────────────────────────────────────────────────────────
# 3. Stylist patterns — surfaced from the existing weekly snapshot,
#    not recomputed here. See module docstring for why.
# ─────────────────────────────────────────────────────────────────
def surface_stylist_pattern(engine) -> dict | None:
    query = "select stylist, total_customers, at_risk, at_risk_percent from mw_stylist_performance_snapshot where tenant_id = %(tenant_id)s"
    df = pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})
    df = df[df["total_customers"] >= 10]  # ignore stylists with too few attributed customers to mean anything
    if len(df) < 2:
        return None  # need at least 2 stylists to meaningfully compare

    tenant_avg = df["at_risk_percent"].mean()
    df["delta"] = df["at_risk_percent"] - tenant_avg
    row = df.loc[df["delta"].abs().idxmax()]
    if abs(row["delta"]) < 10:  # less than a 10-point swing isn't worth surfacing
        return None

    direction = "negative" if row["delta"] > 0 else "positive"  # higher at-risk % is the bad direction
    verb = "higher" if row["delta"] > 0 else "lower"
    return {
        "insight_type": "stylist",
        "title": f"{row['stylist']}'s customers are {abs(round(row['delta']))} points {verb} at-risk than average",
        "detail": f"{row['stylist']}: {round(row['at_risk_percent'])}% at-risk vs a {round(tenant_avg)}% tenant average, across {int(row['total_customers'])} customers. From the most recent weekly model run, not a live daily computation.",
        "direction": direction,
        "metric_value": float(row["delta"]),
    }


# ─────────────────────────────────────────────────────────────────
# 4. Revenue pacing — where is this month actually heading?
# ─────────────────────────────────────────────────────────────────
def compute_pacing(revenue: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    """Compares month-to-date revenue through YESTERDAY against the
    same day-of-month range last month - genuinely like-to-like, not a
    full-month projection versus a full prior-month total (which
    compares different kinds of numbers). Today is excluded since it
    may still be incomplete."""
    yesterday = as_of - pd.Timedelta(days=1)
    month_start = as_of.replace(day=1)
    days_elapsed = (yesterday - month_start).days + 1
    if days_elapsed < 2:
        return None  # too early in the month for a comparison to mean anything

    mtd = revenue[(revenue["transaction_date"] >= month_start) & (revenue["transaction_date"] <= yesterday)]["amount"].sum()
    if mtd <= 0:
        return None

    prior_month_end = month_start - pd.Timedelta(days=1)
    prior_month_start = prior_month_end.replace(day=1)
    prior_month_same_range_end = prior_month_start + pd.Timedelta(days=days_elapsed - 1)
    prior_mtd = revenue[(revenue["transaction_date"] >= prior_month_start) & (revenue["transaction_date"] <= prior_month_same_range_end)]["amount"].sum()
    if prior_mtd <= 0:
        return None  # no honest comparison possible without a real same-period prior total

    pct_vs_prior = round(((mtd - prior_mtd) / prior_mtd) * 100)
    direction = "positive" if pct_vs_prior >= 0 else "negative"
    verb = "ahead of" if pct_vs_prior >= 0 else "behind"
    return {
        "insight_type": "pacing",
        "title": f"This month is running {abs(pct_vs_prior)}% {verb} last month, same point",
        "detail": f"{round(mtd)} so far this month (day 1 through yesterday, {days_elapsed} days) vs {round(prior_mtd)} over the same {days_elapsed} days last month.",
        "direction": direction,
        "metric_value": float(pct_vs_prior),
    }


def main():
    print(f"Computing daily intelligence for tenant: {TENANT_ID}")
    engine = create_engine(DATABASE_URL)
    as_of = pd.Timestamp(datetime.now(timezone.utc).date())

    tx = load_transactions(engine)
    revenue = load_all_revenue(engine)
    profiles = load_profiles(engine)
    print(f"  Loaded {len(tx)} customer-matched transactions, {len(revenue)} total transactions (all revenue), {len(profiles)} customer profiles")

    diagnose_queue_revenue(engine, as_of)

    findings = []
    for fn, args in [
        (detect_anomaly, (tx, as_of)),
        (detect_cohort_shift, (tx, profiles, as_of)),
        (compute_pacing, (revenue, as_of)),
    ]:
        result = fn(*args)
        if result:
            findings.append(result)
            print(f"  [{result['insight_type']}] {result['title']}")
        else:
            print(f"  [{fn.__name__}] nothing to report - either not enough data, or genuinely nothing unusual")

    stylist_result = surface_stylist_pattern(engine)
    if stylist_result:
        findings.append(stylist_result)
        print(f"  [stylist] {stylist_result['title']}")
    else:
        print("  [stylist] nothing to report")

    with engine.begin() as conn:
        conn.exec_driver_sql("delete from mw_daily_intelligence where tenant_id = %(tenant_id)s and computed_for_date = current_date", {"tenant_id": TENANT_ID})
        for f in findings:
            conn.exec_driver_sql(
                """insert into mw_daily_intelligence (tenant_id, insight_type, title, detail, direction, metric_value)
                   values (%(tenant_id)s, %(insight_type)s, %(title)s, %(detail)s, %(direction)s, %(metric_value)s)""",
                {**f, "tenant_id": TENANT_ID},
            )
    print(f"\n{len(findings)} finding(s) written for today.")


if __name__ == "__main__":
    main()
