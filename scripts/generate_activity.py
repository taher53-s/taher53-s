#!/usr/bin/env python3
"""
generate_activity.py — generative contribution visualization for the profile.

Fetches the last 12 months of public contribution data for the profile owner
via the GitHub GraphQL API and renders a self-contained, dual-mode (light/dark)
animated SVG at assets/activity.svg.

Design: a full-bleed data composition — accent-scaled contribution cells that
reveal sequentially, a weekly activity pulse line drawn from real data with a
peak marker, and computed statistics. No third-party stat-card services.

Engineering goals
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

# Signature vermilion scale — the profile's single accent.
SCALE_LIGHT = ["#EFECE8", "#F5C6B5", "#EE9E82", "#E56A45", "#D9482B"]
SCALE_DARK = ["#1A1E24", "#542F22", "#8A4630", "#C25E3E", "#FF8A66"]
LEVEL_FRAC = [0, 1, 3, 6]  # min contributions for levels 1..3 (4 = above)

MONO = "ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

W, H = 1040, 376
CELL, GAP = 14, 3.2
GRID_X, GRID_Y = 52, 208
SPARK_X0, SPARK_X1 = 52, 942
SPARK_TOP, SPARK_BOTTOM = 132, 176
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
    today = dt.date.today()
    step = CELL + GAP
    grid_w = 52 * step - GAP

    # ── grid cells + month labels ────────────────────────────────────────
    cells, month_labels = [], []
    last_label_x, last_m = -10_000, None
    weeks = [days[i * 7:(i + 1) * 7] for i in range((len(days) + 6) // 7)]
    for wi, week in enumerate(weeks):
        x = GRID_X + wi * step
        col_delay = 0.15 + wi * 0.016  # sequential reveal, left → right
        seen_month = None
        for di, (d, c) in enumerate(week):
            y = GRID_Y + di * step
            cells.append(
                f'<rect class="cell L{level(c)}" style="animation-delay:{col_delay:.2f}s" '
                f'x="{x:.1f}" y="{y:.1f}" width="{CELL}" height="{CELL}" rx="3">'
                f'<title>{d.isoformat()} · {c} contribution{"s" if c != 1 else ""}</title></rect>')
            if d.day <= 7:
                seen_month = (d.month, d.year)
        if seen_month and seen_month != last_m and x - last_label_x >= 58:
            month_labels.append(
                f'<text class="t-micro" x="{x:.1f}" y="{GRID_Y - 12}" '
                f'font-family="{MONO}" font-size="10.5" font-weight="600">'
                f'{MONTH_NAMES[seen_month[0] - 1]}</text>')
            last_label_x, last_m = x, seen_month

    weekday_tags = "".join(
        f'<text class="t-micro" x="{GRID_X - 12}" y="{GRID_Y + 10 + row * step}" '
        f'text-anchor="end" font-family="{MONO}" font-size="10.5">'
        f'{label}</text>'
        for row, label in ((0, "Mon"), (2, "Wed"), (4, "Fri"))
    )

    # ── weekly pulse line (real data only) ──────────────────────────────
    weekly = [sum(c for _, c in w) for w in weeks]
    while len(weekly) < 52:
        weekly.append(0)
    wmax = max(weekly)
    n = len(weekly)
    px = lambda i: SPARK_X0 + i * (SPARK_X1 - SPARK_X0) / max(n - 1, 1)
    py = lambda v: (SPARK_BOTTOM if wmax == 0
                    else SPARK_BOTTOM - (v / wmax) * (SPARK_BOTTOM - SPARK_TOP))
    points = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(weekly))
    area = (f"M {SPARK_X0},{SPARK_BOTTOM} L " +
            " L ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(weekly)) +
            f" L {px(n - 1):.1f},{SPARK_BOTTOM} Z")
    spark_peak = ""
    if wmax > 0:
        pi = weekly.index(wmax)
        # find the date of the peak week (its most recent day)
        peak_date = weeks[pi][-1][0] if pi < len(weeks) else today
        peak_x, peak_y = px(pi), py(wmax)
        label_y = max(peak_y - 14, 118)
        label_x = min(max(peak_x, 110), 930)
        spark_peak = (
            f'<circle class="fade peakdot" cx="{peak_x:.1f}" cy="{peak_y:.1f}" r="3.2"/>'
            f'<text class="fade t-micro" style="animation-delay:1.5s" x="{label_x:.1f}" '
            f'y="{label_y:.0f}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="10" font-weight="600" letter-spacing="1">peak · {wmax} · '
            f'{MONTH_NAMES[peak_date.month - 1]} {peak_date.day}</text>')

    # ── stat chips ───────────────────────────────────────────────────────
    chips, x = [], 52
    for value, label in ((f"{stats['total']}", "contributions"),
                         (f"{stats['active_days']}", "active days"),
                         (f"{stats['longest_streak']}d", "longest streak"),
                         (f"{stats['busiest_month']}", "busiest month")):
        text = f"{value} {label}"
        w = 7.4 * len(text) + 28
        chips.append(
            f'<g class="fade" style="animation-delay:1.25s"><rect x="{x:.0f}" y="82" '
            f'width="{w:.0f}" height="28" rx="14" class="chip"/>'
            f'<text class="t-primary" x="{x + w / 2:.0f}" y="100" text-anchor="middle" '
            f'font-family="{MONO}" font-size="12.5" font-weight="700">{esc(value)} '
            f'<tspan class="t-micro" font-weight="600">{esc(label)}</tspan></text></g>')
        x += w + 10

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="actTitle actDesc" font-family="{SANS}">
  <title id="actTitle">Contribution activity — {esc(user)}, last 12 months</title>
  <desc id="actDesc">Custom-generated contribution calendar: {stats['total']} contributions across {stats['active_days']} active days; longest streak {stats['longest_streak']} days; busiest month {stats['busiest_month']}; weekly pulse peaking at {wmax}.</desc>

  <style>
    .bg {{ fill:#ffffff; }}
    .t-primary {{ fill:#1F2328; }} .t-micro {{ fill:#8A93A0; }}
    .accent {{ fill:#D9482B; }}
    .chip {{ fill:#F5F3F0; stroke:#E4E2DE; stroke-width:1; }}
    .hairline {{ stroke:#1F2328; stroke-opacity:.10; stroke-width:1; }}
    .spark {{ stroke:#D9482B; stroke-width:1.75; fill:none; }}
    .sparkarea {{ fill:#D9482B; fill-opacity:.06; }}
    .peakdot {{ fill:#D9482B; animation: rise .5s ease 1.35s backwards; }}
    .L0 {{ fill:#EFECE8; }} .L1 {{ fill:#F5C6B5; }} .L2 {{ fill:#EE9E82; }}
    .L3 {{ fill:#E56A45; }} .L4 {{ fill:#D9482B; }}
    @media (prefers-color-scheme: dark) {{
      .bg {{ fill:#0D1117; }}
      .t-primary {{ fill:#E8EDF2; }} .t-micro {{ fill:#6E7681; }}
      .accent {{ fill:#FF8A66; }}
      .chip {{ fill:#161B22; stroke:#262B33; stroke-width:1; }}
      .hairline {{ stroke:#E8EDF2; stroke-opacity:.10; }}
      .spark {{ stroke:#FF8A66; }}
      .sparkarea {{ fill:#FF8A66; fill-opacity:.07; }}
      .peakdot {{ fill:#FF8A66; }}
      .L0 {{ fill:#1A1E24; }} .L1 {{ fill:#542F22; }} .L2 {{ fill:#8A4630; }}
      .L3 {{ fill:#C25E3E; }} .L4 {{ fill:#FF8A66; }}
    }}
    .fade {{ opacity:1; animation: rise .5s ease backwards; }}
    .cell {{ opacity:1; animation: cellin .35s ease backwards; }}
    .draw {{ stroke-dasharray:100 100; stroke-dashoffset:0; animation: draw 1.2s cubic-bezier(.4,.1,.2,1) .7s backwards; }}
    @keyframes rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:translateY(0); }} }}
    @keyframes cellin {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
    @keyframes draw {{ from {{ stroke-dashoffset:100; }} to {{ stroke-dashoffset:0; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .fade, .cell, .draw, .peakdot {{ animation: none; }}
    }}
  </style>

  <rect class="bg" width="{W}" height="{H}"/>

  <text class="fade t-primary" style="animation-delay:.05s" x="52" y="44" font-family="{MONO}" font-size="14" font-weight="700" letter-spacing="2.5">CONTRIBUTION ACTIVITY — LAST 12 MONTHS</text>
  <text class="fade t-micro" style="animation-delay:.15s" x="52" y="66" font-family="{MONO}" font-size="11" font-weight="500" letter-spacing=".5">sourced live from the GitHub GraphQL API · no third-party stat cards</text>

  {''.join(chips)}

  <!-- weekly pulse — real data -->
  <path class="sparkarea fade" style="animation-delay:.9s" d="{area}"/>
  <path class="spark draw" pathLength="100" d="M {points}"/>
  {spark_peak}

  {weekday_tags}
  {month_labels}
  <g class="cellgroup">
  {''.join(cells)}
  </g>

  <g font-family="{MONO}" font-size="11" font-weight="500" letter-spacing=".5">
    <text class="fade t-micro" style="animation-delay:1.6s" x="52" y="358">generated {today.isoformat()} · auto-refreshed weekly</text>
    <text class="fade t-micro" style="animation-delay:1.6s" x="988" y="358" text-anchor="end">github.com/{esc(user)}</text>
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
