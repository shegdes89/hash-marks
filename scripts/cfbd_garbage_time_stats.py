"""
Hash Marks — Garbage-Time-Excluded Team Efficiency Puller
------------------------------------------------------------
Pulls play-by-play from CollegeFootballData.com for every week from 1
through --through-week, strips out garbage-time snaps, and computes
SEASON-TO-DATE opponent-un-adjusted offensive & defensive EPA-per-play
(PPA) and success rate for every FBS team — overall, and split by rush
vs. pass plays.

USAGE
    pip install requests
    export CFBD_API_KEY="your key here"        # macOS/Linux
    setx CFBD_API_KEY "your key here"           # Windows (new terminal after)

    python cfbd_garbage_time_stats.py --year 2026 --through-week 3

    # Optional: also merge the result straight into your local repo's
    # data/team_stats.json (same folder layout as cfbd_lines_puller.py):
    python cfbd_garbage_time_stats.py --year 2026 --through-week 3 --out-json data/team_stats.json

Output: data/team_stats.json (or wherever --out-json points), plus a CSV
snapshot (team_efficiency_{year}_thru_wk{N}.csv) you can eyeball or upload
back into the chat if something looks off.

Notes:
  - Set CFBD_API_KEY as an environment variable rather than pasting it into
    this file.
  - Run this locally; the API blocks direct browser calls.
  - Garbage time definition below is a common score-margin-by-quarter
    heuristic, not official. Tune GARBAGE_TIME_THRESHOLDS if you want it
    stricter/looser.
  - Team names come straight from CFBD's own spelling (e.g. "Miami-FL").
    Hash Marks normalizes these against its own roster when you hit "Sync
    Latest Data" on the site, the same way it does for lines/games — any
    name that doesn't match gets reported rather than silently dropped.
"""

import os
import sys
import csv
import json
import argparse
from collections import defaultdict

import requests

API_BASE = "https://api.collegefootballdata.com"

# Garbage time heuristic: play is considered "garbage time" if the score
# margin (absolute value) exceeds the threshold for that period.
# Period 1 = never garbage time. Tune these to taste.
GARBAGE_TIME_THRESHOLDS = {
    1: 999,   # 1st quarter: never garbage time
    2: 38,    # 2nd quarter
    3: 28,    # 3rd quarter
    4: 22,    # 4th quarter (and OT below)
}


def is_garbage_time(period, offense_score, defense_score):
    if period is None:
        return False
    margin = abs((offense_score or 0) - (defense_score or 0))
    threshold = GARBAGE_TIME_THRESHOLDS.get(period, 16)  # OT/unknown periods: tight threshold
    return margin > threshold


def is_successful_play(down, distance, yards_gained):
    if down is None or distance is None or yards_gained is None:
        return False
    if distance <= 0:
        return False
    if down == 1:
        return yards_gained >= 0.5 * distance
    elif down == 2:
        return yards_gained >= 0.7 * distance
    else:  # 3rd or 4th down
        return yards_gained >= distance


RUSH_KEYWORDS = ("rush", "rushing")
PASS_KEYWORDS = ("pass", "sack", "interception")


def classify_rush_pass(play_type):
    """Return 'rush', 'pass', or None (special-teams/penalty/other plays we
    don't split — they still count in the overall off/def totals above)."""
    if not play_type:
        return None
    pt = play_type.lower()
    if any(k in pt for k in RUSH_KEYWORDS):
        return "rush"
    if any(k in pt for k in PASS_KEYWORDS):
        return "pass"
    return None


