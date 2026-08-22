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


def load_profiles(engine) -> pd.DataFrame:
    query = "select customer_key, segment from mw_customer_profile where tenant_id = %(tenant_id)s"
    return pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})


# ─────────────────────────────────────────────────────────────────
# 1. Anomaly detection — is this week genuinely unusual?
# ─────────────────────────────────────────────────────────────────
def detect_anomaly(tx: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    """Compares this week's visit count against the mean and standard
    deviation of the business's own prior full weeks. Returns None
    (rather than a fabricated finding) if there isn't enough history
    to establish a genuine baseline, or if this week isn't actually
    unusual - a quiet week is not itself a finding."""
    daily = tx.set_index("transaction_date").resample("D").size()
    weekly = daily.resample("W-SAT").sum()  # week ending Saturday, matches the salon's own week
    if len(weekly) < MIN_WEEKS_FOR_ANOMALY + 1:
        return None  # not enough history yet to know what "normal" looks like

    this_week = weekly.iloc[-1]
    baseline = weekly.iloc[-(MIN_WEEKS_FOR_ANOMALY + 1):-1]
    mean, std = baseline.mean(), baseline.std()
    if std == 0 or pd.isna(std):
        return None  # no variance to compare against - can't call anything an outlier

    z = (this_week - mean) / std
    if abs(z) < ANOMALY_STDDEV_THRESHOLD:
        return None  # within normal range - not a finding

    direction = "positive" if z > 0 else "negative"
    pct_diff = round(((this_week - mean) / mean) * 100) if mean > 0 else 0
    verb = "above" if z > 0 else "below"
    return {
        "insight_type": "anomaly",
        "title": f"This week's visits are {abs(pct_diff)}% {verb} the usual pattern",
        "detail": f"{int(this_week)} visits this week vs a typical {round(mean)} (based on the last {MIN_WEEKS_FOR_ANOMALY} weeks) - a genuine deviation, not normal week-to-week noise.",
        "direction": direction,
        "metric_value": float(this_week),
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
    verb = "grown" if biggest_shift > 0 else "shrunk"
    return {
        "insight_type": "cohort",
        "title": f"{biggest_segment.capitalize()} segment has {verb} {abs(round(biggest_shift))} points as a share of visits",
        "detail": f"{biggest_segment.capitalize()} made up {round(recent_share[biggest_segment]*100)}% of visits in the last 60 days, vs {round(prior_share[biggest_segment]*100)}% in the 60 days before that.",
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
def compute_pacing(tx: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    month_start = as_of.replace(day=1)
    days_elapsed = (as_of - month_start).days + 1
    days_in_month = (month_start + pd.offsets.MonthEnd(1)).day
    if days_elapsed < 3:
        return None  # too early in the month for a pace projection to mean anything

    mtd = tx[(tx["transaction_date"] >= month_start) & (tx["transaction_date"] <= as_of)]["amount"].sum()
    if mtd <= 0:
        return None

    daily_pace = mtd / days_elapsed
    projected = daily_pace * days_in_month

    prior_month_end = month_start - pd.Timedelta(days=1)
    prior_month_start = prior_month_end.replace(day=1)
    prior_month_total = tx[(tx["transaction_date"] >= prior_month_start) & (tx["transaction_date"] <= prior_month_end)]["amount"].sum()
    if prior_month_total <= 0:
        return None  # no honest comparison possible without a real prior-month total

    pct_vs_prior = round(((projected - prior_month_total) / prior_month_total) * 100)
    direction = "positive" if pct_vs_prior >= 0 else "negative"
    verb = "ahead of" if pct_vs_prior >= 0 else "behind"
    return {
        "insight_type": "pacing",
        "title": f"On pace to finish {abs(pct_vs_prior)}% {verb} last month",
        "detail": f"At the current daily pace ({round(daily_pace)}/day, {days_elapsed} of {days_in_month} days elapsed), this month projects to ~{round(projected)}, vs {round(prior_month_total)} last month.",
        "direction": direction,
        "metric_value": float(pct_vs_prior),
    }


def main():
    print(f"Computing daily intelligence for tenant: {TENANT_ID}")
    engine = create_engine(DATABASE_URL)
    as_of = pd.Timestamp(datetime.now(timezone.utc).date())

    tx = load_transactions(engine)
    profiles = load_profiles(engine)
    print(f"  Loaded {len(tx)} transactions, {len(profiles)} customer profiles")

    findings = []
    for fn, args in [
        (detect_anomaly, (tx, as_of)),
        (detect_cohort_shift, (tx, profiles, as_of)),
        (compute_pacing, (tx, as_of)),
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
