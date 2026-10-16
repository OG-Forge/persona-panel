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

## Prompt injection

The website under test is untrusted: its text reaches the panel agents (digest, page names, measured-check labels), the live walkers (`walk.py` output) and, through their result files, the synthesizer. A hostile page could try to talk an agent into running commands, reading your files or writing somewhere else. Mitigations, in layers:

1. **Restricted agents.** The plugin ships `agents/pp-panelist.md` (tools: Read, Write), `pp-walker.md` (Bash, Read, Write) and `pp-synthesizer.md` (Read, Write). None can fetch URLs, search or edit beyond these tools, and their system prompts say site content is data.
2. **Guard hook.** `hooks/hooks.json` runs `hooks/pp_guard.py` before every tool call. It identifies the agent from the hook input's `agent_type` (`persona-panel:pp-*` for the plugin, `pp-*` for manual copies) and, for those agents only:
   - Read: only files under the configured `runs_dir` and the skill's `references/`;
   - Write/Edit: panelist only `results/*.json`, walker also its `walk/` folder, synthesizer only `synthesis.json`, all inside `runs_dir`;
   - Bash/PowerShell: walker only, and only a single `"PY" ".../walk.py" "<run>/walk/<pid>" <command> [args]` call made of quoted strings and plain words, with no `;`, `&`, `|`, backticks, `$`, `<`, `>` or line breaks; the script must be persona-panel's own `walk.py` and the interpreter a Python outside the runs folder;
   - everything else is denied with a reason, and a check that fails denies.
   The main session and every other agent get no output from the hook and are untouched.
3. **Untrusted blocks.** Every site-derived input in a brief is wrapped in `<untrusted_site_content id="NONCE">`...`</untrusted_site_content id="NONCE">` with a random per-run nonce the site never sees, and any occurrence of the tag name inside the content is neutralised, so a page can't close the block early. The walker's start URL is kept out of its command lines (`walk/<pid>/start.json`), `walk.py` labels and wraps page text in its output, and `aggregate.py` wraps the persona-written part of `issues_digest.md` for the synthesizer. Capture slugs, which appear in screenshot file paths, are reduced to `a-z`, `0-9` and `-`.
4. **Images.** Briefs and the report only open `.png`/`.jpg`/`.jpeg`/`.webp` files that resolve inside `runs_dir` (or the run folder), so a result file can't make the report embed an arbitrary local file. Concept images are copied into the run first.

Limits:

- **Text inside screenshots can't be delimited.** An agent reading a screenshot sees whatever the page drew; the agents' rules are the only defence there, backed by the tool restrictions above.
- **The restrictions apply only to a plugin install, or a manual install with the agents and hook copied in** ([docs/INSTALL.md](docs/INSTALL.md#safety-restrictions-for-a-manual-install-recommended)). Otherwise the skill falls back to `general-purpose` agents and tells you the restrictions are off.
- The hook needs a POSIX `sh` (Git Bash on Windows) and Python 3 on `PATH`. If `sh` is missing, Claude Code reports a hook error and the call is not checked (the agents' tool lists still apply); if no Python is found, the launcher denies pp-* calls.
- A model can still write misleading text into its own result file; the synthesis and report treat results as data and escape them.

## Walker safety guarantees

Live walkers browse a real website in a headless Chromium driven by `walk.py`. Besides the rules in their brief, `walk.py` enforces in code (the checks live in `scripts/safety.py` and are unit-tested):

- **Same site only.** Top-level navigation to another site is blocked, `goto` to another site or to a non-http(s) URL (`data:`, `javascript:`, `file:`) is refused, and new tabs that open off-site are closed. Blocked attempts are reported back to the walker.
- **No personal data.** `type`, `select` and printable `press` keys are refused in fields whose type, name, autocomplete tokens, id, placeholder, aria-label, label text, inputmode or title suggests a password, email, phone, card number, expiry, CVV/CVC, OTP, address, any kind of name, date of birth, UPI/VPA, Aadhaar, PAN, SSN, IBAN/IFSC/account number, GST, or a login/username. `contenteditable` elements are checked the same way. ZIP/postal/PIN-code fields accept only the test values `110001` or `10001`.
- **Isolated browser.** Each walker gets its own fresh browser profile under the run folder. No cookies or logins from your own browser are used.

Their brief also tells them never to pay, sign up, log in or enter real personal data, and to stop at the first checkout screen. These rules must never be relaxed; PRs may only tighten them.

Capture and the UX checks (`capture.py`, `probe.py`) only load pages, scroll, click in-page buttons and same-site links, and press Back. They don't type into anything.

## Your responsibility for third-party sites

persona-panel loads and interacts with the website you point it at, from your machine and IP address. You are responsible for making sure you're allowed to do that: run it on sites you own or have permission to test, and respect their terms of service and rate limits. Reports and screenshots are saved locally in your runs folder; treat them as you would any copy of that site's content.