def fetch_plays(year, week, season_type, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"year": year, "week": week, "seasonType": season_type, "classification": "fbs"}
    resp = requests.get(f"{API_BASE}/plays", headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Pull season-to-date garbage-time-excluded EPA/success rate from CFBD")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--through-week", type=int, required=True, help="Aggregate weeks 1..N (inclusive)")
    parser.add_argument("--season-type", default="regular", choices=["regular", "postseason"])
    parser.add_argument("--out-json", default="data/team_stats.json", help="Path to write the merged JSON (default: data/team_stats.json)")
    args = parser.parse_args()

    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        print("ERROR: set the CFBD_API_KEY environment variable first.", file=sys.stderr)
        sys.exit(1)

    stats = defaultdict(lambda: {
        "off_plays": 0, "off_ppa_sum": 0.0, "off_success": 0,
        "def_plays": 0, "def_ppa_sum": 0.0, "def_success": 0,
        "off_rush_plays": 0, "off_rush_ppa_sum": 0.0, "off_rush_success": 0,
        "off_pass_plays": 0, "off_pass_ppa_sum": 0.0, "off_pass_success": 0,
        "def_rush_plays": 0, "def_rush_ppa_sum": 0.0, "def_rush_success": 0,
        "def_pass_plays": 0, "def_pass_ppa_sum": 0.0, "def_pass_success": 0,
    })

    total_excluded_garbage = 0
    total_excluded_no_ppa = 0
    total_plays_seen = 0

    for wk in range(1, args.through_week + 1):
        print(f"Fetching plays for {args.year} week {wk} ({args.season_type})...")
        try:
            plays = fetch_plays(args.year, wk, args.season_type, api_key)
        except requests.exceptions.HTTPError as e:
            print(f"  Skipping week {wk}: {e}")
            continue
        print(f"  Got {len(plays)} plays.")
        total_plays_seen += len(plays)

        for p in plays:
            period = p.get("period")
            off_score = p.get("offenseScore")
            def_score = p.get("defenseScore")

            if is_garbage_time(period, off_score, def_score):
                total_excluded_garbage += 1
                continue

            ppa = p.get("ppa")
            if ppa is None:
                total_excluded_no_ppa += 1
                continue

            offense = p.get("offense")
            defense = p.get("defense")
            down = p.get("down")
            distance = p.get("distance")
            yards_gained = p.get("yardsGained")
            success = is_successful_play(down, distance, yards_gained)
            rush_or_pass = classify_rush_pass(p.get("playType"))

            if offense:
                s = stats[offense]
                s["off_plays"] += 1
                s["off_ppa_sum"] += ppa
                s["off_success"] += 1 if success else 0
                if rush_or_pass == "rush":
                    s["off_rush_plays"] += 1
                    s["off_rush_ppa_sum"] += ppa
                    s["off_rush_success"] += 1 if success else 0
                elif rush_or_pass == "pass":
                    s["off_pass_plays"] += 1
                    s["off_pass_ppa_sum"] += ppa
                    s["off_pass_success"] += 1 if success else 0

            if defense:
                s = stats[defense]
                s["def_plays"] += 1
                s["def_ppa_sum"] += ppa
                s["def_success"] += 1 if success else 0
                if rush_or_pass == "rush":
                    s["def_rush_plays"] += 1
                    s["def_rush_ppa_sum"] += ppa
                    s["def_rush_success"] += 1 if success else 0
                elif rush_or_pass == "pass":
                    s["def_pass_plays"] += 1
                    s["def_pass_ppa_sum"] += ppa
                    s["def_pass_success"] += 1 if success else 0

    if total_plays_seen == 0:
        print("No plays returned across any week — check --year/--through-week.")
        sys.exit(0)

    print(f"\nTotal plays seen: {total_plays_seen}")
    print(f"Excluded {total_excluded_garbage} garbage-time plays, {total_excluded_no_ppa} plays with no PPA value.")

    def safe_div(n, d):
        return n / d if d else 0

    teams_out = {}
    for team, s in sorted(stats.items()):
        teams_out[team] = {
            "offPlays": s["off_plays"],
            "offPpa": round(safe_div(s["off_ppa_sum"], s["off_plays"]), 4),
            "offSuccessRate": round(safe_div(s["off_success"], s["off_plays"]), 4),
            "defPlays": s["def_plays"],
            "defPpa": round(safe_div(s["def_ppa_sum"], s["def_plays"]), 4),
            "defSuccessRate": round(safe_div(s["def_success"], s["def_plays"]), 4),

            "offRushPlays": s["off_rush_plays"],
            "offRushPpa": round(safe_div(s["off_rush_ppa_sum"], s["off_rush_plays"]), 4),
            "offRushSuccessRate": round(safe_div(s["off_rush_success"], s["off_rush_plays"]), 4),
            "offPassPlays": s["off_pass_plays"],
            "offPassPpa": round(safe_div(s["off_pass_ppa_sum"], s["off_pass_plays"]), 4),
            "offPassSuccessRate": round(safe_div(s["off_pass_success"], s["off_pass_plays"]), 4),

            "defRushPlays": s["def_rush_plays"],
            "defRushPpa": round(safe_div(s["def_rush_ppa_sum"], s["def_rush_plays"]), 4),
            "defRushSuccessRate": round(safe_div(s["def_rush_success"], s["def_rush_plays"]), 4),
            "defPassPlays": s["def_pass_plays"],
            "defPassPpa": round(safe_div(s["def_pass_ppa_sum"], s["def_pass_plays"]), 4),
            "defPassSuccessRate": round(safe_div(s["def_pass_success"], s["def_pass_plays"]), 4),
        }

    payload = {
        "year": args.year,
        "asOfWeek": args.through_week,
        "teams": teams_out,
    }

    out_dir = os.path.dirname(args.out_json)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out_json, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\nWrote {args.out_json} ({len(teams_out)} teams, season-to-date through week {args.through_week}).")

    csv_path = f"team_efficiency_{args.year}_thru_wk{args.through_week}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "team", "off_plays", "off_ppa_per_play", "off_success_rate",
            "def_plays", "def_ppa_per_play", "def_success_rate",
            "off_rush_ppa", "off_rush_sr", "off_pass_ppa", "off_pass_sr",
            "def_rush_ppa", "def_rush_sr", "def_pass_ppa", "def_pass_sr",
        ])
        for team, s in teams_out.items():
            writer.writerow([
                team, s["offPlays"], s["offPpa"], s["offSuccessRate"],
                s["defPlays"], s["defPpa"], s["defSuccessRate"],
                s["offRushPpa"], s["offRushSuccessRate"], s["offPassPpa"], s["offPassSuccessRate"],
                s["defRushPpa"], s["defRushSuccessRate"], s["defPassPpa"], s["defPassSuccessRate"],
            ])
    print(f"Wrote {csv_path} (snapshot copy, not used by the site).")


if __name__ == "__main__":
    main()
