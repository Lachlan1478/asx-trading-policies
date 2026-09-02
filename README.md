# ASX trading policies

Collects the securities trading policy of the largest ASX-listed companies and extracts the terms that matter for a director or executive entering an equity collar with a bank.

## How it works

1. `scrape.py` ranks ASX-listed companies by market cap from the ASX company directory (there is no official "ASX 500"; the top 500 approximates the All Ordinaries). For each company it finds the latest announcement ASX has typed **Trading Policy** (Listing Rule 12.9 requires every entity to lodge its policy and any changes), downloads the PDF and extracts the text. Companies with no lodgement (mostly foreign-exempt dual listings) fall back to a DuckDuckGo search for a policy PDF on the company website, then to `data/overrides.csv` (`symbol,url`) for anything you locate by hand.
2. `watch.py` reads the market-wide announcement feed for lodgements typed **Trading Policy** since the last run, and re-downloads any that are newer than the manifest copy (deleting the stale PDF and parsed JSON so `extract.py` redoes them). Run it weekly; lodgements run at a few per week across the whole market.
3. `extract.py` sends each policy to Claude with a JSON schema (`schema.py`) and writes one JSON per company, then flattens everything into `data/results.csv`.

Extracted terms: covered persons, trading-window model, open windows, closed periods, ad hoc blackouts, derivatives, hedging of unvested and vested holdings, monetisation, short selling, margin lending, encumbrance, short-term trading, minimum holding period, prior approval (required, written, approver, validity, post-trade notification), exceptional-circumstances relief, explicit collar mention, other collar-relevant clauses, and a short collar assessment. Each finding carries a verbatim evidence quote in the JSON.

## Usage

```bash
uv sync
uv run python scrape.py -n 500                # data/pdf, data/text, data/policies.csv
export ANTHROPIC_API_KEY=...
uv run python extract.py                      # data/parsed/*.json, data/results.csv, data/results.json
uv run python extract.py --symbols CBA BHP    # subset
uv run python extract.py --report-only        # rebuild CSV from existing JSON
uv run python watch.py --dry-run --all        # list new lodgements since last run (all companies)
uv run python watch.py                        # pull in updates for tracked companies, then re-run extract.py
```

Both scripts are resumable: existing PDFs and parsed JSON are skipped. Extraction uses `claude-opus-5`; a full run over 500 policies costs roughly A$50-100 in API usage.

## Caveats

- Policies lodged before a company changed its name or code, or lodged only on the company website, are missed. `data/policies.csv` records a status per company so gaps are visible.
- PDFs where a third or more of the pages have no text layer (scanned policies, often behind a typed cover letter) are sent to the model as PDF instead of text, at roughly four times the token cost.
- DuckDuckGo rate-limits bursts; the fallback runs one query every five seconds and backs off on its challenge page, so a run with many misses is slow.
- The model answers only from the document; "not_addressed" means silence, not permission. Verify anything you rely on against the PDF in `data/pdf`.
