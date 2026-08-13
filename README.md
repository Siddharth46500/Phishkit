# Phishkit
# logme.py — Phishing Simulation Toolkit

A lightweight, self-contained credential-capture and IP-logging tool built for
**authorized** penetration testing, red-team engagements, and security
awareness training.

You can serve your own HTML login templates (zphisher-compatible) or live-clone
any login page on the fly. Every form submission is logged with the victim's
IP address, User-Agent, and timestamp.

> ⚠️ **WARNING — Authorized use only.** This tool captures login credentials.
> Use it exclusively against systems you own, or within the scope of a signed
> penetration-testing / red-team agreement. Misuse against third parties is
> illegal in most jurisdictions. You are responsible for your own actions.

---

## Features

- **Two operating modes**
  - `Mode 1` — serve your own static HTML templates from `site/`
    (drop in zphisher-style templates; the tool rewrites all forms to capture)
  - `Mode 2` — live-clone **any** login page: HTML is fetched and rewritten,
    while CSS/JS/images stream straight from the real site, so the page looks
    100% authentic
- **Credential + IP capture** — every submission is appended to `log.bin` with
  victim IP, User-Agent, timestamp, and all form fields
- **Injected JS collector** — also catches XHR/fetch POST bodies from modern
  JavaScript apps, not just classic HTML forms
- **Post-capture redirect** — the victim is transparently redirected to the
  real site after submitting, so the flow looks natural
- **Public link support** — optional cloudflared tunnel for internet exposure
- **Path-traversal-safe** file serving, threaded server (no request blocking),
  and per-request terminal logging for easy debugging

---

## Installation

Requires **Python 3.6+** (no third-party packages needed).

```bash
git clone https://github.com/siddharth46500/phishkit.git
cd phishkit
mkdir -p site
