#!/usr/bin/env python
"""budget_calc.py — derive every token/leaf-frame figure quoted in docs/SCALE_UP_PLAN.md §4 and docs/NEXT_STAGE.md §7
from config/budgets.yaml (R1-12). Prints a markdown table; the docs paste its output and cite this script.

    python scripts/budget_calc.py [--studies 6000 8000]
"""
import argparse
import math
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", nargs=2, type=int, default=[6000, 8000], help="S1 candidate-study range")
    a = ap.parse_args(argv)
    B = yaml.safe_load(open(os.path.join(ROOT, "config", "budgets.yaml")))
    P, R, C = B["platform"], B["per_request"], B["per_cycle_expected"]
    ovh = R["fixed_overhead_tokens"]
    rub = R["sonnet_rubric"]
    # per judged study: Sonnet x2 replicates (items per request amortise the overhead) + Opus adjudication on ~20 % + Haiku screen share
    sonnet = 2 * (rub["tokens_per_item"] + ovh / rub["items"])
    opus = 0.20 * (R["adjudication"]["tokens_per_item"] + ovh / R["adjudication"]["items"])
    haiku_share = ovh / R["study_screen_haiku"]["items"] + (R["paper_screen"]["tokens_per_item"])  # per-item screen cost not measured; paper-screen 775 used as proxy
    per_study_lo = C["triage_tokens_per_judged_study"]            # measured aggregate (4,000)
    per_study_hi = sonnet + opus + haiku_share                       # component build-up
    rows = ["| quantity | value | derivation (config/budgets.yaml) |", "|---|---:|---|"]
    rows.append(f"| Sonnet x2 per study | {sonnet:,.0f} | 2 x ({rub['tokens_per_item']} + {ovh}/{rub['items']}) |")
    rows.append(f"| Opus share per study | {opus:,.0f} | 0.20 x ({R['adjudication']['tokens_per_item']} + {ovh}/1) |")
    rows.append(f"| Haiku screen share per study | {haiku_share:,.0f} | {ovh}/{R['study_screen_haiku']['items']} + 775 proxy (per-item screen cost unmeasured) |")
    rows.append(f"| **triage tokens per judged study** | **{per_study_lo:,.0f}–{per_study_hi:,.0f}** | measured aggregate vs component build-up |")
    lo, hi = a.studies
    s1_lo, s1_hi = lo * per_study_lo, hi * per_study_hi
    rows.append(f"| S1 classification of {lo:,}–{hi:,} studies | {s1_lo/1e6:.0f}–{s1_hi/1e6:.0f} M | studies x per-study |")
    cap, soft = P["host_llm_cap_per_frame_tokens"], P["leaf_worker_soft_cap_tokens"]
    rows.append(f"| S1 leaf frames at the {cap/1e6:.1f} M hard cap | {math.ceil(s1_lo/cap)}–{math.ceil(s1_hi/cap)} | ceil(tokens / cap) |")
    rows.append(f"| S1 leaf frames at the {soft/1e3:.0f} k soft cap | {math.ceil(s1_lo/soft)}–{math.ceil(s1_hi/soft)} | ceil(tokens / soft cap) — the dispatch plan |")
    m = C["llm_judged_per_month"]
    cyc_tri_lo, cyc_tri_hi = m["mean"] * per_study_lo, m["max"] * per_study_hi
    rows.append(f"| monthly triage ({m['mean']} judged, max {m['max']}) | {cyc_tri_lo/1e6:.2f}–{cyc_tri_hi/1e6:.2f} M | judged x per-study |")
    inc = C["new_included_per_month"]
    ext = C["extraction_tokens_per_new_included_study"]
    rows.append(f"| monthly extraction ({inc['mean']} includes, max {inc['max']}) | {inc['mean']*ext/1e6:.2f}–{inc['max']*ext/1e6:.2f} M | includes x {ext:,} |")
    ct = C["cycle_tokens_expected"]
    rows.append(f"| **monthly cycle total** | **{ct['typical']/1e6:.1f} M typical, ≤ {ct['high']/1e6:.1f} M high** | cycle_tokens_expected |")
    rows.append(f"| monthly leaf frames at the soft cap | {math.ceil(ct['typical']/soft)}–{math.ceil(ct['high']/soft)} | ceil(cycle / {soft/1e3:.0f} k) |")
    rows.append(f"| new human-signal studies / month | {C['new_human_signal_studies_per_month']['mean']} ({C['new_human_signal_studies_per_month']['min']}–{C['new_human_signal_studies_per_month']['max']}) | per_cycle_expected |")
    rows.append(f"| deterministic auto-excluded / month | {C['deterministic_excluded_per_month']} | per_cycle_expected |")
    rows.append(f"| new included / month | {inc['mean']} ({inc['min']}–{inc['max']}) | per_cycle_expected |")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
