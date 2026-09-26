#!/usr/bin/env python
"""check_reports.py REPORTS_DIR — fail when a report the site links to is missing (R1-08).
The required list is config/inputs.json group `reports` (entries with required != false)."""
import json, os, sys

def main(argv):
    reports = argv[0] if argv else "data/inputs/reports"
    cfg = os.path.join(os.environ.get("CATALOG_CONFIG_DIR", "config"), "inputs.json")
    req = [e["filename"] for e in json.load(open(cfg))["inputs"]["reports"] if e.get("required", True)]
    missing = [f for f in req if not os.path.exists(os.path.join(reports, f))]
    if missing:
        print(f"missing report inputs in {reports}: {missing} — run bootstrap (group reports) or place them there", file=sys.stderr)
        return 1
    print("reports present:", req)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
