"""
Hash Marks — Betting Lines Puller
------------------------------------------------------------
Pulls betting lines from CollegeFootballData.com for a given year/week.

Two output modes, both written every run:
  1. hash_marks_import_{year}_wk{week}.txt — paste into the Bulk Import box
     on the Board tab (manual workflow, works with any copy of the file).
  2. --out-json PATH — writes the same games as a JSON array in the exact
     shape Hash Marks' "Sync Latest Data" button expects. Used by the
     GitHub Actions workflow to update data/games.json automatically;
     harmless to ignore if you're just using the manual paste workflow.

USAGE
    pip install requests
    export CFBD_API_KEY="your key here"        # macOS/Linux
    setx CFBD_API_KEY "your key here"           # Windows (new terminal after)
    python cfbd_lines_puller.py --year 2026 --week 1
    python cfbd_lines_puller.py --year 2026 --week 1 --out-json ../data/games.json

By default it prefers DraftKings, then falls back to whatever else is
available per game (and tells you which book each line actually came
from). Pass --provider to force a specific book, or --list-providers to
just see what CFBD has for that week without writing anything.

CFBD's /lines entries also carry homeMoneyline/awayMoneyline alongside
spread and overUnder — this script pulls those from the same picked
provider so the spread, total, and moneyline in one output row are
always from the same book (mixing books per-market would be misleading).

Note: the /lines endpoint doesn't carry neutral-site or kickoff-time info
by itself (that data lives on /games), so this script fetches /games too
and joins the two by game id to get accurate neutral-site flags and start
times. Earlier versions of this script guessed neutral site from /lines
alone and were always wrong (defaulted to False) — this is the fix.
"""

import os
import sys
import json
import argparse
from collections import Counter

import requests

API_BASE = "https://api.collegefootballdata.com"

# Preference order when a game has lines from multiple books and you
# didn't force one with --provider. Add/reorder as you like.
PROVIDER_PREFERENCE = ["DraftKings", "FanDuel", "BetMGM", "ESPN Bet", "Bovada"]


