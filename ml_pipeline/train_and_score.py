"""
train_and_score.py — MiniCuts / Zen Platform return-probability model +
weekly load forecast.

Real, full-cycle ML pipeline: pulls transaction history from Postgres,
builds a labeled dataset with pandas, trains a scikit-learn logistic
regression, evaluates it on a genuine held-out split, then scores every
current customer and writes both the model and the predictions back to
the database. Also computes a weekly visit-load pattern (day-of-week
averages) for staffing/planning.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:port/dbname"
    export TENANT_ID="minicuts"
    python3 train_and_score.py

Designed to be run on a schedule (see the GitHub Actions workflow) — each
run trains a fresh model on the latest data and rescores every customer,
so predictions never go stale.
"""
import os
import sys
import psycopg2
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime, timezone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

RETURN_WINDOW_DAYS = 90
MIN_TRAINING_EXAMPLES = 30
# avg_spend is new here — closes a real gap where 'amount' data existed
# but the model never used it (the "Monetary" in Recency/Frequency/
# Monetary — only the first two were being used before).
FEATURE_NAMES = ["days_since_previous_visit", "visit_number", "days_since_first_visit", "is_girl_segment", "avg_spend"]
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

DATABASE_URL = os.environ.get("DATABASE_URL")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")

if not DATABASE_URL:
    print("ERROR: set DATABASE_URL (your Supabase connection string, found under Project Settings > Database > Connection string > URI).", file=sys.stderr)
    sys.exit(1)


def load_transactions(engine) -> pd.DataFrame:
    """Pull every transaction for this tenant into a DataFrame — the raw
    material for feature engineering below. Grouped by customer_key (the
    real per-person identity), not phone number — a shared phone number
    across siblings must never merge two people into one record here."""
    query = """
        select customer_key, customer_mobile, customer_name, transaction_date, transaction_datetime, amount, stylist_phone
        from mw_transactions
        where tenant_id = %(tenant_id)s and customer_key is not null
        order by customer_key, transaction_date asc
    """
    df = pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["transaction_datetime"] = pd.to_datetime(df["transaction_datetime"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def load_profiles(engine) -> pd.DataFrame:
    query = "select customer_key, segment from mw_customer_profile where tenant_id = %(tenant_id)s"
    return pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})


def load_stylists_roster(engine) -> pd.DataFrame:
    query = "select phone_number, name from mw_stylists where tenant_id = %(tenant_id)s"
    return pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})


