# LinkedIn Decision Maker Outreach

LinkedIn Decision Maker Outreach creates researched messages for relevant people who are already connected to the user on LinkedIn. It reads an offer, a list of acceptable roles, and the user's LinkedIn `Connections.csv` export.

The plugin saves its work in a local CSV file. A later run can see which connections were researched, which messages are waiting for approval, and which messages were sent.

Version 0.2.0 adds sending that requires approval through Chrome CDP. It attaches to a Chrome process the user started and uses the LinkedIn session already signed in there. The sender verifies the recipient and exact sealed text, then records `sent` only after the exact message appears as a new outgoing message. It does not read passwords or cookies, and it does not launch another browser.

The automated tests use a fake browser session. A publisher must still complete the controlled live send test using accounts they own before presenting the release as tested with LinkedIn.

Chrome CDP is the only automated LinkedIn transport. Manual sending remains a recovery path.

## Inputs

The plugin needs an offer Markdown file, a LinkedIn `Connections.csv` export, and a text file with one accepted decision maker role per line. Example files are in `skills/linkedin-decision-maker-outreach/references/`.

## Create the tracker

```bash
python3 skills/linkedin-decision-maker-outreach/scripts/outreach_tracker.py init \
  --offer offer.md \
  --connections Connections.csv \
  --roles decision-maker-roles.txt \
  --output outreach.csv
```

The command merges connections into an existing tracker when `outreach.csv` already exists. It does not discard completed research or drafts for unchanged records.

## Run the daily preparation queue

```bash
python3 skills/linkedin-decision-maker-outreach/scripts/outreach_tracker.py \
  research-queue --tracker outreach.csv --limit 20
```

Hermes researches these companies on the public web and saves sourced drafts. The user reviews the CSV and marks chosen rows `approved`; `seal` then binds each exact recipient and message.

## Connect Chrome and dispatch

Start Chrome yourself with a dedicated profile and a local debugging endpoint, then sign in to LinkedIn in that visible browser. For example on Linux:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-linkedin-outreach"
```

Install the maintained CDP client. This installs no browser because the sender attaches to your Chrome:

```bash
python3 -m pip install -r skills/linkedin-decision-maker-outreach/requirements.txt
```

Run the read only check, then make a separate explicit dispatch call:

```bash
python3 skills/linkedin-decision-maker-outreach/scripts/linkedin_cdp.py \
  preflight --cdp-url http://127.0.0.1:9222

python3 skills/linkedin-decision-maker-outreach/scripts/linkedin_cdp.py \
  dispatch --tracker outreach.csv --cdp-url http://127.0.0.1:9222 \
  --limit 5 --confirm-send
```

Dispatch is serial and stops on the first mismatch or uncertain delivery. See [REQUIREMENTS.md](REQUIREMENTS.md) for the full safety contract.

## Test the repository

The tracker uses only the Python standard library. CDP sending uses Playwright's CDP attachment client. The tests require pytest.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

## Build distribution files

```bash
python3 packaging/build.py
```

The builder writes platform folders, ZIP files, and SHA 256 checksums to `dist/`. It creates packages for ChatGPT Work and Codex, Claude Cowork, a Claude marketplace, a Hermes skill, and a Hermes profile.

## Use this repository as a Hermes profile

```bash
hermes profile install . --name linkedin-decision-maker-outreach --yes
```

Read [packaging/PUBLISHING.md](packaging/PUBLISHING.md) before publishing the repository or submitting a marketplace listing.
