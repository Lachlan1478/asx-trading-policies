"""Find and download the latest ASX-lodged trading policy for the largest ASX companies."""
import argparse
import csv
import io
import json
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
import requests

API = "https://asx.api.cmfyapp.com/asx-research/1.0"
DIRECTORY = "https://asx.api.markitdigital.com/asx-research/1.0/companies/directory/file?access_token=83ff96335c2d45a094df02a206a39ff4"
HEADERS = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.asx.com.au", "Referer": "https://www.asx.com.au/"}
POLICY_RE = re.compile(r"(trading|dealing)\s+(in\s+)?(securities\s+|shares?\s+)?polic|share\s+trading|securities\s+trading|securities\s+dealing", re.I)
URL_RE = re.compile(r"(trading|dealing).{0,20}polic|polic.{0,20}(trading|dealing)|share.?trading|securities.?(trading|dealing)|insider.?trading", re.I)
DATA = Path(__file__).parent / "data"
session = requests.Session()
session.headers.update(HEADERS)
plain = requests.Session()
plain.headers["User-Agent"] = HEADERS["User-Agent"]
search_lock = threading.Lock()


def get(url, s=session, **params):
    for attempt in range(4):
        r = s.get(url, params=params, timeout=60)
        if r.status_code < 500 and r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(2 ** attempt)
    r.raise_for_status()


def companies(n):
    """Top n ASX-listed companies by market cap (there is no official ASX 500; this approximates the All Ordinaries)."""
    rows = list(csv.DictReader(io.StringIO(get(DIRECTORY).text)))
    rows = [r for r in rows if r["Market Cap"].strip().isdigit()]
    rows.sort(key=lambda r: -int(r["Market Cap"]))
    return [{"symbol": r["ASX code"], "name": r["Company name"], "market_cap": int(r["Market Cap"]), "industry": r["GICs industry group"]} for r in rows[:n]]


def entity_xid(symbol):
    items = get(f"{API}/search/predictive", searchText=symbol, useBondsLookup="true").json()["data"]["items"]
    return next((i["xidEntity"] for i in items if i["symbol"] == symbol), None)


def announcements(xid, kind):
    page = 0
    while True:
        d = get(f"{API}/markets/announcements", entityXids=xid, page=page, itemsPerPage=200, announcementTypes=kind).json()["data"]
        yield from d["items"]
        if (page + 1) * 200 >= d["count"] or not d["items"]:
            return
        page += 1


def find_policy(xid):
    """Latest announcement typed 'Trading Policy'; falls back to headline matching under company administration."""
    for a in announcements(xid, "other"):
        if "Trading Policy" in a["announcementTypes"]:
            return a
    for a in announcements(xid, "company administration"):
        if POLICY_RE.search(a["headline"]):
            return a
    return None


def web_policy(name):
    """First policy-looking PDF from a DuckDuckGo search of the company website; used when ASX holds no lodgement."""
    q = f'"{name.title().replace(" Limited", "").replace(" Ltd", "")}" trading policy filetype:pdf'
    with search_lock:  # DuckDuckGo blocks the ASX Origin header and parallel queries; 202 is its rate-limit challenge page
        for attempt in range(4):
            r = plain.get("https://html.duckduckgo.com/html/", params={"q": q}, timeout=60)
            if r.status_code == 200:
                break
            time.sleep(30 * (attempt + 1))
        html = r.text
        time.sleep(5)
    for m in re.finditer(r'uddg=([^"&]+)', html):
        url = urllib.parse.unquote(m.group(1))
        if URL_RE.search(url) and "asx.com.au" not in url and url.lower().endswith(".pdf"):
            return url
    return None


def pdf_text(path):
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def overrides():
    """Manual symbol,url pairs in data/overrides.csv for policies neither ASX nor the search finds."""
    f = DATA / "overrides.csv"
    return {r["symbol"]: r["url"] for r in csv.DictReader(open(f))} if f.exists() else {}


def process(c):
    sym = c["symbol"]
    out = {**c, "status": "", "source": "", "policy_date": "", "headline": "", "document_key": "", "pdf": "", "text_chars": 0}
    try:
        run(c, out)
    except Exception as e:
        out["status"] = f"error: {e}"
    print(f"{sym:6} {out['status']:24} {out['policy_date']} {out['headline']}", file=sys.stderr)
    return out


def run(c, out):
    sym = c["symbol"]
    xid = entity_xid(sym)
    a = find_policy(xid) if xid else None
    pdf = DATA / "pdf" / f"{sym}.pdf"
    if a:
        out.update(source="asx", policy_date=a["date"][:10], headline=a["headline"], document_key=a["documentKey"])
        url = f"{API}/file/{a['documentKey']}"
    else:
        url = overrides().get(sym) or (None if pdf.exists() else web_policy(c["name"]))
        if not url and not pdf.exists():
            out["status"] = "no_policy_found"
            return
        out.update(source=url or "cached", headline=(url or pdf.name).rsplit("/", 1)[-1])
    if not pdf.exists():
        pdf.write_bytes(get(url, session if a else plain).content)
    text = pdf_text(pdf)
    (DATA / "text" / f"{sym}.txt").write_text(text)
    out.update(status="ok", pdf=str(pdf), text_chars=len(text))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-n", type=int, default=500, help="number of companies by market cap")
    p.add_argument("--symbols", nargs="*", help="only these ASX codes")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    for d in ("pdf", "text"):
        (DATA / d).mkdir(parents=True, exist_ok=True)
    cs = companies(args.n)
    if args.symbols:
        cs = [c for c in cs if c["symbol"] in args.symbols] or [{"symbol": s, "name": s, "market_cap": 0, "industry": ""} for s in args.symbols]
    with ThreadPoolExecutor(args.workers) as ex:
        rows = list(ex.map(process, cs))
    manifest = DATA / "policies.csv"
    if args.symbols and manifest.exists():  # merge a partial run into the existing manifest
        old = {r["symbol"]: r for r in csv.DictReader(open(manifest))}
        old.update({r["symbol"]: r for r in rows})
        rows = list(old.values())
    with open(manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    ok = sum(r["status"] == "ok" for r in rows)
    print(f"{ok}/{len(rows)} policies downloaded -> {DATA / 'policies.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
