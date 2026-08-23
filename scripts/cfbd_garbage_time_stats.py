"""
Hash Marks — Garbage-Time-Excluded Team Efficiency Puller
------------------------------------------------------------
Pulls play-by-play from CollegeFootballData.com for a given year/week,
strips out garbage-time snaps, and computes opponent-un-adjusted
offensive & defensive EPA-per-play (PPA) and success rate for every team.

USAGE
    pip install requests
    export CFBD_API_KEY="your key here"        # macOS/Linux
    setx CFBD_API_KEY "your key here"           # Windows (new terminal after)
    python cfbd_garbage_time_stats.py --year 2026 --week 1

Output: a CSV named team_efficiency_{year}_wk{week}.csv you can upload
back into the chat to fold into Hash Marks.

Notes:
  - Set CFBD_API_KEY as an environment variable rather than pasting it into
    this file — keeps it out of anything you might later share.
  - Run this locally; the API blocks direct browser calls (that's why the
    tool itself can't do this), but a script on your machine works fine.
  - Garbage time definition below is a common score-margin-by-quarter
    heuristic, not official. Tune GARBAGE_TIME_THRESHOLDS if you want it
    stricter/looser.
"""

import os
import sys
import csv
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


def fetch_plays(year, week, season_type, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"year": year, "week": week, "seasonType": season_type, "classification": "fbs"}
    resp = requests.get(f"{API_BASE}/plays", headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Pull garbage-time-excluded EPA/success rate from CFBD")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--season-type", default="regular", choices=["regular", "postseason"])
    args = parser.parse_args()

    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        print("ERROR: set the CFBD_API_KEY environment variable first.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching plays for {args.year} week {args.week} ({args.season_type})...")
    plays = fetch_plays(args.year, args.week, args.season_type, api_key)
    print(f"Got {len(plays)} plays.")

    if not plays:
        print("No plays returned — check the year/week (bye weeks, future weeks, etc. return nothing).")
        sys.exit(0)

    # Sanity check: print one raw play so you can confirm field names match
    # what this script expects (CFBD's schema can shift between versions).
    print("\nSample play (verify field names below match what the script uses):")
    sample = plays[0]
    for k in ("offense", "defense", "period", "down", "distance", "yardsGained",
              "offenseScore", "defenseScore", "ppa", "playType"):
        print(f"  {k}: {sample.get(k)}")
    print()

    stats = defaultdict(lambda: {
        "off_plays": 0, "off_ppa_sum": 0.0, "off_success": 0,
        "def_plays": 0, "def_ppa_sum": 0.0, "def_success": 0,
    })

    excluded_garbage = 0
    excluded_no_ppa = 0

    for p in plays:
        period = p.get("period")
        off_score = p.get("offenseScore")
        def_score = p.get("defenseScore")

        if is_garbage_time(period, off_score, def_score):
            excluded_garbage += 1
            continue

        ppa = p.get("ppa")
        if ppa is None:
            excluded_no_ppa += 1
            continue

        offense = p.get("offense")
        defense = p.get("defense")
        down = p.get("down")
        distance = p.get("distance")
        yards_gained = p.get("yardsGained")
        success = is_successful_play(down, distance, yards_gained)

        if offense:
            s = stats[offense]
            s["off_plays"] += 1
            s["off_ppa_sum"] += ppa
            s["off_success"] += 1 if success else 0

        if defense:
            s = stats[defense]
            s["def_plays"] += 1
            s["def_ppa_sum"] += ppa
            s["def_success"] += 1 if success else 0

    print(f"Excluded {excluded_garbage} garbage-time plays, {excluded_no_ppa} plays with no PPA value.")

    out_path = f"team_efficiency_{args.year}_wk{args.week}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "team", "off_plays", "off_ppa_per_play", "off_success_rate",
            "def_plays", "def_ppa_per_play", "def_success_rate",
        ])
        for team, s in sorted(stats.items()):
            off_ppa = s["off_ppa_sum"] / s["off_plays"] if s["off_plays"] else 0
            off_sr = s["off_success"] / s["off_plays"] if s["off_plays"] else 0
            def_ppa = s["def_ppa_sum"] / s["def_plays"] if s["def_plays"] else 0
            def_sr = s["def_success"] / s["def_plays"] if s["def_plays"] else 0
            writer.writerow([
                team, s["off_plays"], round(off_ppa, 4), round(off_sr, 4),
                s["def_plays"], round(def_ppa, 4), round(def_sr, 4),
            ])

    print(f"\nWrote {out_path}")
    print("Upload this CSV in chat and I'll fold it into Hash Marks.")


if __name__ == "__main__":
    main()
