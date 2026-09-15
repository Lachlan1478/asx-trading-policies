"""Six permission questions per trading policy, for a covered employee's vested shares: extraction, validation and table."""
import argparse
import csv
import json
import sys
from pathlib import Path

from schema import Questions

DATA = Path(__file__).parent / "data"
OUT = DATA / "questions"
MODEL = "claude-opus-5"
QUESTIONS = {
    "cash_hedge": "Purchase a cash-settled hedge over vested shares (a cash-settled collar, put, swap or similar)",
    "physical_hedge": "Purchase a physically settled hedge over vested shares (a collar or put settled by delivering the shares)",
    "encumber": "Encumber vested shares (pledge, mortgage or grant a security interest over them)",
    "borrow_against_stock": "Borrow cash secured against vested shares (a margin loan or any loan secured over the shares)",
    "borrow_against_derivative": "Borrow cash secured against a derivative over vested shares (a loan secured on a collar or put rather than the shares)",
    "stock_loan": "Lend vested shares under a title-transfer securities loan",
    "lender_enforcement": "Have a lender enforce its security by selling the shares during a closed period (a margin call or default sale)",
}
MECHANISMS = {
    "express": "the policy names the activity, or a close synonym, in the clause",
    "via_definition": "the activity is caught only because a definition of dealing, securities or hedging sweeps it in",
    "none": "not mentioned and not caught",
}
ANSWERS = {
    "explicitly_permitted": "a clause allows the activity by name, with no approval or notice step; the mechanism must be express",
    "not_mentioned_implicitly_permitted": "no clause addresses the activity for this tier and no definition of dealing or securities sweeps it in, so the only constraint is the law; the mechanism must be none",
    "never_permitted": "prohibited outright, whether by name or because a definition catches it and the catch-all rule is a ban",
    "permitted_with_notification": "allowed if the employee tells the company, before or after",
    "permitted_with_pre_approval": "allowed only with clearance or written consent first, including where a general clearance regime catches it through the definition of dealing",
    "unclear": "the text is contradictory, or the definitions could reasonably be read either way",
}
SYSTEM = f"""You are a securities lawyer reading an ASX-listed company's securities trading policy for a bank that may finance or hedge an employee's shareholding.

Answer seven questions about what an employee may do with vested shares, twice: once for the general tier, meaning the widest group of employees the policy binds (often all employees or personnel), and once for the senior tier, meaning the most restrictive tier short of the board, such as key management personnel, restricted persons or designated employees; if directors and executives share a tier use it, and if the policy has a single tier use it for both and say so in tier_name. Vested shares means shares the employee owns outright with no plan holding lock still running.

The questions, in order:
{chr(10).join(f"- {k}: {v}" for k, v in QUESTIONS.items())}

The answers:
{chr(10).join(f"- {k}: {v}" for k, v in ANSWERS.items())}

The mechanism, recorded with every answer:
{chr(10).join(f"- {k}: {v}" for k, v in MECHANISMS.items())}

Then say whether the rules reach the employee's associates: spouse, family trust, controlled company or nominee, which is where a hedge or loan is usually written.

Rules of reading. Read the definitions first: an activity the policy never names can still be caught if dealing covers derivatives, agreements to deal, granting security or lending stock, or if securities includes derivatives; then the answer is whatever the policy says about dealing, the mechanism is via_definition, and the definition goes in definition. A hedging ban worded as limiting economic risk catches both cash and physically settled hedges. A physically settled hedge ends in a disposal of the shares, so a rule that governs only dealing or disposal catches the physical hedge but not the cash-settled one. A margin lending ban does not by itself ban other secured borrowing, and a rule about loans secured on the shares says nothing about a loan secured on a derivative unless it speaks of financing in respect of securities generally. A lender's forced sale is never_permitted when the policy makes it a breach by the employee, permitted_with_pre_approval when it needs clearance, and explicitly_permitted when the policy excludes it from dealing. A holding floor such as a minimum shareholding requirement is permitted_with_pre_approval with the floor stated in reasoning. Closed periods and windows do not change an answer; they govern timing. Do not infer from what a well-drafted policy would say, and never turn silence into explicit permission: when a tier is bound only by the insider trading prohibition and nothing addresses the activity, the answer is not_mentioned_implicitly_permitted with mechanism none. Quote clause verbatim from the text, one to three sentences. For a not_mentioned answer, quote the clause that shows what does bind the tier, such as the general prohibition or the scope paragraph, so a reader can see the silence; leave clause empty only when nothing at all applies. Return exactly one finding per question, in the order above, for each tier."""


