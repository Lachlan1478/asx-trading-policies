# ASX trading policies

Collects the securities trading policy of the largest ASX-listed companies and extracts the terms that matter for a director or executive entering an equity collar with a bank.

## How it works

1. `scrape.py` ranks ASX-listed companies by market cap from the ASX company directory (there is no official "ASX 500"; the top 500 approximates the All Ordinaries). For each company it finds the latest announcement ASX has typed **Trading Policy** (Listing Rule 12.9 requires every entity to lodge its policy and any changes), downloads the PDF and extracts the text. Companies with no lodgement (mostly foreign-exempt dual listings) fall back to a DuckDuckGo search for a policy PDF on the company website, then to `data/overrides.csv` (`symbol,url`) for anything you locate by hand.
2. `watch.py` reads the market-wide announcement feed for lodgements typed **Trading Policy** since the last run, and re-downloads any that are newer than the manifest copy (deleting the stale PDF and parsed JSON so `extract.py` redoes them). Run it weekly; lodgements run at a few per week across the whole market.
3. `extract.py` sends each policy to Claude with the JSON schema in `schema.py` (design in `DATASET.md`) and writes one JSON per company to `data/parsed/`, then builds the tables below. The same JSON can be produced by hand or by any other extractor; `extract.py --validate SYM` checks a file against the schema.

## Outputs

`report/findings.html` is a self-contained summary of the findings with charts; open it locally in a browser.

| File | One row per | Contents |
|---|---|---|
| `data/tables/policies.json` | company | Full nested extraction, including `bespoke_clauses` for anything the structured fields cannot hold |
| `data/tables/policies.csv` | company | Dates, tiers, window model, definition flags, financing scope, forced-sale treatment, disclosure triggers, funded-collar status, summary |

The `funded_collar` column is computed from the rules for the senior tiers (director, KMP, restricted persons): `blocked_hedge` when every senior tier is barred from hedging or OTC derivatives over vested unrestricted shares; `blocked_loan` when secured financing is banned in terms wider than margin loans; `loan_margin_features_banned` when only margin lending is banned, so the loan must avoid margin-call and LVR features; `enforcement_restricted` when a lender's forced sale in a closed period would be a breach; `clearance_required` when such a sale needs clearance; otherwise `workable`, meaning nothing in the policy blocks it, though clearance and window timing still apply (see `collar.csv`).
| `data/tables/rules.csv` | company x tier x topic x security state x venue | Answer (prohibited / permitted / with clearance / with notification / floor / not addressed), mechanism (express or via the dealing definition), section, verbatim evidence |
| `data/tables/clearance.csv` | company x tier | Approval vs notification vs system pre-clearance, approver, validity, SLA, revocability, post-trade notice |
| `data/tables/windows.csv` | window | Open or closed, anchors, duration, tiers |
| `data/tables/collar.csv` | company x tier | Rule-derived collar status (available, clearance required, notification required, blocked, blocked below floor, unclear) and funded-collar status, with blockers |
| `data/tables/bespoke.csv` | clause | Tagged collar-relevant clauses outside the schema, with why they matter |

| `data/tables/qa.csv` | issue | Cross-checks from `extract.py --qa`: schema validity, topic coverage, tier names used in rules but not declared, evidence quotes not found in the source text (expected for scanned PDFs), and parsed company name not matching the manifest (usually a rename, occasionally a reused ASX code) |

`data/skipped.txt` lists lodgements that turned out not to be a trading policy (date-change notices, cover letters pointing to a website, a responsible entity's staff policy) and other provenance notes. `data/parsed_v1/` holds the first-pass flat extractions of six policies under the earlier schema.

Provenance caveats worth knowing before relying on a row: the lodged copy can be years old (about 55 policies date from 2010 to 2012); some codes have been reused by a different company since lodgement (SKS resolves to an Energy Developments policy); renamed companies appear under their old name in the document; and listed trusts often lodge their responsible entity's staff policy rather than a director policy (QRI, KKC, MOT, OPH, GLF, MA1).

## Usage

```bash
uv sync
uv run python scrape.py -n 500                # data/pdf, data/text, data/policies.csv (the manifest)
export ANTHROPIC_API_KEY=...
uv run python extract.py                      # data/parsed/*.json, data/results.csv, data/results.json
uv run python extract.py --symbols CBA BHP    # subset
uv run python extract.py --report-only        # rebuild tables from existing JSON
uv run python extract.py --validate CBA BHP   # check hand-written or edited JSON
uv run python extract.py --qa                 # cross-checks -> data/tables/qa.csv
uv run python watch.py --dry-run --all        # list new lodgements since last run (all companies)
uv run python watch.py                        # pull in updates for tracked companies, then re-run extract.py
```

Both scripts are resumable: existing PDFs and parsed JSON are skipped. Extraction uses `claude-opus-5`; a full run over 455 policies costs roughly A$100-150 in API usage.

## Caveats

- Policies lodged before a company changed its name or code, or lodged only on the company website, are missed. `data/policies.csv` records a status per company so gaps are visible.
- PDFs where a third or more of the pages have no text layer (scanned policies, often behind a typed cover letter) are sent to the model as PDF instead of text, at roughly four times the token cost.
- DuckDuckGo rate-limits bursts; the fallback runs one query every five seconds and backs off on its challenge page, so a run with many misses is slow.
- The model answers only from the document; "not_addressed" means silence, not permission. Verify anything you rely on against the PDF in `data/pdf`.