def fetch_lines(year, week, season_type, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"year": year, "week": week, "seasonType": season_type}
    resp = requests.get(f"{API_BASE}/lines", headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_games(year, week, season_type, api_key):
    """Fetch /games for the same year/week — this is where neutralSite and
    startDate actually live. Returns a dict keyed by game id."""
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"year": year, "week": week, "seasonType": season_type, "classification": "fbs"}
    resp = requests.get(f"{API_BASE}/games", headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    by_id = {}
    for g in resp.json():
        by_id[g.get("id")] = {
            "neutralSite": g.get("neutralSite", False),
            "startDate": g.get("startDate"),
        }
    return by_id


def pick_line(game_lines, forced_provider=None):
    """Return the (provider, spread, overUnder, homeMoneyline, awayMoneyline)
    tuple to use for this game — all from the same book, so the numbers are
    internally consistent rather than a mix of the sharpest spread from one
    book and the sharpest total from another."""
    by_provider = {l["provider"]: l for l in game_lines if l.get("provider")}

    def extract(l):
        return (
            l.get("spread"),
            l.get("overUnder"),
            l.get("homeMoneyline"),
            l.get("awayMoneyline"),
        )

    if forced_provider:
        l = by_provider.get(forced_provider)
        if not l:
            return None
        return (forced_provider,) + extract(l)

    for pref in PROVIDER_PREFERENCE:
        if pref in by_provider:
            l = by_provider[pref]
            return (pref,) + extract(l)

    # nothing matched preference list — just take the first available
    if game_lines:
        l = game_lines[0]
        return (l.get("provider", "unknown"),) + extract(l)

    return None


def main():
    parser = argparse.ArgumentParser(description="Pull CFBD betting lines into Hash Marks import format")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--season-type", default="regular", choices=["regular", "postseason"])
    parser.add_argument("--provider", default=None, help="Force a specific book, e.g. FanDuel")
    parser.add_argument("--list-providers", action="store_true", help="Just print available books for this week and exit")
    parser.add_argument("--out-json", default=None, help="Also write games as JSON to this path, in the shape Hash Marks' Sync Latest Data expects")
    args = parser.parse_args()

    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        print("ERROR: set the CFBD_API_KEY environment variable first.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching lines for {args.year} week {args.week} ({args.season_type})...")
    games = fetch_lines(args.year, args.week, args.season_type, api_key)
    print(f"Got {len(games)} games with line data.")

    if not games:
        print("No games returned — check the year/week.")
        sys.exit(0)

    print("Fetching game info (kickoff times, neutral-site flags)...")
    game_info = fetch_games(args.year, args.week, args.season_type, api_key)
    matched = sum(1 for g in games if g.get("id") in game_info)
    print(f"Matched {matched}/{len(games)} games to kickoff/neutral-site info.")

    provider_counts = Counter()
    for g in games:
        for l in g.get("lines", []):
            if l.get("provider"):
                provider_counts[l["provider"]] += 1

    print("\nBooks found in this week's data:")
    for provider, count in provider_counts.most_common():
        print(f"  {provider}: {count} lines")

    for target in ("FanDuel", "BetMGM", "DraftKings"):
        status = "available" if target in provider_counts else "NOT in this week's data"
        print(f"  -> {target}: {status}")

    if args.list_providers:
        sys.exit(0)

    rows = []
    json_games = []
    skipped = 0
    ml_missing = 0
    for g in games:
        home = g.get("homeTeam")
        away = g.get("awayTeam")
        info = game_info.get(g.get("id"), {})
        neutral = info.get("neutralSite", False)
        start_date = info.get("startDate")
        lines = g.get("lines", [])

        picked = pick_line(lines, args.provider)
        if not picked or picked[1] is None:
            skipped += 1
            continue

        provider, spread, total, home_ml, away_ml = picked
        # CFBD's "spread" is already the home team's line (negative = home favored)
        total_str = f"{total}" if total is not None else ""
        neutral_str = "N" if neutral else ""
        time_str = start_date if start_date else ""
        home_ml_str = f"{home_ml}" if home_ml is not None else ""
        away_ml_str = f"{away_ml}" if away_ml is not None else ""
        if home_ml is None and away_ml is None:
            ml_missing += 1
        rows.append((provider, f"{args.week}, {away}, {home}, {spread}, {total_str}, {neutral_str}, {time_str}, {home_ml_str}, {away_ml_str}"))

        json_games.append({
            "week": args.week,
            "away": away,
            "home": home,
            "marketLine": spread,
            "marketTotal": total,
            "neutral": bool(neutral),
            "time": start_date,
            "homeML": home_ml,
            "awayML": away_ml,
        })

    print(f"\n{len(rows)} games with a usable line, {skipped} skipped (no line posted yet).")
    if rows:
        print(f"{len(rows) - ml_missing}/{len(rows)} games had moneyline data from their picked book.")

    out_path = f"hash_marks_import_{args.year}_wk{args.week}.txt"
    with open(out_path, "w") as f:
        for provider, line in rows:
            f.write(line + "\n")

    print(f"\nWrote {out_path} — paste its contents into Hash Marks' Bulk Import box.")
    print("(Each line also printed below with its source book for reference:)\n")
    for provider, line in rows:
        print(f"  [{provider}] {line}")

    if args.out_json:
        # Merge with whatever's already in the JSON file (e.g. other weeks
        # already synced) rather than clobbering it, matching the same
        # week+home+away identity the frontend uses to dedupe.
        existing = []
        if os.path.exists(args.out_json):
            try:
                with open(args.out_json) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []

        def key(g):
            return (g.get("week"), g.get("home"), g.get("away"))

        by_key = {key(g): g for g in existing}
        for jg in json_games:
            by_key[key(jg)] = jg

        merged = list(by_key.values())
        os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
        with open(args.out_json, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"\nWrote {len(merged)} total games to {args.out_json} ({len(json_games)} from this run).")


if __name__ == "__main__":
    main()