def run(rows):
    import anthropic
    client = anthropic.Anthropic()
    for r in rows:
        sym, out = r["symbol"], OUT / f"{r['symbol']}.json"
        if out.exists():
            continue
        text = (DATA / "text" / f"{sym}.txt").read_text()
        resp = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                      output_config={"format": {"type": "json_schema", "schema": Questions.model_json_schema()}},
                                      messages=[{"role": "user", "content": f"ASX code: {sym}\n\n<policy>\n{text}\n</policy>"}])
        q = Questions.model_validate_json(next(b.text for b in resp.content if b.type == "text"))
        out.write_text(q.model_dump_json(indent=1))
        print(sym, "ok", file=sys.stderr)


def load(rows):
    """Validate every questions JSON and write data/tables/questions.csv."""
    ok, table = True, []
    for r in rows:
        f = OUT / f"{r['symbol']}.json"
        if not f.exists():
            continue
        try:
            q = Questions.model_validate_json(f.read_text())
            if [t.tier_kind for t in q.tiers] != ["general", "senior"]:
                raise ValueError("tiers must be general then senior")
            for t in q.tiers:
                if [x.question for x in t.findings] != list(QUESTIONS):
                    raise ValueError(f"{t.tier_kind}: findings must be one per question in order")
                for x in t.findings:
                    want = {"explicitly_permitted": {"express"}, "not_mentioned_implicitly_permitted": {"none"}}.get(x.answer, {"express", "via_definition"})
                    if x.answer != "unclear" and x.mechanism not in want:
                        raise ValueError(f"{t.tier_kind}.{x.question}: answer {x.answer} needs mechanism {' or '.join(sorted(want))}, not {x.mechanism}")
            text = " ".join((DATA / "text" / f"{r['symbol']}.txt").read_text().split())
            quotes = [(f"{t.tier_kind}.{x.question}", x.clause) for t in q.tiers for x in t.findings] + [("associates", q.associates.clause)]
            missing = [k for k, c in quotes if c and " ".join(c.split()) not in text]
            if missing:
                print(f"{r['symbol']}: clause not verbatim for {', '.join(missing)}", file=sys.stderr)
        except Exception as e:
            ok = False
            print(f"{r['symbol']}: {e}", file=sys.stderr)
            continue
        for t in q.tiers:
            for x in t.findings:
                table.append({"symbol": q.symbol, "company": q.company, "market_cap": r["market_cap"], "policy_date": r["policy_date"],
                              "tier_kind": t.tier_kind, "tier_name": t.tier_name, "associates": q.associates.answer, **x.model_dump()})
    with open(DATA / "tables" / "questions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]) if table else ["symbol"])
        w.writeheader()
        w.writerows(table)
    print(f"{len(table) // (2 * len(QUESTIONS))} policies, {len(table)} findings", file=sys.stderr)
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["run", "load"])
    p.add_argument("--symbols", nargs="*")
    a = p.parse_args()
    OUT.mkdir(exist_ok=True)
    rows = [r for r in csv.DictReader(open(DATA / "policies.csv")) if r["status"] == "ok"]
    if a.symbols:
        rows = [r for r in rows if r["symbol"] in a.symbols]
    sys.exit(0 if (run if a.command == "run" else load)(rows) is not False else 1)


if __name__ == "__main__":
    main()
