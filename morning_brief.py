#!/usr/bin/env python3
"""
Morning Market Brief
--------------------
Uses Claude (with the web search tool) to scan the last 24-48h of world news and
produce a concise pre-market brief: market pulse, top risks, market-moving news,
short- and long-term opportunities, and notes on your own watchlist. Emails it to
you and saves a dated copy locally.

Run manually:   python3 morning_brief.py
Scheduled:      see README.md (launchd, runs every morning)
"""

import os
import sys
import ssl
import json
import smtplib
import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

HERE = Path(__file__).resolve().parent


# ----------------------------------------------------------------------
# Minimal .env loader (no extra dependency; works under launchd, which does
# not inherit your shell environment).
# ----------------------------------------------------------------------
def load_env():
    env_path = HERE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()

try:
    import anthropic
except ImportError:
    sys.exit("Missing dependency. Run:  pip install anthropic")

# ----------------------------------------------------------------------
# Config (from .env)
# ----------------------------------------------------------------------
API_KEY   = os.environ.get("ANTHROPIC_API_KEY")
MODEL     = os.environ.get("BRIEF_MODEL", "claude-sonnet-4-6")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
EMAIL_TO  = os.environ.get("EMAIL_TO", SMTP_USER or "")

if not API_KEY:
    sys.exit("ANTHROPIC_API_KEY is not set. Add it to your .env file (see README.md).")


# ----------------------------------------------------------------------
# Load your portfolio / watchlist for personalization
# ----------------------------------------------------------------------
def load_portfolio():
    p = HERE / "portfolio.json"
    if not p.exists():
        return {"holdings": [], "watchlist": [], "focus": ""}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"holdings": [], "watchlist": [], "focus": ""}


# ----------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------
SYSTEM_PROMPT = """You are a markets analyst writing a concise pre-market morning brief \
for an individual investor based in Melbourne, Australia who follows GLOBAL markets. \
Use the web_search tool to gather news and developments from roughly the last 24-48 hours \
across geographies (US, Europe, Asia, Australia) and asset classes (equities, rates, FX, \
commodities, crypto).

Produce these sections, in this order, using these exact headings:

1. World Economic News — the most important economic and market developments of the last \
24-48 hours: central bank decisions and commentary, major data releases (inflation, jobs, \
GDP, PMIs), fiscal/trade policy, geopolitics, commodities, and major corporate news. \
Bullets, each with a one-line summary of what happened.

2. Impact on Securities & Industries — for the developments above, explain how they affect \
specific securities, sectors and industries. For each, clearly split <strong>Short term</strong> \
(days-to-weeks) and <strong>Long term</strong> (months-to-years) effects, naming which \
sectors/companies are likely helped versus hurt and why.

3. Potential Beneficiaries — concrete companies, ETFs, or securities that may benefit from \
these changes, separated into <strong>Short term</strong> and <strong>Long term</strong> \
ideas. For each, one line on the thesis and one line on the main risk. These are ideas to \
research, not recommendations.

4. Your Portfolio Impact — using the user's holdings provided in the prompt, assess how \
today's developments could affect each relevant holding (positive / negative / neutral) \
with a one-line reason, and split short-term vs long-term where it matters. Flag any \
concentration or risk worth watching. Holdings not touched by today's news can be grouped \
or briefly noted.

5. Sources — 4 to 8 key source links you used.

Rules:
- This is INFORMATIONAL and EDUCATIONAL, not personalized financial advice. Frame all \
opportunities and portfolio notes as analysis and ideas to research and verify, never as \
instructions to buy or sell.
- Be specific and concrete: name companies, tickers, sectors, price levels, data, events. \
No filler.
- Always distinguish SHORT-TERM from LONG-TERM clearly in sections 2, 3 and 4.
- Balance bullish and bearish framing; state uncertainty honestly.
- Output a CLEAN HTML FRAGMENT only. Use <h2>, <h3>, <p>, <ul>, <li>, <strong>, and \
<a href>. Do NOT include <html>, <head>, <body>, markdown, or code fences.
- Keep it skimmable in 4-5 minutes."""


def build_user_prompt(pf):
    today = datetime.date.today().strftime("%A, %d %B %Y")
    holdings = ", ".join(pf.get("holdings", [])) or "(none provided)"
    watchlist = ", ".join(pf.get("watchlist", [])) or "(none provided)"
    focus = pf.get("focus", "") or "general global markets"
    return (
        f"Today is {today}. Write today's morning brief.\n\n"
        f"My current holdings: {holdings}\n"
        f"My watchlist: {watchlist}\n"
        f"My focus areas: {focus}\n\n"
        "Search for the latest before writing. In the 'Your Portfolio Impact' section, "
        "focus on how today's developments could affect my holdings specifically."
    )


# ----------------------------------------------------------------------
# Generate the brief
# ----------------------------------------------------------------------
def generate_brief():
    pf = load_portfolio()
    client = anthropic.Anthropic(api_key=API_KEY)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=3500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(pf)}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


# ----------------------------------------------------------------------
# Wrap the fragment in a styled HTML email
# ----------------------------------------------------------------------
def wrap_html(fragment):
    today = datetime.date.today().strftime("%A, %d %B %Y")
    return f"""<!DOCTYPE html>
<html><body style="margin:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1f2e;">
<div style="max-width:680px;margin:0 auto;background:#ffffff;">
  <div style="background:#0B1020;color:#fff;padding:24px 28px;">
    <div style="font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#F5A623;">Morning Brief</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px;">{today}</div>
  </div>
  <div style="padding:8px 28px 24px;line-height:1.55;font-size:15px;">
    {fragment}
  </div>
  <div style="padding:16px 28px;border-top:1px solid #e3e6ec;color:#8b95ad;font-size:12px;line-height:1.5;">
    Generated automatically with Claude + live web search. <strong>Informational only — not
    financial advice.</strong> Opportunities are ideas to research and verify, not
    instructions to act. Always confirm against primary sources before making decisions.
  </div>
</div>
</body></html>"""


# ----------------------------------------------------------------------
# Send + archive
# ----------------------------------------------------------------------
def archive(html):
    folder = HERE / "briefs"
    folder.mkdir(exist_ok=True)
    fname = folder / f"brief-{datetime.date.today().isoformat()}.html"
    fname.write_text(html, encoding="utf-8")
    return fname


def send_email(html):
    if not (SMTP_USER and SMTP_PASS and EMAIL_TO):
        print("Email not configured (SMTP_USER / SMTP_PASS / EMAIL_TO missing) — saved file only.")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Morning Brief — {datetime.date.today().strftime('%a %d %b')}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText("Your morning brief is attached as HTML. View in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [EMAIL_TO], msg.as_string())
    print(f"Sent to {EMAIL_TO}")
    return True


def main():
    print("Gathering news and writing your brief…")
    try:
        fragment = generate_brief()
    except Exception as e:
        sys.exit(f"Failed to generate brief: {e}")
    if not fragment:
        sys.exit("The model returned an empty brief. Try again or check your API credits.")
    html = wrap_html(fragment)
    path = archive(html)
    print(f"Saved: {path}")
    try:
        send_email(html)
    except Exception as e:
        print(f"Email failed ({e}). The brief is still saved at: {path}")


if __name__ == "__main__":
    main()
