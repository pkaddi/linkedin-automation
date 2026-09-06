# Tracker schema

The tracker is UTF-8 CSV with one connection per row. It is both the review surface and the state machine.

## Identity and source

- `schema_version`: current schema, `2`. The tracker loads and upgrades version 1 rows.
- `record_id`: stable short hash used by commands.
- `first_name`, `last_name`, `full_name`: imported connection name.
- `title`, `company`, `profile_url`, `connected_on`: imported LinkedIn fields.
- `offer_sha256`: hash of the offer used for this row.

## Qualification

- `role_match`: `yes`, `no`, or `review`.
- `matched_role`: supplied title that matched.
- `role_reason`: automatic or human reason for the decision.

Only `yes` rows can become send-ready.

## Research and draft

- `company_website`: official company URL.
- `research_status`: `pending`, `complete`, or `skipped`.
- `research_summary`: short factual summary.
- `research_sources`: one or more HTTP URLs separated by ` | `.
- `personalization_hook`: the sourced angle used in the draft.
- `draft_message`: exact message to review and send.
- `draft_message_sha256`: current draft hash.

## Approval

- `approval_status`: `pending`, `approved`, or `rejected`. This is the main field a reviewer edits.
- `approved_at`: time the approved text was sealed.
- `approved_message_sha256`: sealed hash of the exact approved text.
- `approved_payload_sha256`: sealed hash binding record ID, recipient name, profile URL, and message.

Approval is valid only when the message hash and full payload hash match the current row.

## Delivery

- `send_status`: `not_ready`, `ready`, `sending`, `sent`, or `manual_review`.
- `send_started_at`: time a locked send attempt began.
- `sent_at`: time visible delivery was verified.
- `conversation_url`: LinkedIn conversation URL captured after verification.
- `send_attempt_id`: unique ID for the current delivery attempt.
- `delivery_verified_at`: time the exact outgoing message was verified.
- `delivery_proof`: a short record of the visible proof, including the message hash.
- `last_error`: last delivery problem.
- `updated_at`: last tracker update.

`manual_review` means delivery may have occurred or the state is otherwise unclear. It must not be retried automatically.

## CSV safety

Imported values that begin with spreadsheet formula characters are prefixed with an apostrophe. Email fields from the LinkedIn export are never copied into the tracker. Writes are atomic so an interruption cannot leave a half-written file.
