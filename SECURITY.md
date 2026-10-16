# Security policy

## Reporting a vulnerability

Please report security problems **privately** through GitHub's private vulnerability reporting: go to the repository's **Security** tab and click **Report a vulnerability** (https://github.com/OG-Forge/persona-panel/security/advisories/new).

Don't open a public issue, pull request or discussion for a vulnerability.

Include what you found, how to reproduce it, the version (`version` in `.claude-plugin/plugin.json`) and your OS. The maintainer ([@darthfl45h](https://github.com/darthfl45h)) will acknowledge the report, keep you updated in the advisory, and credit you in the fix unless you'd rather not be named. This is a one-person project, so please allow reasonable time for a fix before disclosing.

## Supported versions

Only the latest release gets fixes. To update, in a Claude Code session use `/plugin` → Marketplaces → `og-forge` → Update marketplace (or `/plugin` → Installed → `persona-panel` → Update now); from a shell run `claude plugin marketplace update og-forge` then `claude plugin update persona-panel@og-forge`. Then run `/reload-plugins` or start a new session. See [docs/INSTALL.md](docs/INSTALL.md#updating).

## Scope

In scope:

- the scripts in `skills/persona-panel/scripts/`, including anything that lets a run write outside the run folder or `~/.persona-panel`, or execute code it shouldn't;
- **walker safety bypasses**: any way a live walker can leave the site under test, open off-site pages, or type into password, email, phone, address, name, card, CVV or OTP fields (see below);
- the agent briefs in `skills/persona-panel/references/` if a crafted website can use them to make agents do something harmful beyond the run (prompt injection that escapes the brief's rules);
- the plugin and marketplace manifests, the CI workflow, and `setup_env.py` (supply-chain issues).

Out of scope:

- vulnerabilities in Claude Code, Playwright, Chromium, Pillow or Python themselves (report those upstream);
- the quality or accuracy of simulated persona feedback;
- problems that need an attacker who already controls your machine or your `~/.persona-panel` folder.

## Walker safety guarantees

Live walkers browse a real website in a headless Chromium driven by `walk.py`. Besides the rules in their brief, `walk.py` enforces in code:

- **Same site only.** Top-level navigation to another site is blocked, `goto` to another site is refused, and new tabs that open off-site are closed. Blocked attempts are reported back to the walker.
- **No personal data.** Typing into fields whose type, name, autocomplete, id or placeholder suggests a password, email, phone, mobile, address, name, card, CVV or OTP is refused.
- **Isolated browser.** Each walker gets its own fresh browser profile under the run folder. No cookies or logins from your own browser are used.

Their brief also tells them never to pay, sign up, log in or enter real personal data, and to stop at the first checkout screen. These rules must never be relaxed; PRs may only tighten them.

Capture and the UX checks (`capture.py`, `probe.py`) only load pages, scroll, click in-page buttons and same-site links, and press Back. They don't type into anything.

## Your responsibility for third-party sites

persona-panel loads and interacts with the website you point it at, from your machine and IP address. You are responsible for making sure you're allowed to do that: run it on sites you own or have permission to test, and respect their terms of service and rate limits. Reports and screenshots are saved locally in your runs folder; treat them as you would any copy of that site's content.
