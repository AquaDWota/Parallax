"""The research agent.

`ask(question)` is an async generator of UI events:
    {"type": "plan",   "todos": [{"content", "status"}]}
    {"type": "step",   "agent": "...", "tool": "...", "args": {...}}
    {"type": "result", "tool": "...", "data": {...}}       # chart-ready
    {"type": "note",   "text": "..."}                      # reasoning shown live
    {"type": "final",  "text": "markdown research note"}
    {"type": "error",  "text": "..."}

With an LLM key it runs a LangChain deepagents planner with helper sub-agents.
Without one (or with PARALLAX_AGENT=scripted) it runs a deterministic planner over the
same tools - same events, so the UI and the demo never depend on the LLM being up.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import AsyncIterator

from . import config
from .tools import (ALL_TOOLS, TOOLS_BY_NAME, build_lease_events, compare_groups, example_buildings,
                    imagery_quality, lead_time, regional_series, regression, run_sql,
                    submarket_context, usage_vs_renewal, validate)

PLANNER_PROMPT = """You are Parallax, a commercial real-estate research agent.

You study one question: does parking-lot usage (car counts from Vexcel aerial imagery, 2018-2026,
two captures a year) predict whether a tenant renews its lease (CoStar lease outcomes), and how far
ahead? Buildings with structured/underground parking can't be measured from above and are excluded.

How to work:
1. Write a short plan with write_todos.
2. For a full study, delegate: lease-event-builder (build the table, report exclusions),
   statistician (usage bins, regression, lead time, validation), imagery-analyst (regional series,
   data quality, example buildings), market-analyst (submarket context). For a quick follow-up on a
   slice ("only Class A offices in LA?") call the tools directly - it's faster.
3. Choose the next cut based on what results show (city, type, class, tenant industry, tenant size).
   Tenant size matters: a tenant leasing <10% of a building barely moves its lot.
4. Check yourself: say what was excluded and why. Never overstate: this is correlation, not cause.
5. Finish with a research note in markdown: the headline (odds ratio per 10-point drop with CI, renewal
   rate in the emptiest vs busiest bin), lead time, where it holds, validation, caveats. Under 250 words.

