# Structured dataset design (v2)

Six policies were read clause by clause (ORG, WTC, WBC, CBA, BHP, MQG). The flat v1 schema in `schema.py` loses the same things in every one of them. This is the proposed replacement.

## What v1 cannot represent

1. **Tiers.** Every policy has two to five overlapping person tiers (all staff; incentive plan participants; restricted persons; directors/KMP/PDMRs; associates) with different rules. One answer per topic forces a choice. CBA bans hedging vested shares for directors and Group Executives but not for EGMs; WBC directors need approval while other Prescribed Employees only notify.
2. **Security state.** The hedging line is not vested/unvested. All six use three states: unvested, vested-but-locked (holding lock or plan restriction), vested-unrestricted. Two also distinguish plan-sourced shares from on-market shares.
3. **Notification versus approval.** WBC and WTC let directors self-certify by notifying; MQG clears through a compliance system with no written step. `permitted_with_approval` overstates two of them.
4. **Express rule versus caught by definition.** Monetisation is never named. It is caught, if at all, by the definition of dealing ("agreement to dispose", "contract to secure a profit or avoid a loss by reference to price fluctuations"). BHP's derivatives ban is venue-limited ("on an exchange or in any other organised market"), so an OTC collar is outside the express ban but inside the dealing definition. A bank needs to know which.
5. **Clearance mechanics.** Validity (2 business days at ORG and BHP, 3 at CBA, 5 at WTC, unstated at MQG), revocability, conditions, response SLA, confidentiality of refusal, and post-trade notice all vary and all matter for execution.
6. **Tenor rules.** Short-term bans are variously an intention test (ORG, 3 months), a buy-sell window (WTC, 6 months), a LIFO holding period (CBA, 30 days), an instrument maturity test (BHP, one year or less, which catches a short-dated collar), or undefined (WBC, MQG).
7. **Floors rather than bans.** MQG allows hedging vested shares unless it takes the holding below the minimum shareholding requirement.
8. **Exceptional circumstances scope.** The hardship relief is drafted around a sale everywhere; none extends to entering a hedge.
9. **Incorporation by reference.** Key mechanics live in unpublished documents (WBC Key Prescribed Employee Trading Process, CBA Procedure and Conflicts Hub, MQG Personal Investments Policy).

## Proposed shape

Per-policy JSON stays the source of truth, but the body becomes a list of rules keyed by tier, topic and security state, plus structured clearance, windows and definitions. Flat tables are derived from it.

```python
Tier = {name, description, includes_associates: bool}

Rule = {
  topic: derivatives | hedging | monetisation | short_selling | stock_lending | cfd |
         margin_lending | encumbrance | short_term | insider_trading,
  tier: str,                              # Tier.name, or "all"
  security_state: unvested | vested_locked | vested_unrestricted | any,
  venue: exchange | otc | any,            # derivatives only
  answer: prohibited | permitted | permitted_with_clearance |
          permitted_with_notification | floor | not_addressed,
  mechanism: express | via_dealing_definition | via_hedging_definition | implied,
  floor: str,                             # e.g. "minimum shareholding requirement"
  section: str, detail: str, evidence: str,
}

Clearance = {
  tier: str,
  type: approval | notification | preclearance_system | none,
  approver: str, form: written | system | unspecified,
  validity_days: int | null, response_sla_days: int | null,
  revocable: bool | null, conditions_allowed: bool | null, refusal_confidential: bool | null,
  covers_derivatives: express | implied | not_addressed,
  post_trade: {to: str, deadline: str} | null,
  section: str, evidence: str,
}

Window = {kind: open | closed, applies_to: [tier], start_anchor: str, end_anchor: str,
          duration_days: int | null, discretionary_authority: str}

Definitions = {
  dealing_covers: {derivatives, agreements_to_deal, encumbrance, stock_lending,
                   change_of_beneficial_ownership, cash_settled},   # bools
  hedging_definition: str,        # verbatim, e.g. "any arrangement that limits economic risk"
  substance_over_form: bool,
  securities_include_otc_derivatives: bool,
}

ShortTermRule = {type: holding_period | buy_sell_window | intention | instrument_maturity | undefined,
                 months: float | null, basis: str, carve_outs: [str], tier: str}

Exception = {kind: hardship | court_order | plan_dealing | no_change_beneficial_interest |
                   non_discretionary_plan | secured_lender_sale | dividend_plan | takeover,
             scope: sale_only | any_dealing, approver: str, evidence: str}

Policy = {
  symbol, company, title,
  dates: {approved, effective, lodged, next_review},
  tiers: [Tier], definitions: Definitions, windows: [Window], ad_hoc_blackout_authority: str,
  rules: [Rule], clearance: [Clearance], short_term: [ShortTermRule], exceptions: [Exception],
  external_documents: [str], exemption_authority: str, jurisdiction_overlays: [str],
  collar: [{tier, status: available | clearance_required | notification_required |
                  blocked | blocked_below_floor | unclear, blockers: [str], conditions: [str]}],
}
```

