#!/usr/bin/env python
"""findings_schema.py — load audit/schema.json (the single source of the findings loop, R1-09/F2) and generate the
GitHub issue form from it.

    python -m catalog.findings_schema --write-template      # rewrite .github/ISSUE_TEMPLATE/catalog-finding.yml
    python -m catalog.findings_schema --check               # exit 1 when the template differs from the generated one
    python -m catalog.findings_schema --auditor-vocab       # print the finding_type list for the CATALOG_AUDITOR prompt
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCHEMA_PATH = os.environ.get("CATALOG_FINDINGS_SCHEMA", os.path.join(REPO, "audit", "schema.json"))
TEMPLATE_PATH = os.path.join(REPO, ".github", "ISSUE_TEMPLATE", "catalog-finding.yml")


def load(path: str | None = None) -> dict:
    return json.load(open(path or SCHEMA_PATH, encoding="utf-8"))


def finding_cols(s: dict | None = None) -> list[str]:
    return list((s or load())["csv_columns"]["required"])


def struct_cols(s: dict | None = None) -> list[str]:
    return list((s or load())["csv_columns"]["structured"])


def actions(s: dict | None = None) -> set[str]:
    return set((s or load())["actions"])


def finding_types(s: dict | None = None) -> list[str]:
    return list((s or load())["finding_types"])


def _yaml_list(xs) -> str:
    return "[" + ", ".join(json.dumps(x) for x in xs) + "]"


def render_template(s: dict | None = None) -> str:
    """Deterministic GitHub issue-form YAML. Dropdowns have NO empty option (GitHub rejects it): optional dropdowns
    are simply not `required`. Evidence fields are optional in the form; apply_findings enforces them per action
    (confirm needs none — issue_form.evidence_optional_for)."""
    s = s or load()
    f = s["issue_form"]
    ft = s["finding_types"]
    ft_desc = "; ".join(f"{k} = {v['description']}" for k, v in ft.items())
    lines = [
        "# GENERATED from audit/schema.json by `python -m catalog.findings_schema --write-template` — do not edit by hand (R1-09/F2).",
        "# Site buttons open this form prefilled (…/issues/new?template=catalog-finding.yml&labels=finding&title=…&identifier=…&",
        "# current_state=…&release_tag=…). `date` and `source` are NOT asked: ingest_issues.py fills them from the Issue's",
        "# created_at and number. The form must be INSTALLED in the Issues repo (config/site.yaml github.issues.repo) — make install-workflows.",
        f"name: {f['name']}",
        "description: " + json.dumps(f["description"]),
        f"title: {json.dumps(f['title'])}",
        f"labels: {_yaml_list(f['labels'])}",
        "body:",
        "  - type: markdown",
        "    attributes:",
        "      value: |",
        "        Every row of the catalog carries evidence; a finding needs evidence too (Rule 1 of the curation rules): a",
        "        source label and a verbatim quote of **at most 12 words**. Values without evidence are recorded but not applied.",
        "        For `confirmed_correct` (the \"Confirm correct\" button) no quote is needed — the confirmation becomes a truth-set row.",
        "  - type: input",
        "    id: identifier",
        "    attributes:",
        "      label: identifier",
        "      description: " + json.dumps("Study accession (PRJ…), sample key (SAMN…/SAMEA…/SAMD…/run accession) or cohort id (COH…)"),
        "      placeholder: PRJNA294605",
        "    validations: { required: true }",
        "  - type: dropdown",
        "    id: finding_type",
        "    attributes:",
        "      label: finding_type",
        f"      description: {json.dumps(ft_desc)}",
        f"      options: {_yaml_list(ft)}",
        "    validations: { required: true }",
        "  - type: dropdown",
        "    id: action",
        "    attributes:",
        "      label: " + json.dumps("action (what should the pipeline do)"),
        "      description: " + json.dumps("; ".join(f"{k}: {v['writes']}" for k, v in s["actions"].items())),
        f"      options: {_yaml_list(s['actions'])}",
        "    validations: { required: true }",
        "  - type: input",
        "    id: sample_key",
        "    attributes:",
        "      label: " + json.dumps("sample_key (for sample-level findings)"),
        "      placeholder: SAMN04161034",
        "  - type: dropdown",
        "    id: field_name",
        "    attributes:",
        "      label: " + json.dumps("field_name (for sample-level findings; leave unselected for study-level findings)"),
        f"      options: {_yaml_list(s['field_names'])}",
        "  - type: textarea",
        "    id: current_state",
        "    attributes:",
        "      label: current_state",
        "      description: " + json.dumps("What the site shows now (value · route · confidence · quote) — copied by the link when prefilled"),
        "    validations: { required: true }",
        "  - type: textarea",
        "    id: proposed_change",
        "    attributes:",
        "      label: proposed_change",
        "      description: For confirmed_correct write \"confirmed\".",
        "    validations: { required: true }",
        "  - type: input",
        "    id: new_value",
        "    attributes:",
        "      label: " + json.dumps("new_value (normalised; ages in days, GA in weeks, controlled vocabularies; study_verdict: " + "|".join(s["study_verdict_values"]) + ")"),
        "  - type: dropdown",
        "    id: reason_code",
        "    attributes:",
        "      label: " + json.dumps("reason_code (required when action = study_verdict and new_value = excluded)"),
        f"      options: {_yaml_list(s['reason_codes'])}",
        "  - type: input",
        "    id: evidence_quote",
        "    attributes:",
        "      label: " + json.dumps("evidence_quote (≤ 12 words, verbatim; required unless finding_type = confirmed_correct)"),
        "  - type: input",
        "    id: evidence_source",
        "    attributes:",
        "      label: evidence_source",
        "      description: \"Labelled source: paper.supp.<file>[sheet!column], paper.fulltext.methods, sample.attr.<key>, external_curation.human\"",
        "      placeholder: external_curation.human",
        "  - type: dropdown",
        "    id: confidence",
        "    attributes:",
        "      label: " + json.dumps("confidence (required unless finding_type = confirmed_correct)"),
        f"      options: {_yaml_list(s['confidence_options'])}",
        "  - type: dropdown",
        "    id: route",
        "    attributes:",
        "      label: route of the NEW evidence",
        "      description: " + json.dumps("; ".join(f"{k} = {v}" for k, v in s["routes"].items())),
        f"      options: {_yaml_list(s['routes'])}",
        "  - type: input",
        "    id: release_tag",
        "    attributes:",
        "      label: " + json.dumps("release_tag / page URL"),
        "      description: " + json.dumps("Filled automatically by the site link (VERSION.json release_tag + page path)"),
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-template", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--auditor-vocab", action="store_true")
    a = ap.parse_args(argv)
    s = load()
    if a.auditor_vocab:
        for k, v in s["finding_types"].items():
            print(f"{k}: {v['description']} → actions {', '.join(v['actions'])}")
        return 0
    text = render_template(s)
    if a.write_template:
        open(TEMPLATE_PATH, "w", encoding="utf-8").write(text)
        print("wrote", TEMPLATE_PATH)
        return 0
    if a.check:
        cur = open(TEMPLATE_PATH, encoding="utf-8").read() if os.path.exists(TEMPLATE_PATH) else ""
        if cur != text:
            print("catalog-finding.yml differs from audit/schema.json — run: python -m catalog.findings_schema --write-template", file=sys.stderr)
            return 1
        print("template up to date")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
