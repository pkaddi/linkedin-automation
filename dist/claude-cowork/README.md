# LinkedIn Decision Maker Outreach

LinkedIn Decision Maker Outreach creates researched messages for relevant people who are already connected to the user on LinkedIn. It reads an offer, a list of acceptable roles, and the user's LinkedIn `Connections.csv` export.

The plugin saves its work in a local CSV file. A later run can see which connections were researched, which messages are waiting for approval, and which messages were marked as sent.

Version 0.1.0 does not automate LinkedIn through Chrome CDP. It does not click the LinkedIn Send button. After approval, it either gives the user the exact message for manual sending or uses a separate LinkedIn approved messaging connector supplied by the host. No such connector is included in this repository.

Read [REQUIREMENTS.md](REQUIREMENTS.md) for the full product behavior and limits.

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
