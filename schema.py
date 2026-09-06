"""Pydantic schema (v2) for the terms extracted from a securities trading policy. See DATASET.md."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Topic = Literal["derivatives", "hedging", "monetisation", "short_selling", "stock_lending", "cfd", "margin_lending", "encumbrance", "secured_financing", "short_term"]
SecurityState = Literal["unvested", "vested_locked", "vested_unrestricted", "any"]
Answer = Literal["prohibited", "permitted", "permitted_with_clearance", "permitted_with_notification", "floor", "not_addressed"]
YesNo = Literal["yes", "no", "not_addressed"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tier(Strict):
    name: str = Field(description="The policy's own label, e.g. 'Restricted Persons', 'PDMRs', 'all employees'.")
    kind: Literal["director", "kmp", "restricted", "plan_participant", "all_staff", "associate", "other"]
    description: str
    includes_associates: YesNo = Field(description="Whether the policy extends this tier's rules to spouses, dependants, controlled entities or trusts.")


class Definitions(Strict):
    dealing_covers_derivatives: YesNo
    dealing_covers_agreements_to_deal: YesNo
    dealing_covers_encumbrance: YesNo = Field(description="Granting security, a charge, lien or pledge is itself a dealing.")
    dealing_covers_stock_lending: YesNo
    dealing_covers_change_of_beneficial_ownership: YesNo
    securities_include_otc_derivatives: YesNo
    hedging_definition: str = Field(description="Verbatim definition of hedging or 'limiting economic risk', or empty.")
    substance_over_form: YesNo


class Window(Strict):
    kind: Literal["open", "closed"]
    applies_to: list[str] = Field(description="Tier names, or ['all'].")
    start_anchor: str = Field(description="e.g. '1 July', 'close of trading 30 June', 'day after release of full-year results'.")
    end_anchor: str
    duration_days: int | None = Field(description="Fixed length in days if the policy states one.")


class Rule(Strict):
    topic: Topic
    tier: str = Field(description="Tier name, or 'all'.")
    security_state: SecurityState
    venue: Literal["exchange", "otc", "any"] = Field(description="Derivatives only; 'any' otherwise.")
    answer: Answer
    mechanism: Literal["express", "via_dealing_definition", "via_hedging_definition", "implied", "none"] = Field(
        description="'express' when the policy names the activity; 'via_dealing_definition' when it is caught only because the definition of dealing sweeps it in.")
    floor: str = Field(description="For answer 'floor': what the holding must not drop below, e.g. 'minimum shareholding requirement'. Else empty.")
    section: str
    detail: str
    evidence: str = Field(description="Verbatim quote, one to three sentences. Empty only when not_addressed.")


class Clearance(Strict):
    tier: str
    type: Literal["approval", "notification", "preclearance_system", "none", "not_addressed"]
    approver: str
    form: Literal["written", "system", "unspecified"]
    validity_days: int | None = Field(description="Business days the clearance remains valid, if stated.")
    response_sla_days: int | None
    revocable: YesNo
    conditions_allowed: YesNo
    refusal_confidential: YesNo
    covers_derivatives: Literal["express", "implied", "not_addressed"]
    post_trade_to: str = Field(description="Who must be told after dealing, or empty.")
    post_trade_deadline: str
    section: str
    evidence: str


class ShortTermRule(Strict):
    tier: str
    type: Literal["holding_period", "buy_sell_window", "intention", "instrument_maturity", "undefined", "not_addressed"]
    months: float | None
    basis: str = Field(description="e.g. 'LIFO', 'from acquisition', or empty.")
    carve_outs: list[str]
    evidence: str


class Exception_(Strict):
    kind: Literal["hardship", "court_order", "plan_dealing", "no_change_beneficial_interest", "non_discretionary_plan", "secured_lender_sale", "dividend_plan", "takeover", "other"]
    scope: Literal["sale_only", "any_dealing", "specific_dealing", "acquisition_only", "unclear"]
    approver: str
    evidence: str


class Financing(Strict):
    secured_financing_scope: Literal["margin_loan_only", "any_secured_financing", "any_financing_in_respect_of_securities", "not_addressed"] = Field(
        description="How widely the policy's financing rules reach, whether by ban or by clearance. Whether financing is banned is recorded in the rules, not here.")
    unvested_as_collateral: Literal["prohibited", "not_addressed"]
    transfer_into_margin_account_is_dealing: YesNo
    forced_sale_in_closed_period: Literal["breach", "excluded_dealing", "clearance_required", "not_addressed"]
    margin_call_sale_needs_clearance: YesNo
    price_trigger_guidance: str
    financing_disclosure: list[str] = Field(description="Each entry: tier, trigger (inception / annual / financier entitled to demand / threshold), to whom, deadline.")
    transfer_to_custodian_is_dealing: YesNo
    minimum_shareholding_requirement: str = Field(description="Whether an MSR is referenced and whether hedged shares are excluded, or empty.")


class BespokeClause(Strict):
    topic: str = Field(description="Short tag, e.g. 'forced sale', 'MAR overlay', 'exemption authority', 'ETF lookthrough'.")
    clause: str = Field(description="Verbatim or closely paraphrased clause.")
    why_it_matters: str = Field(description="One sentence on the effect on a funded collar with a bank.")


class Policy(Strict):
    symbol: str
    company: str
    title: str
    date_approved: str
    date_effective: str
    date_lodged: str
    date_next_review: str
    tiers: list[Tier]
    definitions: Definitions
    windows: list[Window]
    ad_hoc_blackout_authority: str = Field(description="Who can impose extra blackouts, and whether they are confidential; empty if none.")
    rules: list[Rule] = Field(description="One entry per (topic, tier, security_state, venue) the policy distinguishes. Cover every topic at least once, using not_addressed where silent.")
    clearance: list[Clearance] = Field(description="One entry per tier with a distinct regime.")
    short_term: list[ShortTermRule]
    exceptions: list[Exception_]
    financing: Financing
    external_documents: list[str] = Field(description="Documents incorporated by reference that are not in the PDF.")
    exemption_authority: str
    jurisdiction_overlays: list[str] = Field(description="e.g. UK MAR, NZX, US rules.")
    bespoke_clauses: list[BespokeClause] = Field(description="Anything collar-relevant that the structured fields cannot hold.")
    summary: str = Field(description="Three to five sentences: can a director or executive enter a funded collar with a bank, and on what conditions.")
