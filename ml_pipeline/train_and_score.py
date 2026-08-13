"""
train_and_score.py — MiniCuts / Zen Platform return-probability model.

Real, full-cycle ML pipeline: pulls transaction history from Postgres,
builds a labeled dataset with pandas, trains a scikit-learn logistic
regression, evaluates it on a genuine held-out split, then scores every
current customer and writes both the model and the predictions back to
the database.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:port/dbname"
    export TENANT_ID="minicuts"
    python3 train_and_score.py

Designed to be run on a schedule (see the GitHub Actions workflow) — each
run trains a fresh model on the latest data and rescoring every customer,
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
FEATURE_NAMES = ["days_since_previous_visit", "visit_number", "days_since_first_visit", "is_girl_segment"]

DATABASE_URL = os.environ.get("DATABASE_URL")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")

if not DATABASE_URL:
    print("ERROR: set DATABASE_URL (your Supabase connection string, found under Project Settings > Database > Connection string > URI).", file=sys.stderr)
    sys.exit(1)


def load_transactions(engine) -> pd.DataFrame:
    """Pull every transaction for this tenant into a DataFrame — the raw
    material for feature engineering below."""
    query = """
        select customer_mobile, customer_name, transaction_date
        from mw_transactions
        where tenant_id = %(tenant_id)s and customer_mobile is not null
        order by customer_mobile, transaction_date asc
    """
    df = pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df


def load_profiles(engine) -> pd.DataFrame:
    query = "select customer_mobile, segment from mw_customer_profile where tenant_id = %(tenant_id)s"
    return pd.read_sql(query, engine, params={"tenant_id": TENANT_ID})


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
    tx = tx.merge(profiles, on="customer_mobile", how="left")
    rows = []
    for mobile, g in tx.groupby("customer_mobile"):
        dates = g["transaction_date"].sort_values().tolist()
        segment = g["segment"].iloc[0] if "segment" in g.columns else None
        first_date = dates[0]
        for i in range(1, len(dates)):
            this_date = dates[i]
            days_since_visit = (as_of - this_date).days
            if days_since_visit < RETURN_WINDOW_DAYS:
                continue  # not enough elapsed time to know the true outcome yet
            future_dates = dates[i + 1:]
            returned = any((d - this_date).days <= RETURN_WINDOW_DAYS for d in future_dates)
            rows.append({
                "customer_mobile": mobile,
                "days_since_previous_visit": (this_date - dates[i - 1]).days,
                "visit_number": i + 1,
                "days_since_first_visit": (this_date - first_date).days,
                "is_girl_segment": 1 if segment == "girl" else 0,
                "label": int(returned),
            })
    return pd.DataFrame(rows)


def build_scoring_set(tx: pd.DataFrame, profiles: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """One row per customer using their CURRENT situation (most recent
    visit) — what we actually want a prediction for. Needs at least 2
    visits total, same reason as training: the 'days since previous
    visit' feature isn't defined on a single visit."""
    tx = tx.merge(profiles, on="customer_mobile", how="left")
    rows = []
    for mobile, g in tx.groupby("customer_mobile"):
        dates = g["transaction_date"].sort_values().tolist()
        if len(dates) < 2:
            continue
        name = g["customer_name"].iloc[-1]
        segment = g["segment"].iloc[0] if "segment" in g.columns else None
        first_date, last_date, prev_date = dates[0], dates[-1], dates[-2]
        rows.append({
            "customer_mobile": mobile,
            "customer_name": name,
            "days_since_previous_visit": (last_date - prev_date).days,
            "visit_number": len(dates),
            "days_since_first_visit": (last_date - first_date).days,
            "is_girl_segment": 1 if segment == "girl" else 0,
        })
    return pd.DataFrame(rows)


def main():
    engine = create_engine(DATABASE_URL)
    conn = psycopg2.connect(DATABASE_URL)  # separate raw connection for writes — psycopg2 handles arrays/transactions more directly than going back through SQLAlchemy for inserts
    as_of = pd.Timestamp(datetime.now(timezone.utc).date())

    print(f"Loading data for tenant '{TENANT_ID}'...")
    tx = load_transactions(engine)
    profiles = load_profiles(engine)
    print(f"  {len(tx)} transactions across {tx['customer_mobile'].nunique()} customers")

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
            """insert into mw_customer_predictions (tenant_id, customer_mobile, customer_name, probability, tier, model_version)
               values (%s, %s, %s, %s, %s, %s)""",
            (TENANT_ID, row["customer_mobile"], row["customer_name"], float(row["probability"]), str(row["tier"]), next_version),
        )
    conn.commit()

    tier_counts = score_df["tier"].value_counts()
    print(f"  Scored {len(score_df)} customers: {tier_counts.to_dict()}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
