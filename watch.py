"""Check the ASX market-wide feed for trading policy lodgements newer than what data/policies.csv holds, and pull them in."""
import argparse
import csv
import sys
from datetime import date, timedelta

import scrape

DATA = scrape.DATA
STATE = DATA / "last_check.txt"


def recent_policies(since):
    """Every 'Trading Policy' lodgement across the market on or after `since` (ISO date), newest first."""
    page = 0
    while True:
        d = scrape.get(f"{scrape.API}/markets/announcements", page=page, itemsPerPage=200, announcementTypes="other").json()["data"]
        for a in d["items"]:
            if a["date"][:10] < since:
                return
            if "Trading Policy" in a["announcementTypes"]:
                yield a
        if not d["items"]:
            return
        page += 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", help="ISO date; defaults to the last run, else 30 days ago")
    p.add_argument("--all", action="store_true", help="report lodgements by companies outside the manifest too")
    p.add_argument("--dry-run", action="store_true", help="list without downloading")
    args = p.parse_args()
    since = args.since or (STATE.read_text().strip() if STATE.exists() else (date.today() - timedelta(days=30)).isoformat())
    manifest = {r["symbol"]: r for r in csv.DictReader(open(DATA / "policies.csv"))}
    new = {}
    for a in recent_policies(since):
        sym, d = a["symbol"], a["date"][:10]
        known = manifest.get(sym)
        if known is None and not args.all:
            continue
        if known and known["policy_date"] >= d:
            continue
        new.setdefault(sym, a)  # newest first, so first hit wins
    for sym, a in new.items():
        prev = manifest[sym]["policy_date"] if sym in manifest else "not tracked"
        print(f"{a['date'][:10]} {sym:6} {a['headline'][:60]:60} (had {prev})")
    if not args.dry_run:
        for sym, a in new.items():
            if sym in manifest:
                (DATA / "pdf" / f"{sym}.pdf").unlink(missing_ok=True)
                (DATA / "parsed" / f"{sym}.json").unlink(missing_ok=True)
        if new:
            sys.argv = ["scrape.py", "--symbols", *[s for s in new if s in manifest]]
            scrape.main()
        STATE.write_text(date.today().isoformat())
    print(f"{len(new)} new lodgement(s) since {since}", file=sys.stderr)


if __name__ == "__main__":
    main()
