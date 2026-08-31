# LinkedIn Decision Maker Outreach

LinkedIn Decision Maker Outreach creates researched messages for relevant people who are already connected to the user on LinkedIn. It reads an offer, a list of acceptable roles, and the user's LinkedIn `Connections.csv` export.

The plugin saves its work in a local CSV file. A later run can see which connections were researched, which messages are waiting for approval, and which messages were marked as sent.

Version 0.1.1 does not connect to LinkedIn. It does not open a browser, paste a message, or click Send. The current release prepares the exact message for manual sending and records the result after the user confirms it.

The next milestone is version 0.2.0. It will add automatic sending through Chrome CDP and no other automated transport. Read [REQUIREMENTS.md](REQUIREMENTS.md) for the exact CDP behavior and acceptance tests.

The CDP sender has not been implemented yet.

## Inputs

The plugin needs an offer Markdown file, a LinkedIn `Connections.csv` export, and a text file with one accepted decision maker role per line. Example files are in `skills/linkedin-decision-maker-outreach/references/`.

## Create the tracker

```bash
python skills/linkedin-decision-maker-outreach/scripts/outreach_tracker.py init \
  --offer offer.md \
  --connections Connections.csv \
  --roles decision-maker-roles.txt \
  --output outreach.csv
```

The command merges connections into an existing tracker when `outreach.csv` already exists. It does not discard completed research or drafts for unchanged records.

## Test the repository

The tracker uses only the Python standard library. The tests require pytest.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Build distribution files

```bash
python packaging/build.py
```

The builder writes platform folders, ZIP files, and SHA 256 checksums to `dist/`. It creates packages for ChatGPT Work and Codex, Claude Cowork, a Claude marketplace, a Hermes skill, and a Hermes profile.

## Use this repository as a Hermes profile

```bash
hermes profile install . --name linkedin-decision-maker-outreach --yes
```

Read [packaging/PUBLISHING.md](packaging/PUBLISHING.md) before publishing the repository or submitting a marketplace listing.
