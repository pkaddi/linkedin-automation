# Workflow

## 1. Intake

Read the full offer before touching contact data. Extract the buyer, problem, promised result, proof, constraints, call to action, and any language the user does not want used. Ask for the decision-maker titles as a plain text list.

Use LinkedIn's `Connections.csv` export from the user's own account. The tracker imports names, titles, companies, profile URLs, and connection dates. It intentionally ignores email addresses.

## 2. Candidate review

Initialize the tracker, then review automatic title matches. Mark `yes` only when the role could plausibly approve, own, or directly sponsor the offer. Mark adjacent influencers as `review`, not `yes`, unless the user includes them.

Do not use sensitive traits, private-life details, or unsupported assumptions to prioritize people.

## 3. Company research

Run `research-queue --tracker outreach.csv --limit 20` at the start of a daily preparation run. The command returns only confirmed decision makers who still need research.

For each confirmed candidate:

- identify the official company site;
- find one recent, offer-relevant fact;
- save the direct URL, not a search-results URL;
- summarize only what the source supports;
- record whether a statement is an inference.

Useful signals include a product launch, stated strategic priority, relevant hiring, a new market, or a documented operational change. Personal trivia is not a useful signal.

## 4. Draft

Create a message of 80 words or fewer. Tie the sourced signal to one outcome from the offer. Keep the ask easy to decline. A message should still make sense if the recipient reads it a week later.

Write the research and draft into the tracker with `set-draft`. That command resets any earlier approval because the content has changed.

## 5. Human review

The user opens the CSV and marks each draft `approved` or `rejected`. Run `seal`, which records a hash of every approved message. Run `validate` before presenting the ready queue.

If the user edits an approved message later, the hash no longer matches. The workflow must not send it until the user approves and seals the new text.

## 6. Separate dispatch run

Sending requires an explicit request in the current conversation. First run the read-only CDP preflight. Then show no more than five ready rows and ask the user to approve the displayed batch.

After confirmation, run `linkedin_cdp.py dispatch` with `--confirm-send`. The sender attaches to the user's visible Chrome session, processes rows one at a time, and checks the recipient and exact text before every click.

The sender checks for a new outgoing message with the exact sealed text before it records `sent`. Delivery uncertainty is a hard stop. Mark the row `manual_review` without retrying so the user can inspect the conversation.

## 7. Handoff

At the end, report counts for pending research, pending approval, ready, sent, rejected, and manual review. Keep the CSV local unless the user explicitly chooses to share it.
