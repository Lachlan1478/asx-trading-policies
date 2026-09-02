"""Extract collar-relevant terms from downloaded trading policies with Claude and tabulate them."""
import argparse
import base64
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import pymupdf

from schema import PolicyTerms

DATA = Path(__file__).parent / "data"
MODEL = "claude-opus-5"
SYSTEM = """You are a securities lawyer reviewing an ASX-listed company's securities trading policy on behalf of a bank that wants to offer a director or executive an OTC equity collar (a purchased put plus a written call, possibly funded and possibly monetised) over their vested shareholding.

Extract the terms into the schema. Rules:
- Answer only from the document. Use "not_addressed" when the policy is silent; do not infer from general ASX practice.
- "permitted_with_approval" means the policy allows the dealing only with prior clearance or written consent.
- A collar is a hedge and usually a derivative. Treat clauses on "hedging", "limiting economic risk", "derivatives", "caps and collars", "financial products over securities", "equity swaps", "forward sales" and "monetisation" as directly relevant.
- Quote evidence verbatim, keeping quotes short (one to three sentences).
- If the document is a cover letter with the policy attached, use the attached policy."""
client = anthropic.Anthropic()


def scanned(pdf):
    """True when a third or more of the pages have no usable text layer (e.g. a typed cover letter with a scanned policy attached)."""
    with pymupdf.open(pdf) as doc:
        return sum(len(p.get_text().strip()) < 200 for p in doc) >= len(doc) / 3


def extract(symbol, text, pdf):
    content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(pdf.read_bytes()).decode()}},
        {"type": "text", "text": f"ASX code: {symbol}. Extract the policy terms."}] if scanned(pdf) else [
        {"type": "text", "text": f"ASX code: {symbol}\n\n<policy>\n{text}\n</policy>"}]
    r = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": PolicyTerms.model_json_schema()}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": content}])
    if r.stop_reason == "refusal":
        raise RuntimeError(f"refused: {r.stop_details and r.stop_details.category}")
    return PolicyTerms.model_validate_json(next(b.text for b in r.content if b.type == "text")), r.usage


def process(row, force):
    sym = row["symbol"]
    out = DATA / "parsed" / f"{sym}.json"
    if out.exists() and not force:
        return
    try:
        terms, usage = extract(sym, (DATA / "text" / f"{sym}.txt").read_text(), DATA / "pdf" / f"{sym}.pdf")
        out.write_text(terms.model_dump_json(indent=1))
        print(f"{sym:6} ok  in={usage.input_tokens} out={usage.output_tokens}", file=sys.stderr)
    except Exception as e:
        print(f"{sym:6} error: {e}", file=sys.stderr)


def flatten(sym, row, t):
    """One CSV row per company: scalar answers plus joined windows; full detail stays in the JSON."""
    r = {"symbol": sym, "name": row["name"], "market_cap": row["market_cap"], "industry": row["industry"], "policy_date": row["policy_date"],
         "policy_title": t.policy_title, "covered_persons": t.covered_persons, "window_model": t.window_model,
         "trading_windows": " | ".join(f"{w.opens} -> {w.closes}" for w in t.trading_windows), "closed_periods": t.closed_periods,
         "ad_hoc_blackouts": t.ad_hoc_blackouts}
    for f in ("derivatives", "hedging_unvested", "hedging_vested", "monetisation", "short_selling", "margin_lending", "encumbrance", "short_term_trading", "exceptional_circumstances"):
        r[f] = getattr(t, f).answer
        r[f + "_detail"] = getattr(t, f).detail
    a = t.approval
    r.update(minimum_holding_period=t.minimum_holding_period, approval_required=a.required, approval_written=a.must_be_written, approver=a.approver,
             approval_validity=a.validity, post_trade_notification=a.post_trade_notification, explicit_collar_mention=t.explicit_collar_mention,
             other_collar_relevant_clauses=" | ".join(t.other_collar_relevant_clauses), collar_assessment=t.collar_assessment)
    return r


def report(rows):
    out, full = [], {}
    for row in rows:
        p = DATA / "parsed" / f"{row['symbol']}.json"
        if p.exists():
            t = PolicyTerms.model_validate_json(p.read_text())
            out.append(flatten(row["symbol"], row, t))
            full[row["symbol"]] = json.loads(p.read_text())
    with open(DATA / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)
    (DATA / "results.json").write_text(json.dumps(full, indent=1))
    print(f"{len(out)} companies -> {DATA / 'results.csv'}, {DATA / 'results.json'}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true", help="re-extract even if a parsed JSON exists")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args()
    (DATA / "parsed").mkdir(exist_ok=True)
    rows = [r for r in csv.DictReader(open(DATA / "policies.csv")) if r["status"] == "ok"]
    if args.symbols:
        rows = [r for r in rows if r["symbol"] in args.symbols]
    if not args.report_only:
        with ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(lambda r: process(r, args.force), rows))
    report(rows)


if __name__ == "__main__":
    main()
