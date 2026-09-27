"""catalog.registry — registry tier of the human shotgun-metagenome catalog (SCALE_UP_PLAN §2; docs/EXPANSION.md).

vocab.py                 controlled vocabularies (config/scope.yaml + config/vocab/*.yaml), term matchers, UBERON lookup
classify_deterministic   host / assay / body site / life stage / population flags with evidence rows, needs_llm flag
classify_llm             Sonnet ×2 + Opus adjudication stage (batch builder, parser, validator, agreement, cost log)
build_registry           registry_studies.parquet + REGISTRY_REPORT.md from universe + classifications + infant verdicts
"""
