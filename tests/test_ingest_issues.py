"""F2: issue-form body → findings CSV row; date/source synthesised from the Issue; unselected dropdowns → ''."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from catalog import ingest_issues as II  # noqa: E402
from catalog import apply_findings as AF  # noqa: E402

BODY = """### identifier

SAMN04161034

### finding_type

value_error

### action (what should the pipeline do)

supersede_determination

### sample_key (for sample-level findings)

SAMN04161034

### field_name (for sample-level findings; leave unselected for study-level findings)

delivery_mode

### current_state

vaginal · R2 · 0.7

### proposed_change

cesarean

### new_value (normalised; ages in days, GA in weeks, controlled vocabularies; study_verdict: included|excluded|human_review)

cesarean

### reason_code (required when action = study_verdict and new_value = excluded)

_No response_

### evidence_quote (≤ 12 words, verbatim; required unless finding_type = confirmed_correct)

delivered by caesarean section

### evidence_source

paper.fulltext.methods

### confidence (required unless finding_type = confirmed_correct)

0.9

### route of the NEW evidence

R3

### release_tag / page URL

data-v1.2.1 /studies/PRJNA294605.html
"""


def test_issue_to_row_roundtrip(tmp_path):
    issue = {"number": 42, "created_at": "2026-09-27T10:11:12Z", "title": "[finding] SAMN04161034: delivery_mode", "body": BODY}
    row = II.issue_to_row(issue)
    assert row["date"] == "2026-09-27" and row["source"] == "issue#42"
    assert row["identifier"] == "SAMN04161034" and row["action"] == "supersede_determination"
    assert row["reason_code"] == "" and row["route"] == "R3" and row["confidence"] == "0.9"
    assert row["evidence_quote"] == "delivered by caesarean section"
    assert set(row) == set(AF.FINDING_COLS + AF.STRUCT_COLS)
    # offline main() writes a CSV apply_findings can read
    j = tmp_path / "issues.json"
    j.write_text(json.dumps([issue]))
    out = tmp_path / "findings"
    assert II.main(["--from-json", str(j), "--out", str(out), "--date", "2026-09-27"]) == 0
    df = AF.read_findings(str(out))
    assert len(df) == 1 and df.iloc[0]["source"] == "issue#42"
    # a second run skips the already-ingested issue
    assert II.main(["--from-json", str(j), "--out", str(out), "--date", "2026-09-28"]) == 0
    import pandas as pd
    assert len(pd.read_csv(out / "2026-09-28_issues.csv")) == 0