def compute_stylist_performance(tx: pd.DataFrame, score_df: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    """
    Same logic as the (now-retired) live stylist_performance tool: for
    every customer a stylist has EVER served, check their CURRENT
    return-probability tier. stylist_name (from the queue-based sync,
    a real name) is preferred over stylist_phone (resolved via the
    roster — the Excel-upload path, which only ever has a phone number).
    """
    name_by_phone = dict(zip(roster["phone_number"], roster["name"]))
    tier_by_key = dict(zip(score_df["customer_key"], score_df["tier"]))

    def resolve_label(row):
        if pd.notna(row.get("stylist_name")):
            return row["stylist_name"]
        if pd.notna(row.get("stylist_phone")):
            return name_by_phone.get(row["stylist_phone"], f"Unmapped ({row['stylist_phone']})")
        return None

    tx = tx.copy()
    tx["stylist_label"] = tx.apply(resolve_label, axis=1)
    attributed = tx.dropna(subset=["stylist_label"])
    if attributed.empty:
        return pd.DataFrame(columns=["stylist", "total_customers", "at_risk", "likely_to_return", "at_risk_percent"])

    rows = []
    for stylist, group in attributed.groupby("stylist_label"):
        customers = group["customer_key"].unique()
        tiers = [tier_by_key.get(c) for c in customers]
        at_risk = sum(1 for t in tiers if t == "at_risk")
        likely = sum(1 for t in tiers if t == "likely")
        total = len(customers)
        rows.append({
            "stylist": stylist,
            "total_customers": total,
            "at_risk": at_risk,
            "likely_to_return": likely,
            "at_risk_percent": round(at_risk / total * 100, 1) if total else 0.0,
        })
    return pd.DataFrame(rows)


def compute_campaign_performance(engine, return_window_days: int = 30) -> pd.DataFrame:
    """Same 'did the message actually work' measure as the live tool —
    checks whether each sent customer had a NEW transaction within the
    window afterward, not just how many messages went out."""
    decisions = pd.read_sql(
        "select customer_id, campaign_key, status, created_at from mw_agent_decisions where tenant_id = %(tenant_id)s",
        engine, params={"tenant_id": TENANT_ID},
    )
    if decisions.empty:
        return pd.DataFrame(columns=["campaign_key", "total_decisions", "total_sent", "returned_within_window", "return_rate_percent"])
    # tz_localize(None) strips timezone info — mw_agent_decisions.created_at
    # is timestamptz (timezone-aware) but mw_transactions.transaction_date
    # is a plain date (timezone-naive); comparing the two directly raises
    # a TypeError otherwise. The date column has no timezone to begin
    # with, so normalizing to naive is the correct fix, not a workaround.
    decisions["created_at"] = pd.to_datetime(decisions["created_at"]).dt.tz_localize(None)

    tx_dates = pd.read_sql(
        "select customer_key, transaction_date from mw_transactions where tenant_id = %(tenant_id)s",
        engine, params={"tenant_id": TENANT_ID},
    )
    tx_dates["transaction_date"] = pd.to_datetime(tx_dates["transaction_date"])
    tx_by_customer = tx_dates.groupby("customer_key")["transaction_date"].apply(list).to_dict()

    rows = []
    for campaign_key, group in decisions.groupby("campaign_key"):
        sent = group[group["status"].isin(["sent", "auto_sent"])]
        returned = 0
        for _, d in sent.iterrows():
            dates = tx_by_customer.get(d["customer_id"], [])
            sent_at = d["created_at"]
            if any(sent_at < dt <= sent_at + pd.Timedelta(days=return_window_days) for dt in dates):
                returned += 1
        total_sent = len(sent)
        rows.append({
            "campaign_key": campaign_key,
            "total_decisions": len(group),
            "total_sent": total_sent,
            "returned_within_window": returned,
            "return_rate_percent": round(returned / total_sent * 100, 1) if total_sent else 0.0,
        })
    return pd.DataFrame(rows)


def build_training_set(tx: pd.DataFrame, profiles: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Builds one labeled row per visit (from each customer's 2nd visit
    onward — the 1st visit has no 'days since previous visit' to measure).

    Label: did the customer return again within RETURN_WINDOW_DAYS after
    this visit? Only visits old enough that we genuinely KNOW the answer
    are used — a visit from last week can't be labeled yet, since the
    90-day window hasn't closed. Labeling it "no" would be a guess dressed
    up as ground truth, which is exactly the kind of shortcut we're
    avoiding here.
    """
    tx = tx.merge(profiles, on="customer_key", how="left")
    rows = []
    for key, g in tx.groupby("customer_key"):
        g = g.sort_values("transaction_date")
        dates = g["transaction_date"].tolist()
        amounts = g["amount"].tolist()
        segment = g["segment"].iloc[0] if "segment" in g.columns else None
        first_date = dates[0]
        for i in range(1, len(dates)):
            this_date = dates[i]
            days_since_visit = (as_of - this_date).days
            if days_since_visit < RETURN_WINDOW_DAYS:
                continue  # not enough elapsed time to know the true outcome yet
            future_dates = dates[i + 1:]
            returned = any((d - this_date).days <= RETURN_WINDOW_DAYS for d in future_dates)
            # Cumulative average up to AND INCLUDING this visit — never
            # peek at amounts from visits that haven't happened yet at
            # this point in the customer's history, or the label would be
            # leaking future information into a "past" feature.
            avg_spend_so_far = sum(amounts[: i + 1]) / (i + 1)
            rows.append({
                "customer_key": key,
                "days_since_previous_visit": (this_date - dates[i - 1]).days,
                "visit_number": i + 1,
                "days_since_first_visit": (this_date - first_date).days,
                "is_girl_segment": 1 if segment == "girl" else 0,
                "avg_spend": avg_spend_so_far,
                "label": int(returned),
            })
    return pd.DataFrame(rows)


def build_scoring_set(tx: pd.DataFrame, profiles: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """One row per customer identity using their CURRENT situation (most
    recent visit) — what we actually want a prediction for. Needs at
    least 2 visits total, same reason as training."""
    tx = tx.merge(profiles, on="customer_key", how="left")
    rows = []
    for key, g in tx.groupby("customer_key"):
        g = g.sort_values("transaction_date")
        dates = g["transaction_date"].tolist()
        if len(dates) < 2:
            continue
        amounts = g["amount"].tolist()
        mobile = g["customer_mobile"].iloc[-1]
        name = g["customer_name"].iloc[-1]
        segment = g["segment"].iloc[0] if "segment" in g.columns else None
        first_date, last_date, prev_date = dates[0], dates[-1], dates[-2]
        rows.append({
            "customer_key": key,
            "customer_mobile": mobile,
            "customer_name": name,
            "days_since_previous_visit": (last_date - prev_date).days,
            "visit_number": len(dates),
            "days_since_first_visit": (last_date - first_date).days,
            "is_girl_segment": 1 if segment == "girl" else 0,
            "avg_spend": sum(amounts) / len(amounts),
        })
    return pd.DataFrame(rows)


def compute_load_forecast(tx: pd.DataFrame) -> pd.DataFrame:
    """
    Weekly visit-LOAD pattern, not individual future-date predictions —
    the honest version of "load forecast" given ~15 months of history:
    enough repetitions of "what does a typical Monday look like" (60+
    Mondays in the data) to be genuinely defensible. NOT enough distinct
    Decembers or Ramadans to claim real yearly seasonality from a single
    year — so that claim is deliberately NOT made here.

    Two numbers per weekday: the all-time average, and a recent-8-week
    average — the gap between them is what actually reveals a trend
    (getting busier or quieter lately), which the all-time number alone
    would hide.
    """
    daily_counts = tx.groupby(tx["transaction_date"].dt.date).size()
    daily_counts.index = pd.to_datetime(daily_counts.index)
    full_range = pd.date_range(daily_counts.index.min(), daily_counts.index.max(), freq="D")
    daily_counts = daily_counts.reindex(full_range, fill_value=0)

    df = pd.DataFrame({"date": daily_counts.index, "visits": daily_counts.values})
    df["day_of_week"] = df["date"].dt.dayofweek.map(lambda x: (x + 1) % 7)  # pandas: Mon=0..Sun=6 -> convert to Sun=0..Sat=6

    all_time_avg = df.groupby("day_of_week")["visits"].mean()

    recent_cutoff = df["date"].max() - pd.Timedelta(days=56)  # last 8 weeks
    recent = df[df["date"] > recent_cutoff]
    recent_avg = recent.groupby("day_of_week")["visits"].mean()

    rows = []
    for dow in range(7):
        rows.append({
            "day_of_week": dow,
            "day_name": DAY_NAMES[dow],
            "avg_visits": round(float(all_time_avg.get(dow, 0)), 2),
            "recent_avg_visits": round(float(recent_avg.get(dow, 0)), 2),
        })
    return pd.DataFrame(rows)


def compute_hourly_load_forecast(tx: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """
    Average visits by hour-of-day — deliberately NOT crossed with day of
    week, which would leave too few real historical data points per
    bucket to trust (a specific "Tuesday 11am" bucket might have only a
    handful of visits across 15 months; "11am generally" has far more).

    Honest limitation, stated in the return value, not hidden: this can
    only use rows that actually have a real timestamp, not just a date.
    Historical rows uploaded before the ingest fix don't have one yet —
    the coverage percentage this returns tells you exactly how much of
    your data can currently answer this question.
    """
    with_time = tx.dropna(subset=["transaction_datetime"])
    coverage = len(with_time) / len(tx) if len(tx) else 0.0
    if with_time.empty:
        return pd.DataFrame(columns=["hour_of_day", "avg_visits"]), coverage

    daily_hourly = with_time.groupby([with_time["transaction_datetime"].dt.date, with_time["transaction_datetime"].dt.hour]).size()
    daily_hourly.index.names = ["date", "hour"]
    hourly_avg = daily_hourly.groupby("hour").mean()

    rows = [{"hour_of_day": h, "avg_visits": round(float(hourly_avg.get(h, 0)), 2)} for h in range(24)]
    return pd.DataFrame(rows), coverage


def compute_analytics_snapshot(tx: pd.DataFrame, profiles: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Precomputes the same metrics the semantic layer (mw_metrics) defines,
    for the whole customer base AND each segment separately — this is
    what makes get_metric's "check the snapshot first" fast path real
    rather than empty plumbing. Refreshed every training run (weekly),
    same cadence as the model itself.
    """
    tx = tx.merge(profiles, on="customer_key", how="left")
    rows = []

    def metrics_for(subset: pd.DataFrame, segment_label: str):
        if subset.empty:
            return
        last_visit = subset.groupby("customer_key")["transaction_date"].max()
        active_30d = int((last_visit >= as_of - pd.Timedelta(days=30)).sum())
        lapsed_90d = int((last_visit <= as_of - pd.Timedelta(days=90)).sum())
        total_revenue = float(subset["amount"].sum())
        gaps = []
        for _, g in subset.groupby("customer_key"):
            dates = g["transaction_date"].sort_values().tolist()
            for i in range(1, len(dates)):
                gaps.append((dates[i] - dates[i - 1]).days)
        avg_gap = float(sum(gaps) / len(gaps)) if gaps else None

        rows.append({"metric_key": "active_customers_30d", "segment": segment_label, "value": active_30d})
        rows.append({"metric_key": "lapsed_customers_90d", "segment": segment_label, "value": lapsed_90d})
        rows.append({"metric_key": "total_revenue", "segment": segment_label, "value": round(total_revenue, 2)})
        if avg_gap is not None:
            rows.append({"metric_key": "avg_visit_gap_days", "segment": segment_label, "value": round(avg_gap, 1)})

    # "all" is a real value here, not a placeholder for missing data —
    # segment is part of this table's primary key, and primary key
    # columns can never be NULL in Postgres. Using an actual sentinel
    # string avoids that entirely, rather than fighting it.
    metrics_for(tx, "all")
    for seg in ["boy", "girl"]:
        metrics_for(tx[tx["segment"].str.lower().fillna("") == seg], seg)

    return pd.DataFrame(rows)


def main():
    engine = create_engine(DATABASE_URL)
    conn = psycopg2.connect(DATABASE_URL)  # separate raw connection for writes — psycopg2 handles arrays/transactions more directly than going back through SQLAlchemy for inserts
    as_of = pd.Timestamp(datetime.now(timezone.utc).date())

    print(f"Loading data for tenant '{TENANT_ID}'...")
    tx = load_transactions(engine)
    profiles = load_profiles(engine)
    print(f"  {len(tx)} transactions across {tx['customer_key'].nunique()} distinct customer identities")

    print("Building labeled training set...")
    train_df = build_training_set(tx, profiles, as_of)
    print(f"  {len(train_df)} usable training examples (visits old enough to have a known outcome)")

    if len(train_df) < MIN_TRAINING_EXAMPLES:
        print(f"ERROR: only {len(train_df)} training examples — need at least {MIN_TRAINING_EXAMPLES}. "
              f"Upload more historical data or wait for more visit history to accumulate.", file=sys.stderr)
        sys.exit(1)

    X = train_df[FEATURE_NAMES].values
    y = train_df["label"].values
    print(f"  Class balance: {y.sum()} returned / {len(y) - y.sum()} did not ({y.mean():.1%} return rate)")

    # Genuine held-out validation split — the model NEVER sees this data
    # during training. This is what makes the accuracy number honest.
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)  # transform only, using TRAINING stats — never refit on validation data

    print("Training logistic regression...")
    model = LogisticRegression(C=1.0, max_iter=1000)
    model.fit(X_train_scaled, y_train)

    val_preds = model.predict(X_val_scaled)
    val_probs = model.predict_proba(X_val_scaled)[:, 1]
    accuracy = accuracy_score(y_val, val_preds)
    auc = roc_auc_score(y_val, val_probs) if len(set(y_val)) > 1 else None

    print(f"\n  Validation accuracy: {accuracy:.1%}  (on {len(y_val)} held-out examples the model never trained on)")
    if auc is not None:
        print(f"  Validation ROC-AUC:  {auc:.3f}")
    print("\n  Classification report:")
    print(classification_report(y_val, val_preds, target_names=["did not return", "returned"], zero_division=0))

    print("  Learned feature weights (standardized — sign shows direction, magnitude shows strength):")
    for name, w in zip(FEATURE_NAMES, model.coef_[0]):
        direction = "increases" if w > 0 else "decreases"
        print(f"    {name:32s} {w:+.3f}   ({direction} return likelihood)")

    # ── Persist the model ──
    cur = conn.cursor()
    cur.execute("select coalesce(max(version), 0) from mw_ml_models where tenant_id = %s and model_type = 'return_probability'", (TENANT_ID,))
    next_version = cur.fetchone()[0] + 1
    cur.execute("update mw_ml_models set active = false where tenant_id = %s and model_type = 'return_probability'", (TENANT_ID,))
    cur.execute(
        """insert into mw_ml_models
           (tenant_id, model_type, version, feature_names, weights, bias, feature_means, feature_stds,
            training_examples, validation_accuracy, validation_auc, validation_examples, active)
           values (%s, 'return_probability', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)""",
        (TENANT_ID, next_version, FEATURE_NAMES, [float(w) for w in model.coef_[0]], float(model.intercept_[0]),
         [float(m) for m in scaler.mean_], [float(s) for s in scaler.scale_], len(X_train), float(accuracy), float(auc) if auc else None, len(X_val)),
    )
    print(f"\n  Saved model version {next_version} to mw_ml_models")

    # ── Score every current customer with the freshly trained model ──
    print("Scoring current customers...")
    score_df = build_scoring_set(tx, profiles, as_of)
    Xs = scaler.transform(score_df[FEATURE_NAMES].values)
    probs = model.predict_proba(Xs)[:, 1]
    score_df["probability"] = probs
    score_df["tier"] = pd.cut(probs, bins=[-0.01, 0.35, 0.6, 1.01], labels=["at_risk", "uncertain", "likely"])

    cur.execute("delete from mw_customer_predictions where tenant_id = %s", (TENANT_ID,))
    for _, row in score_df.iterrows():
        cur.execute(
            """insert into mw_customer_predictions (tenant_id, customer_key, customer_mobile, customer_name, probability, tier, model_version)
               values (%s, %s, %s, %s, %s, %s, %s)""",
            (TENANT_ID, row["customer_key"], row["customer_mobile"], row["customer_name"], float(row["probability"]), str(row["tier"]), next_version),
        )

    tier_counts = score_df["tier"].value_counts()
    print(f"  Scored {len(score_df)} customer identities: {tier_counts.to_dict()}")

    # ── Stylist performance snapshot — replaces the old live-computed
    #    tool, same "instant read instead of live compute every time"
    #    upgrade already proven for the 4 core metrics ──
    print("\nComputing stylist performance snapshot...")
    roster = load_stylists_roster(engine)
    stylist_df = compute_stylist_performance(tx, score_df, roster)
    cur.execute("delete from mw_stylist_performance_snapshot where tenant_id = %s", (TENANT_ID,))
    for _, row in stylist_df.iterrows():
        cur.execute(
            """insert into mw_stylist_performance_snapshot (tenant_id, stylist, total_customers, at_risk, likely_to_return, at_risk_percent)
               values (%s, %s, %s, %s, %s, %s)""",
            (TENANT_ID, row["stylist"], int(row["total_customers"]), int(row["at_risk"]), int(row["likely_to_return"]), float(row["at_risk_percent"])),
        )
    print(f"  {len(stylist_df)} stylists computed" if not stylist_df.empty else "  No stylist-attributed transactions found yet")

    # ── Campaign performance snapshot — same 30-day return-window
    #    default the live tool always used ──
    print("\nComputing campaign performance snapshot...")
    campaign_df = compute_campaign_performance(engine, return_window_days=30)
    cur.execute("delete from mw_campaign_performance_snapshot where tenant_id = %s and return_window_days = 30", (TENANT_ID,))
    for _, row in campaign_df.iterrows():
        cur.execute(
            """insert into mw_campaign_performance_snapshot (tenant_id, campaign_key, return_window_days, total_decisions, total_sent, returned_within_window, return_rate_percent)
               values (%s, %s, %s, %s, %s, %s, %s)""",
            (TENANT_ID, row["campaign_key"], 30, int(row["total_decisions"]), int(row["total_sent"]), int(row["returned_within_window"]), float(row["return_rate_percent"])),
        )
    print(f"  {len(campaign_df)} campaigns computed" if not campaign_df.empty else "  No campaign decisions found yet")

    # ── Weekly load forecast ──
    print("\nComputing weekly load forecast...")
    forecast_df = compute_load_forecast(tx)
    cur.execute("delete from mw_load_forecast where tenant_id = %s", (TENANT_ID,))
    for _, row in forecast_df.iterrows():
        cur.execute(
            """insert into mw_load_forecast (tenant_id, day_of_week, day_name, avg_visits, recent_avg_visits, model_version)
               values (%s, %s, %s, %s, %s, %s)""",
            # float() here isn't optional — pandas silently re-casts even
            # explicitly-Python-float values back into numpy.float64 once
            # they're inside a DataFrame column, and psycopg2 can't adapt
            # that type on its own. Same fix already applied to the model
            # weights insert earlier; needed again at every new insert
            # point that pulls a value out of a DataFrame row.
            (TENANT_ID, int(row["day_of_week"]), row["day_name"], float(row["avg_visits"]), float(row["recent_avg_visits"]), next_version),
        )
    print(forecast_df.to_string(index=False))

    # ── Analytics snapshot — the "mini read replica" performance layer ──
    print("\nComputing analytics snapshot...")
    snapshot_df = compute_analytics_snapshot(tx, profiles, as_of)
    cur.execute("delete from mw_analytics_snapshot where tenant_id = %s", (TENANT_ID,))
    for _, row in snapshot_df.iterrows():
        cur.execute(
            """insert into mw_analytics_snapshot (tenant_id, metric_key, segment, value)
               values (%s, %s, %s, %s)
               on conflict (tenant_id, metric_key, segment) do update set value = excluded.value, computed_at = now()""",
            (TENANT_ID, row["metric_key"], row["segment"], float(row["value"])),
        )
    print(f"  {len(snapshot_df)} snapshot values computed")

    # ── Hourly load pattern ──
    print("\nComputing hourly load pattern...")
    hourly_df, time_coverage = compute_hourly_load_forecast(tx)
    print(f"  {time_coverage:.1%} of transactions have real time-of-day data — {'usable' if time_coverage > 0.3 else 'too sparse to trust yet, needs more time-stamped data'}")
    if not hourly_df.empty:
        cur.execute("delete from mw_hourly_load_forecast where tenant_id = %s", (TENANT_ID,))
        for _, row in hourly_df.iterrows():
            cur.execute(
                """insert into mw_hourly_load_forecast (tenant_id, hour_of_day, avg_visits, model_version)
                   values (%s, %s, %s, %s)""",
                (TENANT_ID, int(row["hour_of_day"]), float(row["avg_visits"]), next_version),
            )
        print(hourly_df.to_string(index=False))

    conn.commit()
    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
