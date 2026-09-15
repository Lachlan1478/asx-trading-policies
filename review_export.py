"""Publish the six-question answers to the scrape-review dashboard: page images, located clauses, risk flags."""
import csv
import json
from pathlib import Path

import pymupdf

from questions import ANSWERS, DATA, MECHANISMS, OUT, QUESTIONS

TASK = Path(__file__).parent.parent / "scrape-review" / "tasks" / "asx-trading-policies"
DPI = 110
LABELS = {"cash_hedge": "Cash-settled hedge", "physical_hedge": "Physically settled hedge", "encumber": "Encumber the shares",
          "borrow_against_stock": "Borrow against the shares", "borrow_against_derivative": "Borrow against a derivative",
          "stock_loan": "Title-transfer stock loan", "lender_enforcement": "Lender sale in a closed period"}


def find(pages, quote):
    """Rects for a verbatim quote, falling back to its opening words when line breaks or hyphens defeat the full match."""
    q = " ".join(quote.split())
    for probe in (q, q[:80], q[:40]):
        if len(probe) < 20:
            break
        for i, page in enumerate(pages):
            rects = page.search_for(probe)
            if rects:
                return [(i, r) for r in rects]
    return []


def box(page, r):
    w, h = page.rect.width, page.rect.height
    return [round(r.x0 / w, 4), round(r.y0 / h, 4), round(r.x1 / w, 4), round(r.y1 / h, 4)]


def export(row, q, pages_dir):
    sym = row["symbol"]
    pdf = pymupdf.open(DATA / "pdf" / f"{sym}.pdf")
    pages = list(pdf)
    fields, located = [], {}
    a = q["associates"]
    fields.append({"id": "associates.answer", "label": "Rules reach associates", "value": a["answer"], "type": "enum",
                   "options": ["covered", "not_covered", "unclear"], "section": "Policy", "row": 0, "row_label": "Associates"})
    fields.append({"id": "associates.clause", "label": "Clause", "value": a["clause"] or None, "type": "quote", "section": "Policy", "row": 0})
    if a["clause"]:
        located["associates.clause"] = find(pages, a["clause"])
    fields.append({"id": "associates.reasoning", "label": "Reasoning", "value": a["reasoning"], "type": "note", "section": "Policy", "row": 0})
    for t in q["tiers"]:
        kind = t["tier_kind"]
        section = f"{'General' if kind == 'general' else 'Senior'} tier: {t['tier_name']}"
        for n, f in enumerate(t["findings"]):
            qid = f["question"]
            base = {"section": section, "row": n, "row_label": LABELS[qid]}
            fields.append({"id": f"{kind}.{qid}.answer", "label": "Answer", "value": f["answer"], "type": "enum", "options": list(ANSWERS), **base})
            fields.append({"id": f"{kind}.{qid}.mechanism", "label": "Mechanism", "value": f["mechanism"], "type": "enum", "options": list(MECHANISMS), **base})
            for col in ("clause", "definition"):
                fld = {"id": f"{kind}.{qid}.{col}", "label": col.capitalize(), "value": f[col] or None, "type": "quote", **base}
                if f[col]:
                    located[fld["id"]] = find(pages, f[col])
                fields.append(fld)
            fields.append({"id": f"{kind}.{qid}.reasoning", "label": "Reasoning", "value": f["reasoning"], "type": "note", **base})
    used = sorted({i for hits in located.values() for i, _ in hits}) or [0, 1][:len(pages)]
    images = []
    for i in used:
        png = pages_dir / f"{sym}-{i}.png"
        if not png.exists():
            pages[i].get_pixmap(dpi=DPI).save(png)
        images.append(png.name)
    for fld in fields:
        hits = located.get(fld["id"])
        if hits:
            fld["boxes"] = [[used.index(i), box(pages[i], r)] for i, r in hits]
            fld["page"], fld["bbox"] = fld["boxes"][0]
    flags = []
    unfound = [f["id"] for f in fields if f["type"] == "quote" and f["value"] and "bbox" not in f]
    if unfound:
        flags.append(f"{len(unfound)} quotes not found on the page")
    if sum(len(p.get_text()) for p in pages) < 300 * len(pages):
        flags.append("thin text layer (scanned)")
    unclear = sorted({LABELS[f["question"]] for t in q["tiers"] for f in t["findings"] if f["answer"] == "unclear"})
    if unclear:
        flags.append("unclear: " + ", ".join(unclear))
    if row["policy_date"] < "2018":
        flags.append(f"policy lodged {row['policy_date']}")
    src = f"https://asx.api.cmfyapp.com/asx-research/1.0/file/{row['document_key']}" if row["source"] == "asx" else row.get("url", "")
    return {"doc_id": sym, "title": f"{sym} trading policy lodged {row['policy_date']}", "subtitle": q["company"], "source_url": src,
            "pages": images, "fields": fields, "flags": flags, "strata": {"answers": sorted({f["answer"] for t in q["tiers"] for f in t["findings"]})}}


def main():
    pages_dir = TASK / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    rows = {r["symbol"]: r for r in csv.DictReader(open(DATA / "policies.csv")) if r["status"] == "ok"}
    docs = []
    for f in sorted(OUT.glob("*.json")):
        q = json.loads(f.read_text())
        if q["symbol"] in rows:
            docs.append(export(rows[q["symbol"]], q, pages_dir))
    docs.sort(key=lambda d: -float(rows[d["doc_id"]]["market_cap"] or 0))
    (TASK / "manifest.jsonl").write_text("".join(json.dumps(d) + "\n" for d in docs))
    (TASK / "task.json").write_text(json.dumps({"name": "asx-trading-policies", "title": "ASX trading policies: what an employee may do",
        "description": "Seven permission questions answered from each company's securities trading policy, for vested shares, once for the general employee tier and once for the senior tier, plus whether the rules reach associates. Each answer is a reading of the clause shown beneath it, so judge whether the clause supports the answer. Mechanism says how the policy reaches the activity: express when a clause names it, via definition when only a definition of dealing or securities sweeps it in, none when nothing addresses it."}, indent=1))
    print(f"{len(docs)} documents")


if __name__ == "__main__":
    main()
