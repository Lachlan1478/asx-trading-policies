"""Extract collar-relevant terms from downloaded trading policies with Claude, validate, and build the tables."""
import argparse
import base64
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

from schema import Policy

DATA = Path(__file__).parent / "data"
MODEL = "claude-opus-5"
SYSTEM = """You are a securities lawyer reviewing an ASX-listed company's securities trading policy on behalf of a bank that wants to offer a director or executive a funded OTC equity collar (purchased put plus written call, with a loan secured against the collared shares) over their vested shareholding.

Extract the terms into the schema. Rules:
- Answer only from the document. Use not_addressed when the policy is silent; do not infer from general ASX practice.
- Record rules per tier and per security state wherever the policy distinguishes them. A single policy usually needs several rules per topic.
- mechanism is 'express' only when the policy names the activity; use 'via_dealing_definition' when it is caught only by the definition of dealing.
- Quote evidence verbatim and keep quotes short.
- Put anything collar-relevant that has no structured home into bespoke_clauses.
- If the document is a cover letter with the policy attached, use the attached policy."""


def scanned(pdf):
    """True when a third or more of the pages have no usable text layer."""
    with pymupdf.open(pdf) as doc:
        return sum(len(p.get_text().strip()) < 200 for p in doc) >= len(doc) / 3


def extract(symbol, text, pdf):
    import anthropic
    client = anthropic.Anthropic()
    content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(pdf.read_bytes()).decode()}},
        {"type": "text", "text": f"ASX code: {symbol}. Extract the policy terms."}] if scanned(pdf) else [
        {"type": "text", "text": f"ASX code: {symbol}\n\n<policy>\n{text}\n</policy>"}]
    r = client.beta.messages.create(
        model=MODEL, max_tokens=32000, system=SYSTEM,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": Policy.model_json_schema()}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": content}])
    if r.stop_reason == "refusal":
        raise RuntimeError(f"refused: {r.stop_details and r.stop_details.category}")
    return Policy.model_validate_json(next(b.text for b in r.content if b.type == "text")), r.usage


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


def collar_status(p, tier):
    """Rule-based collar feasibility for one tier, so the verdict is auditable rather than model opinion."""
    def rules(topic):
        return [r for r in p.rules if r.topic == topic and r.tier in (tier, "all") and r.security_state in ("vested_unrestricted", "any")]
    hedge, deriv = rules("hedging"), [r for r in rules("derivatives") if r.venue in ("otc", "any")]
    blockers = [f"{r.topic}: {r.evidence[:120]}" for r in hedge + deriv if r.answer == "prohibited"]
    if blockers:
        return "blocked", blockers
    if any(r.answer == "floor" for r in hedge):
        return "blocked_below_floor", [r.floor for r in hedge if r.answer == "floor"]
    if all(r.answer == "not_addressed" for r in hedge + deriv) and p.definitions.dealing_covers_derivatives != "yes":
        return "unclear", []
    rank = ["approval", "preclearance_system", "notification", "none", "not_addressed"]
    c = next((c for c in p.clearance if c.tier == tier), None) or min(p.clearance, key=lambda c: rank.index(c.type), default=None)
    return {"approval": "clearance_required", "preclearance_system": "clearance_required", "notification": "notification_required"}.get(c.type if c else "", "available"), []


def funded_status(p):
    f = p.financing
    if f.secured_financing_scope in ("any_secured_financing", "any_financing_in_respect_of_securities"):
        pro = [r for r in p.rules if r.topic in ("secured_financing", "margin_lending", "encumbrance") and r.answer == "prohibited"]
        if pro:
            return "blocked"
    return {"breach": "enforcement_restricted", "clearance_required": "clearance_required"}.get(f.forced_sale_in_closed_period, "workable")


def report(rows):
    tables = {k: [] for k in ("policies", "rules", "clearance", "windows", "collar", "bespoke")}
    full = {}
    for row in rows:
        path = DATA / "parsed" / f"{row['symbol']}.json"
        if not path.exists():
            continue
        p = Policy.model_validate_json(path.read_text())
        full[p.symbol] = json.loads(path.read_text())
        base = {"symbol": p.symbol, "company": row["name"], "market_cap": row["market_cap"], "industry": row["industry"], "lodged": row["policy_date"]}
        d, f = p.definitions, p.financing
        tables["policies"].append({**base, "title": p.title, "date_effective": p.date_effective, "tiers": " | ".join(t.name for t in p.tiers),
            "window_model": "open" if any(w.kind == "open" for w in p.windows) else "closed" if p.windows else "none",
            "ad_hoc_blackout_authority": p.ad_hoc_blackout_authority, **{k: getattr(d, k) for k in Definitions_fields},
            "secured_financing_scope": f.secured_financing_scope, "forced_sale_in_closed_period": f.forced_sale_in_closed_period,
            "unvested_as_collateral": f.unvested_as_collateral, "financing_disclosure": " | ".join(f.financing_disclosure),
            "minimum_shareholding_requirement": f.minimum_shareholding_requirement, "exemption_authority": p.exemption_authority,
            "external_documents": " | ".join(p.external_documents), "jurisdiction_overlays": " | ".join(p.jurisdiction_overlays),
            "funded_collar": funded_status(p), "summary": p.summary})
        tables["rules"] += [{**base, **r.model_dump()} for r in p.rules]
        tables["clearance"] += [{**base, **c.model_dump()} for c in p.clearance]
        tables["windows"] += [{**base, **w.model_dump(), "applies_to": " | ".join(w.applies_to)} for w in p.windows]
        tables["bespoke"] += [{**base, **b.model_dump()} for b in p.bespoke_clauses]
        for t in p.tiers:
            status, blockers = collar_status(p, t.name)
            tables["collar"].append({**base, "tier": t.name, "tier_kind": t.kind, "collar": status, "funded_collar": funded_status(p), "blockers": " | ".join(blockers)})
    for name, rows_ in tables.items():
        if rows_:
            with open(DATA / f"{name}.csv", "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=rows_[0].keys())
                w.writeheader()
                w.writerows(rows_)
    (DATA / "policies.json").write_text(json.dumps(full, indent=1))
    print(f"{len(full)} policies -> data/policies.json and data/{{{','.join(tables)}}}.csv", file=sys.stderr)


Definitions_fields = ["dealing_covers_derivatives", "dealing_covers_agreements_to_deal", "dealing_covers_encumbrance", "dealing_covers_stock_lending",
                      "dealing_covers_change_of_beneficial_ownership", "securities_include_otc_derivatives", "substance_over_form"]


def validate(symbols):
    ok = True
    for s in symbols:
        try:
            Policy.model_validate_json((DATA / "parsed" / f"{s}.json").read_text())
            print(f"{s} valid")
        except Exception as e:
            ok = False
            print(f"{s} INVALID: {str(e)[:1500]}")
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true", help="re-extract even if a parsed JSON exists")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--validate", nargs="+", metavar="SYM", help="validate data/parsed/SYM.json against the schema and exit")
    args = p.parse_args()
    if args.validate:
        validate(args.validate)
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
