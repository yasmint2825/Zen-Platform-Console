New backend actions for Operations: Demographics / Acquisition / Locations / Daily ops
========================================================================================

The Zen prototype's Operations insights page now has six tabs, matching
the request. Two are fully real today (Overview, Revenue) - no
deploy needed. The other four call action names that don't exist on
mw-admin yet; each tab already shows an honest "needs this action"
note and will start working the moment the matching action below is
added and deployed, with no further frontend changes.

------------------------------------------------------------------------
1. get_customer_demographics  -  READY TO DEPLOY AS-IS
------------------------------------------------------------------------
This one is fully real right now - segment and dob are confirmed,
existing columns on mw_customer_profile. Nothing to sync first.

  case "get_customer_demographics": {
    if (!requireOwner()) return json({ ok: false, error: "Only an owner can view this" }, 403);
    const { data, error } = await supabase.from("mw_customer_profile")
      .select("segment, dob").eq("tenant_id", tenant_id);
    if (error) return json({ ok: false, error: error.message }, 500);

    const rows = data || [];
    const gender = { boys: 0, girls: 0, unknown: 0 };
    rows.forEach((r) => {
      const s = String(r.segment || "").toLowerCase();
      if (s === "boy") gender.boys++;
      else if (s === "girl") gender.girls++;
      else gender.unknown++;
    });

    const BUCKETS: [string, number, number][] = [
      ["0-2 yrs", 0, 2], ["3-5 yrs", 3, 5], ["6-8 yrs", 6, 8],
      ["9-11 yrs", 9, 11], ["12-15 yrs", 12, 15], ["16+ yrs", 16, 200],
    ];
    const counts = new Array(BUCKETS.length).fill(0);
    let unknownAge = 0;
    const today = new Date();
    rows.forEach((r) => {
      if (!r.dob) { unknownAge++; return; }
      const age = Math.floor((today.getTime() - new Date(r.dob).getTime()) / (365.25 * 86400000));
      const i = BUCKETS.findIndex(([, lo, hi]) => age >= lo && age <= hi);
      if (i >= 0) counts[i]++; else unknownAge++;
    });
    const age_buckets = BUCKETS.map(([label], i) => ({ label, count: counts[i] }));
    if (unknownAge) age_buckets.push({ label: "Unknown", count: unknownAge });

    return json({
      ok: true,
      gender,
      age_buckets,
      age_total: rows.length,
    });
  }

The frontend expects: { ok, gender:{boys,girls}, age_buckets:[{label,count}], age_total }
- exactly what's already wired up in opsDemographicsTab().

------------------------------------------------------------------------
2. get_acquisition_sources  -  NEEDS A SYNC FIRST
------------------------------------------------------------------------
heard_via does not exist anywhere in this backend's real schema. It
lives in a different app's customers table (confirmed from the
uploaded index.html). Before this action can be written for real,
that field needs to land in mw_customer_profile (or wherever this
backend's real sync writes to) - most simply, as a new
"heard_via text" column, populated the same way dob/segment already
are.

Once that sync exists, the action itself is simple:

  case "get_acquisition_sources": {
    if (!requireOwner()) return json({ ok: false, error: "Only an owner can view this" }, 403);
    const { data, error } = await supabase.from("mw_customer_profile")
      .select("heard_via").eq("tenant_id", tenant_id);
    if (error) return json({ ok: false, error: error.message }, 500);
    const sources: Record<string, number> = {};
    (data || []).forEach((r) => {
      const v = String(r.heard_via || "").trim();
      if (v) sources[v] = (sources[v] || 0) + 1;
    });
    return json({ ok: true, sources });
  }

Frontend expects: { ok, sources: { "Google": 467, "Friends / Family": 317, ... } }

The richer version in the uploaded screenshots (New Customers by
Source, split new vs. returning, this month only) is a real second
step past this - it additionally needs each source cross-referenced
against mw_transactions to classify each customer as new or
returning for the period. Worth building once the base column exists
and this simpler version is confirmed working.

------------------------------------------------------------------------
3. get_customers_by_location  -  NEEDS THE SAME SYNC AS #2
------------------------------------------------------------------------
Same situation as Acquisition. location doesn't exist on
mw_customer_profile or anywhere else in this backend.

  case "get_customers_by_location": {
    if (!requireOwner()) return json({ ok: false, error: "Only an owner can view this" }, 403);
    const { data, error } = await supabase.from("mw_customer_profile")
      .select("location").eq("tenant_id", tenant_id);
    if (error) return json({ ok: false, error: error.message }, 500);
    const locations: Record<string, number> = {};
    (data || []).forEach((r) => {
      const v = String(r.location || "").trim();
      if (v) locations[v] = (locations[v] || 0) + 1;
    });
    return json({ ok: true, locations });
  }

Frontend expects: { ok, locations: { "Dubai Silicon Oasis (DSO)": 1007, "Liwan": 38, ... } }

------------------------------------------------------------------------
4. get_daily_operations  -  NEEDS THE queue TABLE EXPOSED
------------------------------------------------------------------------
This is the one backed by the strongest independent evidence: two
separate reference files (this project's own earlier console.html
migration source, and the file this request pointed at) both
independently rely on a real queue table with checkin_time,
called_at, done_at, service_value, and stylist. Neither reference is
part of this backend's own verified schema, so it's treated as a real
gap, not assumed.

  case "get_daily_operations": {
    if (!requireOwner()) return json({ ok: false, error: "Only an owner can view this" }, 403);
    const days = Math.min(Number(body.days) || 7, 90);
    const since = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
    const { data, error } = await supabase.from("queue")
      .select("checkin_date, checkin_time, called_at, done_at, service_value, stylist, status")
      .eq("tenant_id", tenant_id).gte("checkin_date", since).eq("status", "done");
    if (error) return json({ ok: false, error: error.message }, 500);

    const byDay: Record<string, { served: number; wait: number[]; serve: number[]; revenue: number }> = {};
    (data || []).forEach((q) => {
      const d = byDay[q.checkin_date] ||= { served: 0, wait: [], serve: [], revenue: 0 };
      d.served++;
      d.revenue += Number(q.service_value) || 0;
      if (q.checkin_time && q.called_at) {
        const w = (new Date(q.called_at).getTime() - new Date(q.checkin_time).getTime()) / 60000;
        if (w >= 0 && w < 300) d.wait.push(w);
      }
      if (q.called_at && q.done_at) {
        const s = (new Date(q.done_at).getTime() - new Date(q.called_at).getTime()) / 60000;
        if (s > 0 && s < 300) d.serve.push(s);
      }
    });
    const avg = (arr: number[]) => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;
    const days_out = Object.entries(byDay).sort((a, b) => b[0].localeCompare(a[0])).map(([date, d]) => ({
      date, served: d.served, avg_wait_mins: avg(d.wait), avg_service_mins: avg(d.serve),
      revenue: Math.round(d.revenue),
    }));
    return json({ ok: true, days: days_out });
  }

Frontend expects: { ok, days: [{date, served, avg_wait_mins, avg_service_mins, revenue}, ...] }
- exactly what opsDailyTab() already renders.

------------------------------------------------------------------------
NOTE ON TENANT SCOPING
------------------------------------------------------------------------
Every query above assumes queue and mw_customer_profile both have a
tenant_id column matching this project's existing convention. If the
real queue table (wherever it lives) doesn't have tenant_id yet -
plausible, if it was built for a single-tenant app originally - that
would need adding before this can be scoped safely per tenant.
