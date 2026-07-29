# Codex + Hermes/Qwen routing rules

## Delegate to the local worker first

- Batch file inspection, filename or directory classification, asset triage, string grouping.
- First-pass pseudocode summaries, candidate function names, metadata normalization.
- Repetitive evidence collection, result conversion, first-pass cross-checking, and low-value bulk summaries.

Use `hermes_health` before the first delegation. Prefer `submit_local_job` for batches and read `get_local_job_summary` before querying individual records.

## Keep with GPT-5.6

- Overall reverse-engineering strategy, unknown compression/encryption/obfuscation, parser design and debugging.
- Cross-subsystem reasoning, decompiler correction, adjudicating conflicting hypotheses, final validation and reporting.

## Escalate to GPT-5.6

Escalate when confidence is below `0.70`, workers conflict, deterministic evidence conflicts with a model conclusion, an unknown encoding or file-format core field is involved, size/integrity checks fail, step limits are hit, schema validation fails, or `needs_review=true`.

## Context control

Read aggregate summaries, conflicts, low-confidence items, and the review manifest first. Do not load an entire batch into the primary context by default.

## Safety

Use `restricted_batch` for research/game/source data and treat those inputs as read-only. Its bridge tools may write only below this project's `work` directory.

`delegate_trusted_full_task` is a separate high-risk path. Use it only when the user explicitly authorizes broad host tools for the current task, pass `authorization="explicit_user_authorized"`, and keep `allow_network=false` unless external access is also explicitly authorized. This mode can run an unsandboxed host terminal and modify files, so never select it merely because restricted execution is inconvenient.
