"""
metric_learnings.py — finds patterns in the daily metrics without being
told what to look for.

WHAT THIS IS
    Unsupervised in the real sense: no labels, no target variable. It
    looks at ~400 days of daily metrics and reports what moves together,
    what varies by day of week, and where something structurally
    changed.

WHAT IT IS NOT
    It is not causal. "Wait time correlates with lower repeat visits"
    does not mean shorter waits cause more repeats - a busy Saturday
    produces both. Every finding is phrased as an association and the
    caveat travels with it.

THE MULTIPLE-COMPARISONS PROBLEM, AND WHY IT MATTERS HERE
    Eighteen metrics give 153 possible pairs. Testing all of them at
    p < 0.05 means roughly 8 will look significant by pure chance. A
    tool that reported those 8 as findings would be worse than useless -
    it would be confidently wrong, and there would be no way to tell
    which of its claims were real.

    So the threshold is corrected (Benjamini-Hochberg), and anything
    surviving is still reported with its sample size and correlation
    strength rather than as a fact.

Usage:
    export DATABASE_URL=...
    export TENANT_ID=minicuts
    python3 metric_learnings.py
"""
import os
import sys
import json
import psycopg2
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")
MIN_DAYS = 60          # below this, nothing is worth saying
FDR_Q = 0.10           # false discovery rate we accept

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
    sys.exit(1)


def pearson(xs, ys):
    """Correlation and a rough two-sided p-value, without scipy."""
    n = len(xs)
    if n < 10:
        return None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None, None
    r = sxy / (sxx * syy) ** 0.5
    r = max(-0.999999, min(0.999999, r))

    # t-statistic, then a normal approximation for the tail. Adequate
    # at n > 30, which is guaranteed by MIN_DAYS.
    t = abs(r) * ((n - 2) / (1 - r * r)) ** 0.5
    z = t / (1 + 0.147 * t * t / (n - 2)) ** 0.5 if n > 2 else 0
    # Abramowitz-Stegun tail approximation.
    p = 2 * (1 - 0.5 * (1 + _erf(z / (2 ** 0.5))))
    return r, max(0.0, min(1.0, p))


def _erf(x):
    s = 1 if x >= 0 else -1
    x = abs(x)
    a1, a2, a3, a4, a5, pp = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429, 0.3275911
    t = 1 / (1 + pp * x)
    y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (2.718281828 ** (-x * x))
    return s * y


