# Profile Maintenance Manual

This profile is a **small system, not a document**. Three moving parts:

```
data/profile.yml          ← YOU edit this (status, projects, links)
assets/hero.svg           ← hand-drawn orbital hero (edit with care)
assets/project-map.svg    ← hand-drawn systems map (edit with care)
assets/activity.svg       ← GENERATED — never edit by hand
scripts/generate_activity.py  ← fetches real data, renders activity.svg
scripts/build_readme.py       ← renders the status table into README.md
scripts/validate.py           ← pre-flight checks (XML/YAML/links/secrets)
.github/workflows/profile-update.yml  ← automation
```

---

## How to change things

### Update "building / learning / exploring / open to"
Edit **`data/profile.yml`** → the `now:` section. Then run:

```bash
python3 scripts/build_readme.py
```

The status table inside `README.md` is re-rendered between the
`<!-- @BEGIN:now -->` / `<!-- @END:now -->` markers. **Never edit that
table directly** — it will be overwritten.

### Add / change a featured project
Edit the `featured:` list in `data/profile.yml` (fields: `name`, `tagline`,
`what`, `stack`, `live`, `source`, `private`). The featured section of the
README is hand-authored — copy an existing block, keep the same
`### ▸ Name — *tagline*` + blockquote + links format. Keep to 6 max.

### Change your bio / location / website
Those live on GitHub itself, not in this repo:

```bash
# one-time: the profile API needs the "user" scope
gh auth refresh -h github.com -s user

gh api -X PATCH user \
  -f bio="Full-stack product engineer · AI/ML student in Mumbai. I ship complete products — 3D web, AI-powered apps, big-data platforms, macOS utilities." \
  -f location="Mumbai, India" \
  -f blog="https://taher-portfolio-3d.vercel.app"
```

### Add a social link
Add it under `links:` in `data/profile.yml`, then mirror it in the
README `$ contact` section by hand. **Only add URLs you have verified.**

---

## Regenerating the activity card

```bash
GITHUB_TOKEN=$(gh auth token) python3 scripts/generate_activity.py
```

- Fetches the last 12 months of contributions via the GitHub GraphQL API.
- Renders `assets/activity.svg` — contribution grid, total, active days,
  longest streak, busiest month. Every number is computed from the API.
- **Fail-safe by design:** if the fetch, parse, or render fails, the
  script exits non-zero and the previous `activity.svg` is left untouched.
- Add `--user <login>` to render another account.

## Run all checks locally

```bash
pip install pyyaml
python3 scripts/build_readme.py
python3 scripts/validate.py
```

`validate.py` verifies: SVG/XML validity, YAML validity, README markers,
that referenced images exist, that all links are https, and scans the whole
repo for secret-looking strings (tokens, keys, passwords). It exits
non-zero if anything fails — run it before every commit.

---

## How the automation works

`.github/workflows/profile-update.yml` runs every **Monday 00:17 UTC** and
on demand (**Actions tab → Refresh profile activity → Run workflow**).

1. `generate_activity.py` re-fetches live contribution data and re-renders
   `assets/activity.svg` (uses the built-in `GITHUB_TOKEN` — no secrets
   configured anywhere).
2. `build_readme.py` re-renders the status table from `data/profile.yml`.
3. `validate.py` gates the run — a broken asset can never be committed.
4. The workflow **commits only if something actually changed**, as
   `chore(profile): refresh activity visualization [skip ci]`.

There is no `on: push` trigger, so the workflow's own commits cannot
re-trigger it — no recursion, no commit loops.

### If a scheduled run fails
- Open the **Actions tab** and read the log — it states exactly which step
  and why (network, API shape, validation).
- The previous `activity.svg` is always preserved; the profile never breaks.
- Run the workflow manually after the issue is fixed, or regenerate locally
  and commit.

---

## Design notes (why it looks like this)

- **"Orbital System Atlas" concept:** the profile reads as a designed atlas of
  one engineer's work — an orbital hero, a systems map of real products, and
  generative activity art. It echoes the flagship project (a drivable world of
  districts) rather than a terminal/console cliché.
- **One signature accent:** vermilion in light mode (`#D9482B`), coral in dark
  (`#FF8A66`) — carried across the hero, the systems map, the contribution cells
  and the activity pulse line. Green is reserved strictly for "live" semantics.
- **Dual-mode as two art directions:** dark is deep and cinematic, light is
  editorial and clean — both share the same geometry, type and accent.
- **Motion that settles:** every animation is a one-time reveal (draw-in,
  staggered entrances, one-time pings). The only continuous motion is an
  ultra-slow particle drift in the hero (50–84s cycles). `prefers-reduced-motion`
  disables all of it — every element's base state is its final state.
- **No third-party stat-card services:** everything renders from raw SVG in
  this repo. The profile can never be broken by an external badge API.
- **README chapters are numbered (01–07); project entries are unnumbered to
  keep a single numbering system.** GitHub's H2 rule doubles as section
  dividers.
