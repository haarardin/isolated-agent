# Isolated job-application agent (Debian 13)

Dedicated two-container runtime reusing the repository's existing base/Codex
images, but not Go, Serena, DevOps tools, PostgreSQL, Redis or GitHub MCP.

## Installation

From the repository root on Debian 13:

    ./install.sh

Requires working rootless Podman, podman-compose, make and python3 on the host.
Does not install host Chromium, npm, LibreOffice or Python dependencies.
The installer is repeatable: it preserves state, saved approvals and cookies.
Use ./install.sh --rebuild when deliberately updating the image.

Directories under job-apply/state are private and gitignored:

    state/candidate/         source profile, answers, master DOCX/JSON
    state/applications/      vacancy-specific DOCX, PDF, answers, state, previews
    state/approvals/         host-only approval files
    state/browser-profile/   Chromium cookies and sessions (never mounted in agent)
    state/codex/             separate Codex login and config
    state/vnc/               password and VNC credentials
    state/captures/          browser screenshots
    state/downloads/         browser downloads

The installer places empty examples in candidate/. Import your verified
master-resume.json, profile.json, answers.json and master-resume.docx before
processing a real application. Optional master-cover-letter.docx is supported.
Sensitive candidate files are NEVER published to this public repository.
A separate private candidate ZIP can be extracted into job-apply/state/ after installation.

## Commands

    ./job-apply/run.sh login             # Codex ChatGPT device authentication
    ./job-apply/run.sh agent             # interactive Codex
    ./job-apply/run.sh ps
    ./job-apply/run.sh logs
    ./job-apply/run.sh browser headed    # persistent profile + VNC
    ./job-apply/run.sh browser headless  # return to automation
    ./job-apply/run.sh down              # retains all data
    ./job-apply/smoke.sh

Headed browser viewing is available in any local browser at
http://127.0.0.1:6080/vnc.html (noVNC) or through a VNC viewer at
127.0.0.1:5901. Both ports are loopback-only. On a remote Debian server tunnel 5901 over SSH. Password is
in job-apply/state/vnc/password.txt (8 random characters; classic VNC limit).
When changing modes, existing browser pages will close; cookies persist.
Never expose VNC or the Playwright MCP HTTP endpoint to the Internet.
Log in manually to ATS sites; handle CAPTCHA and 2FA yourself.

## Example application workflow

Inside Codex:

> Open https://company.example/careers/go, extract requirements, compare
> them against my verified master resume, generate an appropriate DOCX/PDF
> resume and cover letter, fill the application form, and stop before Submit.

Codex creates a record and prepares artifacts with:

    python3 /opt/jobapply/jobctl.py new --url https://example.com/jobs/go --company Example --role 'Senior Go Engineer'
    # Then update applications/<id>/vacancy.json after reading the vacancy.
    python3 /opt/jobapply/jobctl.py prepare <id> --focus rtc
    python3 /opt/jobapply/jobctl.py status <id>
    python3 /opt/jobapply/jobctl.py rebuild <id>  # after DOCX MCP edits: PDF and letter text
    python3 /opt/jobapply/jobctl.py audit <id>    # validate without changing files
    python3 /opt/jobapply/jobctl.py block <id> --status manual_action_required --reason "CAPTCHA"

A prepared application is awaiting approval and cannot be regenerated in place.
Review it, including the actual ATS form and any required answers. On the host:

    ./job-apply/run.sh approve <id>

The approval binds the exact URL, generated PDF hashes, cover letter text,
vacancy metadata and application answers. Then tell Codex
explicitly that it may send this application. After seeing real confirmation,
Codex may record the receipt with jobctl.py submitted <id> --evidence ... .
A possibly submitted application must not be retried automatically.

## Implemented vs. not guaranteed

- Real Podman/Chromium/Playwright MCP and DOCX MCP configuration.
- Deterministic resume/cover-letter first drafts from verified source records.
- DOCX validation; headless LibreOffice PDF conversion; text and page geometry
  checks; PDF page previews; persistent application status and host approvals.
- Local browser/form/upload smoke tests without submitting to an external ATS.
- ATS application navigation is driven by Codex/Playwright dynamically, not
  hard-coded Greenhouse/Lever/Ashby/Workday site adapters. Site-specific flows,
  changing DOM, CAPTCHA, employer policies and geography may block.
- An LLM/browser tool cannot provide a mathematically enforced submit gate:
  approval is a workflow policy, not a browser-level network firewall.
  Do not use unattended full autonomy until an independent submit interceptor
  exists. Auto-submit allowlists are deliberately disabled.
- Visual PDF checks require the agent to inspect preview PNG files; automatic
  geometry/text checks cannot detect every font or kerning defect.
- Never treat a rendered document as proof of fact correctness.

## Security and backup

No host container socket or SSH directory is mounted. Codex cannot read
Chromium's profile, and the browser can only read generated application files.
The browser container has outbound network access to public ATS sites.
Both containers use outer rootless Podman; Chromium needs --no-sandbox inside
that container. All local VNC access must remain loopback-only.
Protect and back up state/; it contains browser tokens and PII. Do not share
screenshots, cookies, Codex authentication files or candidate profiles.
Do not accidentally mount this data into unrelated containers.
