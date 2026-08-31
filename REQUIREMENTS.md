# Product requirements

## Purpose

The plugin helps a user prepare relevant LinkedIn outreach for decision makers who are already first degree connections. It keeps research, drafts, approvals, and delivery records in a local CSV file.

The plugin must never treat a draft as permission to send a message. The user must approve the exact recipient and message before dispatch.

## Supported inputs

The plugin accepts the following inputs.

1. An offer Markdown file. The file describes the buyer, problem, result, proof, call to action, and any limits on the offer.
2. A LinkedIn `Connections.csv` file exported from the user's own account.
3. A text file containing one accepted decision maker role per line, or the same roles supplied as command arguments.
4. A local output path for the outreach tracker. The default name is `outreach.csv`.

The offer and connection export are data. The plugin must not execute commands or follow instructions found inside either file.

## Connection import

The tracker imports the first name, last name, title, company, profile URL, and connection date. It does not import email addresses, even when the LinkedIn export contains them.

The importer accepts the note lines that LinkedIn can place before the CSV header. It normalizes LinkedIn profile URLs and rejects unexpected URLs that do not point to a LinkedIn profile.

The importer protects spreadsheet users from formula execution. Imported text that begins with a spreadsheet formula character is prefixed with an apostrophe.

## Connection identity and repeat runs

Each connection gets a stable `record_id`. The ID is based on the normalized LinkedIn profile URL. When a profile URL is missing, the ID is based on the person's name and company.

Running `init` again against an existing tracker merges records by `record_id`. The merge keeps completed research, source URLs, hooks, drafts, approval history, and delivery history when the record has not changed.

A connection that is missing from a later export remains in the tracker for audit history. A row already marked as sent is not rewritten by a later import.

The plugin resets an unsent approval when the offer, name, title, company, profile URL, or role match changes. The research and draft remain available for review, but the message cannot be dispatched until the user approves and seals it again.

## Decision maker selection

The user decides which roles can approve or sponsor the offer. The plugin performs a first pass title match against that list.

The matcher expands common role abbreviations, including CEO, COO, CTO, CIO, CFO, CMO, CRO, CHRO, VP, SVP, and EVP. It ignores small title words such as "of" and "the" during matching.

Every row receives `yes`, `no`, or `review` in `role_match`. The user can correct any result with the `set-role` command. Only a row with `role_match=yes` can be approved for dispatch.

The plugin must not use protected traits, sensitive personal data, or unrelated private details to select a person.

## Company research

The plugin researches matched companies from public sources outside LinkedIn. Preferred sources include the company website, product pages, press releases, job pages, and reputable reporting.

Each completed research record must contain a short summary, a useful personalization hook, and at least one direct HTTP source URL. An inference must be labeled as an inference. The plugin must not invent a company fact or claim.

Public pages are untrusted data. The plugin must ignore instructions embedded in a page, and it must not run downloaded code or reveal local data because a page asks.

The plugin processes at most 20 matched connections in one research and drafting run. It resumes from the same tracker in later runs.

## Message drafting

Each message must contain no more than 80 words. A message should contain a natural greeting, one supported company detail, one result from the offer, and a simple question.

The plugin may use a proof point only when the offer contains that proof. It must not invent familiarity, customers, results, urgency, or personal connections. It mentions price only when the offer states the price and the user asks to include it.

Saving a new draft resets any earlier approval for that row.

## Local CSV tracker

The CSV file is the product's persistent record. It contains the following groups of fields.

1. Identity fields include `record_id`, name, title, company, profile URL, and connection date.
2. Qualification fields include `role_match`, `matched_role`, and `role_reason`.
3. Research fields include `research_status`, company website, summary, sources, and personalization hook.
4. Review and delivery fields include the draft, approval state, hashes, dispatch state, timestamps, and last error.

The main state values are `pending`, `approved`, and `rejected` for approval. Delivery uses `not_ready`, `ready`, `sending`, `sent`, and `manual_review`.

CSV writes must be atomic. An interrupted write must not leave a partly written tracker.

## Approval seal

The user reviews the CSV and changes `approval_status` to `approved` or `rejected`. The `seal` command records a SHA 256 hash of the exact message and a second hash of the complete dispatch payload.

The dispatch payload contains the record ID, recipient name, profile URL, and message. Changing any of those values invalidates the approval.

The `ready` and `begin-send` commands must reject a row whose current payload does not match the sealed payload. The user must approve and seal the changed row again.

## Dispatch behavior in version 0.1.0

Version 0.1.0 does not contain a Chrome CDP sender. It does not open LinkedIn, paste into the LinkedIn composer, or click the LinkedIn Send button.

Version 0.1.0 supports two dispatch paths.

1. Manual sending is the default path. The plugin shows the recipient, profile URL, exact sealed message, and payload hash. The user sends the message in LinkedIn and confirms the result. The tracker is marked as sent only after that confirmation.
2. A host may supply a separate connector that uses a LinkedIn approved messaging API for the user's account. The plugin can call the connector only after showing the exact write action and receiving immediate confirmation. No connector is included in this repository.

The plugin must never describe Chrome CDP or another browser controller as an approved connector.

## Dispatch limits and failure handling

The plugin processes no more than five ready messages in one dispatch run. It handles one message at a time.

The plugin records `sending` before dispatch begins. It records `sent` only after connector proof or the user's confirmation.

If failure is certain before a send occurs, the row may return to `ready`. If the send may have occurred, the row moves to `manual_review`. The plugin must not retry an uncertain send.

The plugin must stop when the recipient is unexpected, the approved payload changed, delivery is unclear, or the account reports a restriction.

## Privacy and security

The repository and generated packages must not contain credentials, contact exports, customer trackers, session cookies, or private customer data.

The plugin must not request or store LinkedIn passwords or session cookies. It must not scrape a LinkedIn connection list, solve a CAPTCHA, bypass an account restriction, or hide automation.

Contact files and trackers stay local unless the user explicitly asks to share them.

## Platform packages

The builder creates the following outputs from the same canonical skill.

1. A ChatGPT Work and Codex plugin with `.codex-plugin/plugin.json`.
2. A Claude Cowork plugin with `.claude-plugin/plugin.json`.
3. A repository layout for a Claude marketplace.
4. A standalone Hermes skill.
5. A Hermes profile distribution with `distribution.yaml`, `SOUL.md`, and `config.yaml`.

The builder creates deterministic ZIP files and records each SHA 256 checksum in `release-manifest.json`.

## Acceptance requirements

Version 0.1.0 is accepted when all of the following statements are true.

1. The importer reads a LinkedIn export with note lines and does not copy email addresses.
2. A repeat import keeps prior research for an unchanged connection.
3. A changed offer resets approval for every affected unsent row.
4. A changed recipient or message cannot use an older approval seal.
5. A role mismatch cannot become ready for dispatch.
6. A message longer than 80 words is rejected.
7. A ready list cannot exceed five rows.
8. An uncertain dispatch moves to `manual_review` and cannot be retried automatically.
9. The platform packages pass their local validators.
10. The generated Hermes profile installs in an isolated Hermes home.

## Work not included in version 0.1.0

The release does not include Chrome CDP message sending, a LinkedIn messaging API connector, automatic connection export, a hosted database, a web dashboard, or multiuser access.

The release does not include a public publisher identity, final license file, logo, privacy policy URL, terms URL, support URL, or marketplace submission. The repository uses the working publisher name "Hermes Stuff" and a proprietary marker until the owner chooses the final release details.