### Derived tables

- `policies.csv`: one row per company (dates, window model, definition flags, associates, external docs, exemption authority).
- `rules.csv`: long format, one row per (symbol, tier, topic, security_state, venue). This is the table that answers "which companies block hedging vested shares for directors" or "where is the derivatives ban venue-limited".
- `clearance.csv`: one row per (symbol, tier).
- `windows.csv`: one row per window.
- `collar.csv`: one row per (symbol, tier) with the derived status.

`collar.status` should be computed by code from `rules` and `clearance`, not asked of the model, so it is auditable: blocked if any hedging or derivatives rule for that tier and `vested_unrestricted` is `prohibited` with `venue` in (otc, any); `blocked_below_floor` if the answer is `floor`; else `clearance_required` or `notification_required` from the tier's Clearance type; `unclear` if hedging is `not_addressed` and `dealing_covers.derivatives` is false.

## Extraction and QA

- One structured-output call per policy on `claude-opus-5` at high effort, with the six hand-read policies as a gold set. Compare the model's `rules` against the gold set on (tier, topic, security_state, answer) before running the remaining 449.
- Evidence quotes must appear in the source text. Check with a normalised substring match and flag any rule whose evidence does not, since that is the usual sign of an inferred rather than read answer.
- Tier names are free text in the policy; normalise to a small controlled vocabulary in a second, cheap pass (director, kmp, restricted, plan_participant, all_staff, associate) while keeping the policy's own label.
- Policies lodged in 2010 to 2012 (about 55 of 455) predate the hedging language now common. Expect more `not_addressed` and check the company website for a newer version before relying on them.

## Funding-leg fields (added after a second read of the six)

A funded collar (bank lends against the collared shares) is governed by five separate mechanisms that the v1 `margin_lending` and `encumbrance` findings blur together. Add to `Rule` a `topic` of `secured_financing` with `scope`, and these policy-level fields:

```python
Financing = {
  secured_financing_scope: margin_loan_only | any_secured_financing | any_financing_in_respect_of_securities | not_addressed,
  unvested_as_collateral: prohibited | not_addressed,
  transfer_into_margin_account_is_dealing: bool | null,
  forced_sale_in_closed_period: breach | excluded_dealing | clearance_required | not_addressed,
  margin_call_sale_needs_clearance: bool | null,
  price_trigger_guidance: str,                     # e.g. WBC steer to facilities without price triggers
  financing_disclosure: [{tier, trigger: inception | annual | financier_entitled_to_demand | threshold, to: str, deadline: str}],
  transfer_to_custodian_is_dealing: bool | null,   # change-of-beneficial-interest and off-market transfer rules
  stock_lending: prohibited | dealing | not_addressed,
  minimum_shareholding_requirement: {exists: bool, hedged_shares_excluded: bool | null, source: str},
}
```

Observed values: ORG any_financing_in_respect_of_securities, forced sale = breach; WTC margin_loan_only with approval and conditions, forced sale = excluded_dealing; WBC margin_loan_only permitted, forced sale = breach, price-trigger guidance, KPE disclosure; CBA any_secured_financing prohibited, stock lending prohibited, director off-market transfers not exempt; BHP any_secured_financing is a dealing needing clearance, unvested as collateral prohibited for PDMRs, stock lending is a dealing; MQG permitted with annual and event-driven KMP disclosure, margin-call liquidation needs pre-clearance, minimum shareholding floor.
