---
name: LinkedIn connection outreach
category: outreach
status: implemented
profile_status: cdp_candidate
platforms: [linux, macos, windows]
skills: [linkedin-decision-maker-outreach]
runtime_capabilities: [web_research, csv, chrome_cdp, manual_send_handoff]
runner_support: [hermes, claude, chatgpt]
inputs:
  offer_md: required
  connections_csv: required
  decision_maker_roles: required
  tracker_csv: outreach.csv
  research_batch: 20
  send_limit: 5
output: outreach.csv
---

# LinkedIn Connection Outreach

## Goal

Create relevant, researched LinkedIn messages for decision makers already connected to the user. Put every draft into a local CSV for human approval. Send approved messages through the user's local Chrome CDP session.

## Existing patterns reused

- `offer_intake`: treat the offer Markdown file as the primary source and do not invent proof.
- `linkedin_profile`: use only user-visible, user-owned LinkedIn data and never handle credentials.
- `lead_research`: research companies off LinkedIn, keep source URLs, and separate facts from inferences.
- `personalized_outreach`: write one short, specific, proof-bound draft per person for human review.
- `linkedin_connect`: use a local tracker, explicit approval state, serial execution, caps, and hard stops.

## Sequence

1. Read the offer and the user's decision-maker roles.
2. Import the user's LinkedIn `Connections.csv` export. Do not scrape the Connections page.
3. Match titles, then let the user resolve ambiguous candidates.
4. Research selected companies from public sources outside LinkedIn, in resumable batches of at most 20.
5. Draft a message of 80 words or fewer and save it with research sources.
6. Let the user edit `approval_status` in the CSV, then seal the approved message hashes.
7. On a separate explicit request, show no more than five ready messages and ask the user to approve that batch.
8. Dispatch one message at a time through local Chrome CDP. Update the CSV only after visible delivery verification and stop on uncertainty.

## Boundaries

- No unapproved or bulk messaging.
- No credential handling, connection scraping, CAPTCHA solving, restriction bypass, or browser automation outside the CDP sender.
- No sensitive-trait profiling or unsupported personalization.
- No automatic retry after a possibly successful send.

The portable implementation lives in `skills/linkedin-decision-maker-outreach/`. Keep `profile_status` at `cdp_candidate` until the publisher completes one controlled live send between accounts they own.
