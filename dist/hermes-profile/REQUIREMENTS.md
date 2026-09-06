# Product requirements

## Purpose

The plugin helps a user prepare relevant LinkedIn outreach for decision makers who are already first degree connections. It keeps research, drafts, approvals, and delivery records in a local CSV file.

The plugin must never treat a draft as permission to send a message. The user must approve the exact recipient and message before dispatch.

## Current implementation status

Version 0.2.0 is a local preparation, review, tracking, and Chrome CDP delivery tool. The CDP sender is implemented. The controlled live-send acceptance test must still be completed by the publisher with accounts they own.

The current code can complete the following work.

1. It imports a LinkedIn `Connections.csv` export that the user downloaded manually.
2. It matches decision maker roles and keeps research, sources, drafts, approvals, and delivery history in `outreach.csv`.
3. It seals the exact recipient and message with SHA 256 hashes, and it rejects a changed recipient or message.
4. It prepares a queue of up to five approved rows and records local state changes.
5. It attaches to a user-managed Chrome process through CDP and sends only exact, approved messages.
6. It builds packages for Hermes, Claude Cowork, Claude marketplaces, and ChatGPT Work or Codex.

The `ready`, `begin-send`, `mark-sent`, and `mark-failed` commands only read or update the local CSV file. Browser operations live in the separate `linkedin_cdp.py` sender, which calls the same tracker state checks.

The CDP sender uses Playwright's maintained CDP attachment client. It does not contain Selenium, a LinkedIn API client, OAuth, or a messaging connector. Manual sending remains a recovery path.

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

## Current manual delivery behavior

Version 0.1.1 can prepare a manual delivery handoff. The plugin shows the recipient, profile URL, exact sealed message, and payload hash. The user sends the message in LinkedIn and confirms the result. The tracker is marked as sent only after the user confirms that the exact message was sent.

The plugin processes no more than five ready messages in one run, and it handles one message at a time. If delivery is unclear, the row moves to `manual_review`. The plugin must not treat an uncertain message as safe to retry.

## Chrome CDP delivery

Version 0.2.0 adds LinkedIn message sending through Chrome CDP. CDP means the Chrome DevTools Protocol, which lets local code control an existing Chrome browser.

Chrome CDP must be the only automated LinkedIn transport. Version 0.2.0 must not add a LinkedIn API client, an OAuth flow, a host supplied messaging connector, or a generic connector interface. Manual handoff may remain as a recovery path, but all automatic sending must use CDP.

The CDP implementation must complete the following work.

1. It attaches to a user managed Chrome process through an explicit CDP endpoint. The default endpoint must be on `127.0.0.1` or `localhost`.
2. It uses the LinkedIn session that is already signed in inside that Chrome profile. It must not request, read, export, or store a LinkedIn password or session cookie.
3. It checks that LinkedIn is signed in and that the messaging interface is available before changing any tracker state.
4. It reads no more than five sealed rows from the local tracker and processes them one at a time.
5. It checks the current recipient, profile URL, message text, and approved payload hash immediately before opening LinkedIn.
6. It opens the stored LinkedIn profile, opens the message composer, and verifies the intended recipient before entering text.
7. It enters the exact sealed message without rewriting it, and it verifies the text in the composer before clicking Send.
8. It clicks Send only after the user has approved the CSV row and explicitly started the CDP dispatch command.
9. It verifies that the exact message appears as a new outgoing message before recording `sent` in the tracker.
10. It records `sending` before the click. It records `manual_review` when the click may have happened but delivery cannot be proved.

The CDP sender must fail closed. It must stop before sending when the browser is unavailable, LinkedIn is signed out, the recipient is different, the payload hash changed, the composer contains unexpected text, the UI cannot be identified, or LinkedIn shows an account warning or checkpoint.

The sender must not retry an uncertain send. It must not solve a CAPTCHA, bypass a restriction, hide automation, use anti detection code, or run concurrent sending sessions. A remote CDP endpoint must be rejected unless the user enables a separate explicit option for it.

LinkedIn selectors must live in a versioned selector file instead of being spread through the sending code. Each important control must have a small ordered set of selectors. A missing selector must produce a clear error and must not cause a click on an unverified element.

## CDP commands and files

Version 0.2.0 includes a dedicated CDP sender under the canonical skill. The distribution builder copies the sender and its selector file into every package.

The files are `scripts/linkedin_cdp.py` and `references/linkedin-selectors.json`. The sender uses a maintained CDP library, attaches through CDP, and does not launch a hidden or separate browser.

The sender must provide a read only preflight command. The command checks the CDP endpoint, Chrome version, LinkedIn sign in state, and required selectors. It must not open a composer or change the tracker.

The sender must provide a dispatch command with `--tracker`, `--cdp-url`, and `--limit` options. The command must require an explicit confirmation option before it can click Send. The limit must accept values from one to five.

The sender must use the existing tracker state commands instead of creating a separate database. It must call the same approval and payload checks before each attempt. The tracker schema must add only the fields needed to record the conversation URL, attempt ID, verification time, and delivery proof.

The CDP code must separate browser operations from tracker operations so automated tests can run against a fake CDP session. A live test must use an account and recipient owned by the publisher.

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

## Version 0.1.1 acceptance requirements

Version 0.1.1 is accepted when all of the following statements are true.

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

## CDP milestone acceptance requirements

Version 0.2.0 is accepted only when all of the following statements are true.

1. The sender attaches to a local Chrome CDP endpoint and reports a clear error when the endpoint is unavailable.
2. The sender detects a signed out LinkedIn session without requesting credentials.
3. The sender refuses every row that is not matched, researched, approved, sealed, and ready.
4. The sender verifies the recipient and exact sealed message before clicking Send.
5. A controlled test sends one message to an account owned by the publisher and verifies the exact outgoing message.
6. A batch cannot contain more than five messages, and only one message can be in progress.
7. A confirmed send records `sent`, its timestamp, and the approved payload hash.
8. An uncertain send records `manual_review` and is not retried automatically.
9. Automated tests cover the CDP state changes, recipient mismatch, text mismatch, selector failure, signed out state, and uncertain delivery.
10. The Hermes, Claude Cowork, Claude marketplace, and ChatGPT Work or Codex packages contain the CDP sender and pass their validators.

## Work not included

The release does not include automatic connection export, a hosted database, a web dashboard, or multiuser access. It does not add a LinkedIn API client, OAuth, or another automated transport.

The release does not include a public publisher identity, final license file, logo, privacy policy URL, terms URL, support URL, or marketplace submission. The repository uses the working publisher name "Hermes Stuff" and a proprietary marker until the owner chooses the final release details.
