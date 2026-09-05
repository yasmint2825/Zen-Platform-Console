CORRECTED: get_daily_operations - built against mw_transactions, not a separate queue table
================================================================================================

My earlier spec assumed a separate "queue" table. That assumption
was wrong to rely on without checking first, and the check just
proved it - checkin_at, called_at, done_at, stylist_name, and amount
all sit directly on mw_transactions, the exact table already
confirmed and used throughout this entire build (get_daily_metric,
the daily-metrics refresh job, the MTD revenue fix, everything).

This means Daily ops needs no new table, no sync, nothing uncertain -
just one new action reading columns that already exist, on a table
already proven reliable.

  case "get_daily_operations": {
    if (!requireOwner()) return json({ ok: false, error: "Only an owner can view this" }, 403);
    const days = Math.min(Number(body.days) || 7, 90);
    const since = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);

    const { data, error } = await supabase.from("mw_transactions")
      .select("transaction_date, checkin_at, called_at, done_at, stylist_name, amount")
      .eq("tenant_id", tenant_id)
      .gte("transaction_date", since)
      .not("checkin_at", "is", null);
    if (error) return json({ ok: false, error: error.message }, 500);

    const byDay: Record<string, { served: number; wait: number[]; serve: number[]; revenue: number }> = {};
    const byStylist: Record<string, { customers: number; wait: number[]; serve: number[]; revenue: number }> = {};

    (data || []).forEach((r) => {
      const day = byDay[r.transaction_date] ||= { served: 0, wait: [], serve: [], revenue: 0 };
      day.served++;
      day.revenue += Number(r.amount) || 0;

      const stylist = r.stylist_name || "Unknown";
      const st = byStylist[stylist] ||= { customers: 0, wait: [], serve: [], revenue: 0 };
      st.customers++;
      st.revenue += Number(r.amount) || 0;

      if (r.checkin_at && r.called_at) {
        const w = (new Date(r.called_at).getTime() - new Date(r.checkin_at).getTime()) / 60000;
        if (w >= 0 && w < 300) { day.wait.push(w); st.wait.push(w); }
      }
      if (r.called_at && r.done_at) {
        const s = (new Date(r.done_at).getTime() - new Date(r.called_at).getTime()) / 60000;
        if (s > 0 && s < 300) { day.serve.push(s); st.serve.push(s); }
      }
    });

    const avg = (arr: number[]) => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;

    const days_out = Object.entries(byDay).sort((a, b) => b[0].localeCompare(a[0])).map(([date, d]) => ({
      date, served: d.served, avg_wait_mins: avg(d.wait), avg_service_mins: avg(d.serve),
      revenue: Math.round(d.revenue),
    }));

    const stylists_out = Object.entries(byStylist).sort((a, b) => b[1].customers - a[1].customers).map(([name, s]) => ({
      stylist: name, customers: s.customers, avg_wait_mins: avg(s.wait), avg_service_mins: avg(s.serve),
      revenue: Math.round(s.revenue), avg_per_visit: s.customers ? Math.round(s.revenue / s.customers) : 0,
    }));

    return json({ ok: true, days: days_out, stylists: stylists_out });
  }

Frontend expects: { ok, days: [{date, served, avg_wait_mins, avg_service_mins, revenue}], stylists: [{stylist, customers, avg_wait_mins, avg_service_mins, revenue, avg_per_visit}] }

The "not checkin_at is null" filter matters: plenty of historical
rows almost certainly predate whenever checkin/called/done tracking
was switched on, and counting those as "0 wait time" would be wrong -
they're excluded from the average entirely rather than dragging it
toward zero, the same principle already used elsewhere in this
backend for receipts_available-style gaps.

This replaces the queue-based version in new_operations_actions.md
entirely - that one should be discarded in favour of this.

STILL OPEN (unaffected by this correction)
--------------------------------------------
- Acquisition (get_acquisition_sources) - still waiting on the
  source_type distinct-values check to see whether it's actually
  acquisition data or something else (import source, booking channel,
  etc.)
- Locations (get_customers_by_location) - still no column found
  anywhere confirmed so far; the `visits` table check from earlier is
  still the open lead worth running if you want to settle this one
  too.
