# Publishing the plugin

The repository root is the canonical source. The `skills/` directory contains the shared skill and tracker code. The root also contains the Codex manifest, Claude manifest, and Hermes profile files.

## Build the packages

```bash
python packaging/build.py
```

The builder writes the following files to `dist/`.

1. `chatgpt-work-0.1.0.zip` contains the ChatGPT Work and Codex plugin.
2. `claude-cowork-0.1.0.zip` contains the Claude Cowork plugin.
3. `claude-marketplace-0.1.0.zip` contains a Git repository layout for a Claude marketplace.
4. `hermes-skill-0.1.0.zip` contains the standalone Hermes skill.
5. `hermes-profile-0.1.0.zip` contains the Hermes profile distribution.

The builder also writes `release-manifest.json` with a SHA 256 checksum for each ZIP file. The unpacked directories in `dist/` are the exact inputs used to create those files.

## Hermes

The repository root is a Hermes profile distribution. A local user can install it with:

```bash
hermes profile install . --name linkedin-decision-maker-outreach --yes
```

After the repository is on GitHub, users can install and update it with:

```bash
hermes profile install GIT_URL --name linkedin-decision-maker-outreach
hermes profile update linkedin-decision-maker-outreach
```

The standalone skill can also be published with:

```bash
hermes skills publish skills/linkedin-decision-maker-outreach \
  --to github --repo OWNER/REPOSITORY
```

Hermes documentation covers [profile distributions](https://hermes-agent.nousresearch.com/docs/user-guide/profile-distributions), [profile commands](https://hermes-agent.nousresearch.com/docs/reference/profile-commands/), and [skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).

## Claude Cowork

The Cowork ZIP contains `.claude-plugin/plugin.json` and `skills/` at its root. A user can upload the ZIP as a custom plugin.

The Claude marketplace ZIP can be unpacked into a separate Git repository. Users can then add the marketplace and install the plugin with:

```text
/plugin marketplace add OWNER/REPOSITORY
/plugin install linkedin-decision-maker-outreach@hermes-stuff
```

Validate both forms before release:

```bash
claude plugin validate dist/claude-cowork --strict
claude plugin validate dist/claude-marketplace --strict
```

Claude documentation covers [plugins](https://code.claude.com/docs/en/plugins) and [plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).

## ChatGPT Work and Codex

The ChatGPT ZIP contains `.codex-plugin/plugin.json` and `skills/` at its root. OpenAI accepts plugins that contain only skills.

Validate the package with the current OpenAI plugin validator before submission. OpenAI documentation covers [plugin packaging](https://developers.openai.com/plugins/build/plugins) and [plugin submission](https://developers.openai.com/plugins/deploy/submission).

## Release information still needed

The owner must choose the final publisher name and license before public release. Public listings also need a website, privacy policy, terms, support contact, logo, and any required screenshots.

The owner must test one controlled manual dispatch or an approved API connector against their own LinkedIn account. Version 0.1.0 does not include Chrome CDP sending or a LinkedIn API connector.

Do not commit customer exports, trackers, credentials, cookies, or private research to the release repository.
