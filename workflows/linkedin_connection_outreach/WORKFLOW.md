---
name: LinkedIn connection outreach
category: outreach
status: scaffold
profile_status: fixture_ready
platforms: [linux, macos, windows]
skills: [linkedin-decision-maker-outreach]
runtime_capabilities: [web_research, csv, authorized_messaging_connector_optional]
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

Create relevant, researched LinkedIn messages for decision makers already connected to the user. Put every draft into a local CSV for human approval. Dispatch only sealed, approved text in a separate run through an authorized connector or manual handoff.

## Existing patterns reused

- `offer_intake`: treat the offer Markdown file as the primary source and do not invent proof.
- `linkedin_profile`: use only user-visible, user-owned LinkedIn data and never handle credentials.
- `lead_research`: research companies off LinkedIn, keep source URLs, and separate facts from inferences.
- `personalized_outreach`: write one short, specific, proof-bound draft per person for human review.
- `linkedin_connect`: use a local tracker, explicit approval state, serial execution, caps, and hard stops. Its campaign-specific browser-send exception is not inherited.

## Sequence

1. Read the offer and the user's decision-maker roles.
2. Import the user's LinkedIn `Connections.csv` export. Do not scrape the Connections page.
3. Match titles, then let the user resolve ambiguous candidates.
4. Research selected companies from public sources outside LinkedIn, in resumable batches of at most 20.
5. Draft a message of 80 words or fewer and save it with research sources.
6. Let the user edit `approval_status` in the CSV, then seal the approved message hashes.
7. On a separate explicit request, dispatch no more than five ready messages, one at a time. Use an authorized messaging connector or give the user a manual handoff. Do not automate LinkedIn's website.
8. Update the CSV from connector proof or the user's confirmation after each attempt. Stop on uncertainty.

## Boundaries

- No unapproved or bulk messaging.
- No credential handling, connection scraping, LinkedIn browser automation, CAPTCHA solving, or rate-limit bypass.
- No sensitive-trait profiling or unsupported personalization.
- No automatic retry after a possibly successful send.

The portable implementation lives in `skills/linkedin-decision-maker-outreach/`. Keep `profile_status` at `fixture_ready` until one controlled manual handoff or approved connector dispatch has been tested on the publisher's own account.
