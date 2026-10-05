#!/usr/bin/env python3
"""
generate_activity.py — custom contribution visualization for the profile README.

Fetches the last 12 months of public contribution data for the profile owner
via the GitHub GraphQL API and renders a self-contained, dual-mode (light/dark)
animated SVG at assets/activity.svg.

Design goals
  * stdlib only (urllib, json, xml) — no pip dependencies
  * NEVER destroy a valid existing asset when a fetch fails:
      - all network + parsing + rendering happens into a temp file
      - temp file is XML-validated before an atomic os.replace()
      - any error exits non-zero with a clear log and leaves assets/ untouched
  * honest data: every number rendered is computed from the API response

Usage
  GITHUB_TOKEN=...  python3 scripts/generate_activity.py [--user taher53-s]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.dom.minidom

# ── configuration ────────────────────────────────────────────────────────
API_URL = "https://api.github.com/graphql"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "activity.svg")
DEFAULT_USER = "taher53-s"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

# GitHub's own calendar scales — instantly readable, semantically "activity".
SCALE_LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
SCALE_DARK = ["#151b22", "#033a16", "#0e4429", "#006d32", "#26a641"]
LEVEL_FRAC = [0, 1, 3, 6]  # min contributions for levels 1..3 (4 = above)

MONO = "ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

W, H = 1040, 268
CELL, GAP = 13.5, 3.2
GRID_X, GRID_Y = 52, 130
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def log(msg: str) -> None:
    print(f"[activity] {msg}", flush=True)


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:  # local development: reuse the gh CLI's stored credential
        out = subprocess.run(["gh", "auth", "token"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            log("using token from `gh auth token`")
            return out.stdout.strip()
    except Exception:
        pass
    log("ERROR: no GITHUB_TOKEN env var and `gh auth token` unavailable.")
    sys.exit(2)


def fetch_calendar(user: str) -> dict:
    """Return {'days': [(date, count)], 'total': int} or exit non-zero."""
    body = json.dumps({"query": QUERY, "variables": {"login": user}}).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {get_token()}",
                 "Content-Type": "application/json",
                 "User-Agent": "profile-activity-generator"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log(f"ERROR: GitHub API HTTP {e.code} — {e.reason}. Keeping existing asset.")
        sys.exit(2)
    except Exception as e:
        log(f"ERROR: network failure — {e}. Keeping existing asset.")
        sys.exit(2)

    if "errors" in payload:
        msgs = "; ".join(err.get("message", "?") for err in payload["errors"])
        log(f"ERROR: GraphQL errors — {msgs}. Keeping existing asset.")
        sys.exit(2)

    try:
        cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total = int(cal["totalContributions"])
        weeks = cal["weeks"]
        assert len(weeks) >= 40, f"suspicious week count: {len(weeks)}"
    except Exception as e:
        log(f"ERROR: unexpected API shape — {e!r}. Keeping existing asset.")
        sys.exit(2)

    days, today = [], dt.date.today()
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for week in weeks:
        for d in week["contributionDays"]:
            try:
                assert date_re.match(d["date"])
                when = dt.date.fromisoformat(d["date"])
                count = int(d["contributionCount"])
                assert count >= 0
            except Exception as e:
                log(f"ERROR: malformed day {d!r} — {e!r}. Keeping existing asset.")
                sys.exit(2)
            if when <= today:  # never render future/empty trailing days
                days.append((when, count))

    if not days:
        log("ERROR: API returned zero days. Keeping existing asset.")
        sys.exit(2)

    days.sort()
    log(f"fetched {len(days)} days, total={total} (recount={sum(c for _, c in days)})")
    return {"days": days, "total": sum(c for _, c in days)}


# ── stats ───────────────────────────────────────────────────────────────
def compute_stats(days):
    counts = {d: c for d, c in days}
    active = sorted(d for d, c in counts.items() if c > 0)

    def streak(seq_dates):
        best = run = 0
        prev = None
        for d in seq_dates:
            run = run + 1 if (prev and (d - prev).days == 1) else 1
            best, prev = max(best, run), d
        return best

    longest = streak(active)
    current = 0
    end = max(counts)
    if counts.get(end, 0) == 0:  # today idle → streak may still live up to yesterday
        end -= dt.timedelta(days=1)
    while counts.get(end, 0) > 0:
        current += 1
        end -= dt.timedelta(days=1)

    months = {}
    for d, c in days:
        key = d.strftime("%Y-%m")
        months[key] = months.get(key, 0) + c
    busiest = max(months, default=None)
    busiest_str = (f"{MONTH_NAMES[int(busiest[5:7]) - 1]} {busiest[:4]}"
                   if busiest else "—")

    return {
        "total": sum(counts.values()),
        "active_days": len(active),
        "longest_streak": longest,
        "current_streak": current,
        "busiest_month": busiest_str,
        "peak_day": max(counts.values()),
        "days_span": len(counts),
    }


def level(count: int) -> int:
    for i in range(3, 0, -1):
        if count >= LEVEL_FRAC[i]:
            return i
    return 0


# ── rendering ────────────────────────────────────────────────────────────
_AMP, _LT, _GT = chr(38), chr(60), chr(62)


def esc(s: str) -> str:
    """XML-escape text (built via chr() so the source stays unambiguous)."""
    return (s.replace(_AMP, _AMP + "amp;")
             .replace(_LT, _AMP + "lt;")
             .replace(_GT, _AMP + "gt;"))


def render(user: str, data: dict, stats: dict) -> str:
    days = data["days"]
    step = CELL + GAP
    grid_w = 52 * step - GAP
    today = dt.date.today()

    cells, month_labels = [], []
    last_label_x, last_m = -10_000, None
    for wi, week in enumerate([days[i * 7:(i + 1) * 7] for i in range((len(days) + 6) // 7)]):
        x = GRID_X + wi * step
        seen_month = None
        for di, (d, c) in enumerate(week):
            y = GRID_Y + di * step
            lvl = level(c)
            fill = f"L{lvl}"
            cells.append(
                f'<rect class="{fill}" x="{x:.1f}" y="{y:.1f}" '
                f'width="{CELL}" height="{CELL}" rx="3"><title>{d.isoformat()} · '
                f'{c} contribution{"s" if c != 1 else ""}</title></rect>')
            if d.day <= 7:
                seen_month = (d.month, d.year)
        if seen_month and seen_month != last_m and x - last_label_x >= 58:
            month_labels.append(
                f'<text class="t-faint" x="{x:.1f}" y="{GRID_Y - 10}" '
                f'font-family="{MONO}" font-size="11" font-weight="600">'
                f'{MONTH_NAMES[seen_month[0] - 1]}</text>')
            last_label_x, last_m = x, seen_month

    weekday_tags = "".join(
        f'<text class="t-faint" x="{GRID_X - 12}" y="{GRID_Y + 9 + row * step}" '
        f'text-anchor="end" font-family="{MONO}" font-size="10.5">'
        f'{label}</text>'
        for row, label in ((0, "Mon"), (2, "Wed"), (4, "Fri"))
    )

    def chips(items):
        out, x = [], 52
        for value, label in items:
            text = f"{value} {label}"
            w = 7.2 * len(text) + 26
            out.append(
                f'<g class="chip"><rect x="{x:.0f}" y="76" width="{w:.0f}" '
                f'height="26" rx="13" class="chipbg"/>'
                f'<text class="t-primary" x="{x + w / 2:.0f}" y="93" '
                f'text-anchor="middle" font-family="{MONO}" font-size="12.5" '
                f'font-weight="600">{esc(value)} <tspan class="t-muted">{esc(label)}</tspan></text></g>')
            x += w + 10
        return "".join(out)

    header_chips = chips([
        (f"{stats['total']}", "contributions"),
        (f"{stats['active_days']}", "active days"),
        (f"{stats['longest_streak']}d", "longest streak"),
        (f"{stats['busiest_month']}", "busiest month"),
    ])

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="actTitle actDesc" font-family="{SANS}">
  <title id="actTitle">Contribution activity — {esc(user)}, last 12 months</title>
  <desc id="actDesc">Custom-generated contribution calendar: {stats['total']} contributions across {stats['active_days']} active days; longest streak {stats['longest_streak']} days; busiest month {stats['busiest_month']}.</desc>

  <style>
    .bg {{ fill:#ffffff; }}
    .card {{ fill:#ffffff; stroke:#d0d7de; stroke-width:1.5; }}
    .t-primary {{ fill:#1f2328; }} .t-muted {{ fill:#59636e; }} .t-faint {{ fill:#818b98; }}
    .chipbg {{ fill:#f6f8fa; stroke:#d0d7de; stroke-width:1; }}
    .L0 {{ fill:#ebedf0; }} .L1 {{ fill:#9be9a8; }} .L2 {{ fill:#40c463; }}
    .L3 {{ fill:#30a14e; }} .L4 {{ fill:#216e39; }}
    @media (prefers-color-scheme: dark) {{
      .bg {{ fill:#0d1117; }} .card {{ fill:#151b23; stroke:#30363d; stroke-width:1.5; }}
      .t-primary {{ fill:#e6edf3; }} .t-muted {{ fill:#9198a1; }} .t-faint {{ fill:#6e7681; }}
      .chipbg {{ fill:#1c2129; stroke:#30363d; stroke-width:1; }}
      .L0 {{ fill:#22272e; }} .L1 {{ fill:#033a16; }} .L2 {{ fill:#0e4429; }}
      .L3 {{ fill:#006d32; }} .L4 {{ fill:#26a641; }}
    }}
    .gridfx {{ opacity:1; animation: appear .8s cubic-bezier(.2,.7,.3,1) .15s backwards; }}
    .sweep {{ opacity:0; animation: sweep 1.3s cubic-bezier(.4,.1,.3,1) .3s forwards; }}
    @keyframes appear {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
    @keyframes sweep {{
      0% {{ opacity:.10; transform:translateX(0); }}
      92% {{ opacity:.10; transform:translateX({grid_w:.0f}px); }}
      100% {{ opacity:0; transform:translateX({grid_w:.0f}px); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .gridfx, .sweep {{ animation: none; }}
    }}
  </style>

  <rect class="bg" width="{W}" height="{H}"/>
  <rect class="card" x="8" y="8" width="1024" height="252" rx="14"/>

  <text class="t-primary" x="52" y="42" font-family="{MONO}" font-size="13.5" font-weight="700" letter-spacing="2.5">CONTRIBUTION ACTIVITY — LAST 12 MONTHS</text>
  <text class="t-faint" x="52" y="62" font-family="{MONO}" font-size="11.5">sourced live from the GitHub GraphQL API — no third-party stat cards</text>

  {header_chips}

  {weekday_tags}
  {month_labels}
  <g class="gridfx">
  {''.join(cells)}
  </g>
  <rect class="sweep" x="{GRID_X}" y="{GRID_Y}" width="3" height="102" rx="1.5" fill="#1f2328" opacity="0"/>

  <g font-family="{MONO}" font-size="11.5" font-weight="600">
    <text class="t-faint" x="52" y="250">generated {today.isoformat()} · auto-refreshed weekly</text>
    <text class="t-faint" x="988" y="250" text-anchor="end">github.com/{esc(user)}</text>
  </g>
</svg>
"""
    return svg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=DEFAULT_USER)
    args = ap.parse_args()

    out = os.path.abspath(OUT_PATH)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    data = fetch_calendar(args.user)
    stats = compute_stats(data["days"])
    log(f"stats: {stats}")

    svg = render(args.user, data, stats)

    fd, tmp = tempfile.mkstemp(suffix=".svg", dir=os.path.dirname(out))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(svg)
        xml.dom.minidom.parse(tmp)  # hard validation before touching the asset
        os.replace(tmp, out)       # atomic — a valid old asset can never be lost
        log(f"wrote {out} ({os.path.getsize(out)} bytes)")
    except Exception as e:
        if os.path.exists(tmp):
            os.unlink(tmp)
        log(f"ERROR: render/validation failed — {e!r}. Keeping existing asset.")
        sys.exit(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