def benjamini_hochberg(pvals, q):
    """Which tests survive once the number of tests is accounted for.

    Without this, testing 153 pairs at 0.05 yields ~8 false findings.
    """
    indexed = sorted(enumerate(pvals), key=lambda kv: kv[1])
    m = len(pvals)
    keep = set()
    for rank, (idx, p) in enumerate(indexed, start=1):
        if p <= (rank / m) * q:
            keep = set(i for i, _ in indexed[:rank])
    return keep


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        select metric_key, metric_date, value
        from mw_daily_metrics
        where tenant_id = %s and dimension = 'all' and value is not null
        order by metric_date
    """, (TENANT_ID,))
    rows = cur.fetchall()
    if not rows:
        print("No metrics yet. Run mw_refresh_daily_metrics first.")
        return

    series = {}
    for key, d, v in rows:
        series.setdefault(key, {})[d] = float(v)

    usable = {k: v for k, v in series.items() if len(v) >= MIN_DAYS}
    print(f"{len(series)} metrics, {len(usable)} with at least {MIN_DAYS} days.")
    if len(usable) < 2:
        print("Not enough history to compare anything yet.")
        return

    findings = []

    # ── What moves together ────────────────────────────────────────
    keys = sorted(usable)
    pairs, pvals = [], []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            common = sorted(set(usable[a]) & set(usable[b]))
            if len(common) < MIN_DAYS:
                continue
            xs = [usable[a][d] for d in common]
            ys = [usable[b][d] for d in common]
            r, p = pearson(xs, ys)
            if r is None:
                continue
            pairs.append((a, b, r, len(common)))
            pvals.append(p)

    survived = benjamini_hochberg(pvals, FDR_Q) if pvals else set()
    print(f"{len(pairs)} pairs tested, {len(survived)} survived correction "
          f"(without it, roughly {int(len(pairs) * 0.05)} would look significant by chance).")

    for idx, (a, b, r, n) in enumerate(pairs):
        if idx not in survived or abs(r) < 0.4:
            continue
        direction = "together" if r > 0 else "in opposite directions"
        findings.append({
            "kind": "association",
            "statement": f"{a.replace('_', ' ')} and {b.replace('_', ' ')} move {direction}",
            "strength": round(abs(r), 2),
            "observations": n,
            # Said every time, because the reader will otherwise supply
            # a causal story of their own.
            "caveat": "An association, not a cause. Both may follow from something else - a busy Saturday raises several of these at once.",
        })

    # ── Day of week ────────────────────────────────────────────────
    # Genuinely useful and safely interpretable: a Saturday effect is
    # not confounded by anything a salon cares about.
    for key in ("visits", "revenue", "customers_served"):
        if key not in usable:
            continue
        by_dow = {}
        for d, v in usable[key].items():
            by_dow.setdefault(d.weekday(), []).append(v)
        if len(by_dow) < 7:
            continue
        means = {k: sum(v) / len(v) for k, v in by_dow.items()}
        overall = sum(means.values()) / len(means)
        if overall == 0:
            continue
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        best = max(means, key=means.get)
        worst = min(means, key=means.get)
        spread = (means[best] - means[worst]) / overall
        if spread < 0.25:
            continue
        findings.append({
            "kind": "day_of_week",
            "statement": (f"{names[best]} is the strongest day for {key.replace('_', ' ')} "
                          f"and {names[worst]} the weakest - {round(means[best])} against "
                          f"{round(means[worst])} on average"),
            "strength": round(spread, 2),
            "observations": sum(len(v) for v in by_dow.values()),
            "caveat": None,
        })

    # ── Structural change ──────────────────────────────────────────
    # Compares the last 30 days against the 90 before, so a real shift
    # is distinguished from a single odd week.
    for key, vals in usable.items():
        days = sorted(vals)
        if len(days) < 120:
            continue
        recent = [vals[d] for d in days[-30:]]
        prior = [vals[d] for d in days[-120:-30]]
        if not prior or sum(prior) == 0:
            continue
        mr, mp = sum(recent) / len(recent), sum(prior) / len(prior)
        if mp == 0:
            continue
        change = (mr - mp) / mp
        if abs(change) < 0.30:
            continue
        findings.append({
            "kind": "shift",
            "statement": (f"{key.replace('_', ' ')} has {'risen' if change > 0 else 'fallen'} "
                          f"{abs(round(change * 100))}% in the last 30 days against the 90 before "
                          f"({round(mr, 1)} against {round(mp, 1)})"),
            "strength": round(abs(change), 2),
            "observations": len(recent) + len(prior),
            "caveat": "A shift, not necessarily a trend. Check it is not a sync artefact before acting.",
        })

    # ── Write ──────────────────────────────────────────────────────
    cur.execute("""
        create table if not exists mw_metric_learnings (
          id uuid primary key default gen_random_uuid(),
          tenant_id text not null,
          kind text not null,
          statement text not null,
          strength numeric,
          observations integer,
          caveat text,
          computed_at timestamptz not null default now()
        )
    """)
    cur.execute("delete from mw_metric_learnings where tenant_id = %s", (TENANT_ID,))
    for f in findings:
        cur.execute("""
            insert into mw_metric_learnings
              (tenant_id, kind, statement, strength, observations, caveat)
            values (%s, %s, %s, %s, %s, %s)
        """, (TENANT_ID, f["kind"], f["statement"], f["strength"],
              f["observations"], f["caveat"]))
    conn.commit()

    print(f"\n{len(findings)} finding(s):\n")
    for f in findings:
        print(f"  [{f['kind']}] {f['statement']}")
        print(f"      strength {f['strength']}, {f['observations']} observations")
        if f["caveat"]:
            print(f"      {f['caveat']}")
        print()

    if not findings:
        print("  Nothing survived. That is a real answer, not a failure -")
        print("  most days at this scale look like most other days.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