Tool filters: city ("Houston"/"Los Angeles"), property_type (office/retail/industrial), building_class
(A/B/C), tenant_industry, submarket, exclude_covid, min_lease_share (e.g. 0.25)."""

SUBAGENTS = [
    dict(name="lease-event-builder",
         description="Builds the lease-expiry table for a slice from CoStar lease history and reports exclusions.",
         system_prompt="Build the lease-event table for the requested slice with build_lease_events. Report n, "
                       "renewal rate, outcome mix and every exclusion with its reason. Be brief.",
         tools=[build_lease_events, run_sql]),
    dict(name="statistician",
         description="Runs the correlation study and validation: usage bins, logistic regression, lead time, robustness.",
         system_prompt="Run the requested analyses with your tools and report the numbers exactly, with CIs and n. "
                       "Flag anything that fails validation. Don't speculate beyond the numbers.",
         tools=[usage_vs_renewal, regression, lead_time, validate, compare_groups, run_sql]),
    dict(name="imagery-analyst",
         description="Parking usage from Vexcel imagery: regional time series, data-quality exclusions, example buildings.",
         system_prompt="Answer with the imagery tools. Always report what was dropped (cloud, shadow, garages) and why.",
         tools=[regional_series, imagery_quality, example_buildings]),
    dict(name="market-analyst",
         description="CoStar submarket context: vacancy proxies, rents, renewal rates by submarket.",
         system_prompt="Give submarket context with submarket_context. Keep it to the few submarkets that matter.",
         tools=[submarket_context, run_sql]),
]


def _build_deep_agent():
    from deepagents import create_deep_agent
    return create_deep_agent(model=config.MODEL, tools=ALL_TOOLS, system_prompt=PLANNER_PROMPT,
                             subagents=SUBAGENTS, name="parallax-planner")


def use_llm() -> bool:
    return os.environ.get("PARALLAX_AGENT", "auto") != "scripted" and config.llm_available()


async def ask(question: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
    gen = _ask_llm(question, history) if use_llm() else _ask_scripted(question)
    async for e in gen:
        yield e


# ------------------------------------------------------------------ LLM path
def _val(x):
    return getattr(x, "value", x)


async def _ask_llm(question: str, history: list[dict] | None) -> AsyncIterator[dict]:
    try:
        agent = _build_deep_agent()
    except Exception as e:
        yield {"type": "note", "text": f"LLM agent unavailable ({e}); using scripted planner."}
        async for ev in _ask_scripted(question):
            yield ev
        return
    msgs = list(history or []) + [{"role": "user", "content": question}]
    final_text = None
    try:
        async for ns, update in agent.astream({"messages": msgs}, stream_mode="updates", subgraphs=True):
            who = "planner" if not ns else "helper"
            for node, state in (update or {}).items():
                state = _val(state)
                if not isinstance(state, dict):
                    continue
                todos = _val(state.get("todos"))
                if todos and not ns:
                    yield {"type": "plan", "todos": [dict(content=t.get("content"), status=t.get("status")) for t in todos]}
                messages = _val(state.get("messages")) or []
                if not isinstance(messages, list):
                    messages = [messages]
                for m in messages:
                    kind = getattr(m, "type", None)
                    if kind == "ai":
                        for tc in getattr(m, "tool_calls", None) or []:
                            if tc["name"] == "task":
                                a = tc.get("args", {})
                                yield {"type": "note", "text": f"Delegating to {a.get('subagent_type')}: {a.get('description', '')[:200]}"}
                            elif tc["name"] in TOOLS_BY_NAME:
                                yield {"type": "step", "agent": who, "tool": tc["name"], "args": tc.get("args", {})}
                        text = m.content if isinstance(m.content, str) else "".join(
                            b.get("text", "") for b in m.content if isinstance(b, dict))
                        if text and not getattr(m, "tool_calls", None):
                            if ns:
                                yield {"type": "note", "text": text[:600]}
                            else:
                                final_text = text
                    elif kind == "tool" and getattr(m, "name", None) in TOOLS_BY_NAME:
                        try:
                            yield {"type": "result", "tool": m.name, "data": json.loads(m.content)}
                        except Exception:
                            pass
    except Exception as e:
        yield {"type": "error", "text": f"agent error: {e}"}
        return
    yield {"type": "final", "text": final_text or "(no answer)"}


# ------------------------------------------------------------------ scripted path
_TYPES = {"office": "office", "offices": "office", "retail": "retail", "industrial": "industrial",
          "warehouse": "industrial", "warehouses": "industrial"}
_INDUSTRIES = ["tech", "finance", "legal", "healthcare", "energy", "logistics", "government"]


def parse_filters(q: str) -> dict:
    ql = q.lower()
    f: dict = {}
    cities = [c for c, keys in [("Houston", ["houston", "hou"]), ("Los Angeles", ["los angeles", " la ", " la?", " la.", "in la"])]
              if any(k in f" {ql} " for k in keys)]
    if len(cities) == 1:
        f["city"] = cities[0]
    types = {v for k, v in _TYPES.items() if re.search(rf"\b{k}\b", ql)}
    if len(types) == 1:
        f["property_type"] = types.pop()
    m = re.search(r"class\s+([abc])\b", ql)
    if m:
        f["building_class"] = m.group(1).upper()
    inds = [i for i in _INDUSTRIES if re.search(rf"\b{i}\b", ql)]
    if inds:
        f["tenant_industry"] = inds[0]
    if re.search(r"(major|large|big|anchor) tenant|single.tenant", ql):
        f["min_lease_share"] = 0.25
    if re.search(r"(without|exclud\w*|ignore|no) (covid|2020)", ql):
        f["exclude_covid"] = True
    return f


def _intent(q: str) -> str:
    ql = q.lower()
    if re.search(r"houston (vs\.?|or|versus) (la|los angeles)|(la|los angeles) (vs\.?|or|versus) houston|stronger in", ql):
        return "compare_city"
    if re.search(r"where|which (type|class|industr|submarket)|strongest|hold", ql):
        return "where"
    if re.search(r"how far|lead time|months ahead|how early", ql):
        return "lead"
    if re.search(r"robust|valid|placebo|out.of.sample|trust", ql):
        return "validate"
    if re.search(r"trend|over time|recover|covid|time series|region", ql) and "predict" not in ql:
        return "regional"
    return "full"


async def _call(name: str, agent: str, **args) -> tuple[dict, dict]:
    clean = {k: v for k, v in args.items() if v not in (None, False, "")}
    step = {"type": "step", "agent": agent, "tool": name, "args": clean}
    data = json.loads(await asyncio.to_thread(TOOLS_BY_NAME[name], **clean))
    return step, {"type": "result", "tool": name, "data": data}


def _fmt_filters(f: dict) -> str:
    if not f:
        return "all measurable buildings in Houston and LA"
    parts = []
    if f.get("building_class"):
        parts.append(f"Class {f['building_class']}")
    if f.get("property_type"):
        parts.append(f["property_type"])
    if f.get("tenant_industry"):
        parts.append(f"{f['tenant_industry']} tenants")
    if f.get("city"):
        parts.append(f"in {f['city']}")
    if f.get("min_lease_share"):
        parts.append(f"(tenants leasing {int(f['min_lease_share'] * 100)}%+ of their building)")
    if f.get("exclude_covid"):
        parts.append("excluding 2020-21 expiries")
    return " ".join(parts)


async def _ask_scripted(question: str) -> AsyncIterator[dict]:
    f = parse_filters(question)
    intent = _intent(question)
    slice_name = _fmt_filters(f)
    plans = {
        "full": ["Build lease-event table", "Renewal rate by usage level", "Regression with controls",
                 "Lead time", "Where it holds (tenant size)", "Validation", "Example buildings", "Write note"],
        "compare_city": ["Build lease-event table", "Regression by city", "Regional time series", "Write note"],
        "where": ["Build lease-event table", "Compare by tenant size", "Compare by property type",
                  "Compare by class", "Write note"],
        "lead": ["Build lease-event table", "Lead-time sweep", "Write note"],
        "validate": ["Build lease-event table", "Validation suite", "Write note"],
        "regional": ["Regional time series", "Imagery quality", "Submarket context", "Write note"],
    }[intent]
    todos = [dict(content=p, status="pending") for p in plans]

    def plan(i):
        for j, t in enumerate(todos):
            t["status"] = "completed" if j < i else ("in_progress" if j == i else "pending")
        return {"type": "plan", "todos": [dict(t) for t in todos]}

    yield {"type": "note", "text": f"Question read as: {intent.replace('_', ' ')} for {slice_name}."}
    i = 0
    R: dict = {}

    async def run(name, agent, **a):
        s, r = await _call(name, agent, **a)
        R[name if name not in R else f"{name}:{a.get('by', len(R))}"] = r["data"]
        return s, r

    if intent != "regional":
        yield plan(i)
        s, r = await run("build_lease_events", "lease-event-builder", **f)
        yield s
        yield r
        d = r["data"]
        ex = d["exclusions_all_data"]
        yield {"type": "note", "text": f"Excluded {ex['garage_not_measurable']:,} expiries (both cities) in garage buildings: parking "
                                       f"can't be measured from above. {d['n_events']:,} usable expiries in this slice."}
        if d["n_events"] < 80:
            yield {"type": "final", "text": f"Only {d['n_events']} usable lease expiries for {slice_name} - too few for a "
                                            f"reliable answer. Try a broader slice."}
            return
        i += 1

    steps = {
        "full": [("usage_vs_renewal", "statistician", f), ("regression", "statistician", f),
                 ("lead_time", "statistician", f),
                 ("compare_groups", "statistician", {**{k: v for k, v in f.items() if k != "min_lease_share"}, "by": "tenant_size"}),
                 ("validate", "statistician", {**{k: v for k, v in f.items() if k != "exclude_covid"}, "include_noise_test": True}),
                 ("example_buildings", "imagery-analyst", {**{k: v for k, v in f.items() if k in ("city", "property_type", "building_class")}, "which": "emptiest"})],
        "compare_city": [("compare_groups", "statistician", {**f, "by": "city"}),
                         ("regional_series", "imagery-analyst", {"level": "city"})],
        "where": [("compare_groups", "statistician", {**f, "by": "tenant_size"}),
                  ("compare_groups", "statistician", {**f, "by": "property_type"}),
                  ("compare_groups", "statistician", {**f, "by": "building_class"})],
        "lead": [("lead_time", "statistician", f)],
        "validate": [("validate", "statistician", {**{k: v for k, v in f.items() if k != "exclude_covid"}})],
        "regional": [("regional_series", "imagery-analyst", {"level": "city", "city": f.get("city")}),
                     ("imagery_quality", "imagery-analyst", {"city": f.get("city")}),
                     ("submarket_context", "market-analyst", {"city": f.get("city")})],
    }[intent]
    for name, agent, a in steps:
        yield plan(i)
        s, r = await run(name, agent, **a)
        yield s
        yield r
        for n in _self_check(name, r["data"]):
            yield {"type": "note", "text": n}
        i += 1
    yield plan(i)
    yield {"type": "final", "text": _write_note(question, slice_name, intent, R)}
    yield plan(len(todos))


def _self_check(name: str, d: dict) -> list[str]:
    out = []
    if name == "usage_vs_renewal" and d.get("bins"):
        e = d["emptiest_vs_busiest"]
        out.append(f"Renewal rate: {e['emptiest']:.0%} in the emptiest usage bin vs {e['busiest']:.0%} in the busiest.")
    if name == "regression" and "odds_ratio_per_10pt_drop" in d:
        out.append(d["interpretation"])
        if d["p_value_usage"] > 0.05:
            out.append("Not significant at 5% for this slice - I'll say so rather than overclaim.")
    if name == "lead_time" and d.get("best_lead_months") is not None:
        out.append(f"Best out-of-sample window: {d['best_lead_months']}-{d['best_lead_months'] + 12} months before expiry.")
    if name == "compare_groups" and d.get("groups"):
        g = [x for x in d["groups"] if x.get("odds_ratio_per_10pt_drop")]
        if g:
            strong = min(g, key=lambda x: x["odds_ratio_per_10pt_drop"])
            out.append(f"Strongest link by {d['by']}: {strong['group']} (OR {strong['odds_ratio_per_10pt_drop']} per 10-pt drop, n={strong['n']}).")
    if name == "validate":
        p = d.get("placebo", {})
        out.append("Placebo passed: shuffling usage within submarkets kills the link." if p.get("passed")
                   else "Placebo did NOT cleanly pass - treat the result with caution.")
        o = d.get("out_of_sample", {})
        if "auc_with_usage" in o:
            out.append(f"Out of sample (2023-26): AUC {o['auc_baseline']} without usage -> {o['auc_with_usage']} with it.")
    if name == "imagery_quality":
        sc = d.get("status_counts", {})
        out.append(f"Dropped {sc.get('dropped_cloud', 0)} cloudy and {sc.get('dropped_shadow', 0)} shadowed captures; "
                   f"{d.get('buildings_not_measurable', 0)} garage buildings not measurable.")
    return out


def _write_note(q: str, slice_name: str, intent: str, R: dict) -> str:
    L = [f"### {q.strip()}", f"*Slice: {slice_name}.*", ""]
    ev = R.get("build_lease_events", {})
    if ev:
        L.append(f"**Data:** {ev['n_events']:,} lease expiries (2019-2026) with usable imagery; overall renewal rate "
                 f"{ev['renewal_rate']:.0%}. {ev['exclusions_all_data']['garage_not_measurable']:,} expiries in garage buildings excluded.")
    b = R.get("usage_vs_renewal", {})
    if b.get("bins"):
        e = b["emptiest_vs_busiest"]
        L.append(f"**Headline:** tenants in the emptiest fifth of lots renewed {e['emptiest']:.0%} of the time vs "
                 f"{e['busiest']:.0%} in the busiest fifth - {e['ratio_nonrenewal']}x the non-renewal rate.")
    r = R.get("regression", {})
    if "odds_ratio_per_10pt_drop" in r:
        L.append(f"**Regression:** {r['interpretation']} (n={r['n']:,}, p={r['p_value_usage']:.2g}).")
    lt = R.get("lead_time", {})
    if lt.get("best_lead_months") is not None:
        L.append(f"**Lead time:** the signal predicts best when usage is measured {lt['best_lead_months']}-"
                 f"{lt['best_lead_months'] + 12} months before expiry.")
    groups = [v for k, v in R.items() if k.startswith("compare_groups")]
    for g in groups:
        rows = [x for x in g.get("groups", []) if x.get("odds_ratio_per_10pt_drop")]
        if rows:
            txt = "; ".join(f"{x['group']}: OR {x['odds_ratio_per_10pt_drop']} (n={x['n']})" for x in
                            sorted(rows, key=lambda x: x["odds_ratio_per_10pt_drop"]))
            L.append(f"**By {g['by'].replace('_', ' ')}:** {txt}.")
    v = R.get("validate", {})
    if v:
        o, p = v.get("out_of_sample", {}), v.get("placebo", {})
        parts = []
        if "auc_with_usage" in o:
            parts.append(f"out-of-sample AUC {o['auc_baseline']} -> {o['auc_with_usage']}")
        if p:
            parts.append(f"placebo OR {p.get('placebo_mean_odds_ratio')} ({'passed' if p.get('passed') else 'failed'})")
        nz = v.get("detector_noise_15pct", {})
        if nz.get("odds_ratio_per_10pt_drop"):
            parts.append(f"with +/-15% car-count noise OR {nz['odds_ratio_per_10pt_drop']}")
        cv = v.get("covid", {}).get("without_2020_2021", {})
        if cv.get("odds_ratio_per_10pt_drop"):
            parts.append(f"without 2020-21 OR {cv['odds_ratio_per_10pt_drop']}")
        L.append("**Validation:** " + "; ".join(parts) + ".")
    rs = R.get("regional_series", {})
    if rs.get("series"):
        by_city: dict = {}
        for x in rs["series"]:
            by_city.setdefault(x["city"], []).append(x)
        for c, xs in by_city.items():
            low = min((x for x in xs if x["usage_index"] is not None), key=lambda x: x["usage_index"])
            last = xs[-1]
            L.append(f"**{c}:** usage bottomed at {low['usage_index']} in {low['half_year']}; latest {last['usage_index']} ({last['half_year']}).")
    L += ["", "*Correlation, not cause: remote-work policy, industry and building quality can drive both parking "
              "and renewals. Only surface-lot buildings are measurable.*"]
    return "\n\n".join(L)
