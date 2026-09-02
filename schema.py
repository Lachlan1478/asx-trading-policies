"""Pydantic schema for the terms extracted from a securities trading policy."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Answer = Literal["permitted", "prohibited", "permitted_with_approval", "not_addressed"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(Strict):
    answer: Answer
    detail: str = Field(description="One or two sentences on what the policy says, including who it applies to and any conditions.")
    evidence: str = Field(description="Verbatim quote from the policy supporting the answer, or empty string if not addressed.")


class TradingWindow(Strict):
    opens: str = Field(description="When the window opens, e.g. 'day after release of full-year results'.")
    closes: str = Field(description="When the window closes, e.g. '30 days after opening' or 'close of business 30 June'.")


class Approval(Strict):
    required: Literal["yes", "no", "not_addressed"]
    must_be_written: Literal["yes", "no", "not_addressed"]
    approver: str = Field(description="Who grants clearance, e.g. 'Chairman for directors; Company Secretary for other designated persons'.")
    validity: str = Field(description="How long a clearance remains valid, e.g. '5 business days', or empty.")
    post_trade_notification: str = Field(description="Any obligation to notify after dealing and the deadline, or empty.")
    evidence: str


class PolicyTerms(Strict):
    company: str
    policy_title: str
    policy_date: str = Field(description="Effective or approval date as stated in the document, or empty.")
    covered_persons: str = Field(description="Who the restrictions apply to, e.g. directors, KMP, designated employees, all staff.")
    window_model: Literal["open_windows", "closed_periods", "both", "not_addressed"] = Field(
        description="Whether the policy defines when dealing IS allowed (open windows), when it is NOT (closed/blackout periods), or both.")
    trading_windows: list[TradingWindow] = Field(description="Each open trading window as defined by the policy.")
    closed_periods: str = Field(description="Description of the closed/blackout periods, e.g. 'from 1 January until the day after release of half-year results'.")
    ad_hoc_blackouts: Literal["yes", "no", "not_addressed"] = Field(description="Whether the company can impose additional ad hoc blackout periods.")
    derivatives: Finding = Field(description="Dealing in derivatives, options, warrants or other financial products over company securities.")
    hedging_unvested: Finding = Field(description="Hedging or limiting economic risk on unvested equity incentives (rights, options, performance shares).")
    hedging_vested: Finding = Field(description="Hedging vested holdings via collars, caps, floors, put/call structures, equity swaps or similar.")
    monetisation: Finding = Field(description="Monetising positions via forward sales, prepaid variable forwards, equity swaps or similar structures that transfer economic exposure.")
    short_selling: Finding
    margin_lending: Finding = Field(description="Margin loans, or using securities as collateral where the lender may sell them.")
    encumbrance: Finding = Field(description="Granting security interests, pledging or otherwise encumbering securities; any requirement that holdings remain unencumbered.")
    short_term_trading: Finding = Field(description="Short-term or speculative dealing.")
    minimum_holding_period: str = Field(description="Any minimum holding period, e.g. '3 months', or empty.")
    approval: Approval
    exceptional_circumstances: Finding = Field(description="Whether dealing in a closed period is possible under exceptional circumstances (e.g. severe financial hardship).")
    explicit_collar_mention: bool = Field(description="True if the policy expressly names collars, caps and collars, or zero-cost collars.")
    other_collar_relevant_clauses: list[str] = Field(description="Any other clauses that would affect entering an OTC collar with a bank, quoted or closely paraphrased.")
    collar_assessment: str = Field(description="Two to four sentences: can a director or executive enter a collar over vested shares with a bank under this policy, and on what conditions.")
