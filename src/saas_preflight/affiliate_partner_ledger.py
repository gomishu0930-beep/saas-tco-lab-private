"""Credential-free affiliate partner ledger and fail-closed CTA gate.

The ledger records reviewable account and program state only. It accepts names
of runtime secret bindings, but never a destination URL, tracking identifier,
credential, personal datum, or non-public commission detail.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


class AffiliateAccountStatus(str, Enum):
    REGISTRATION_INCOMPLETE = "registration_incomplete"
    REGISTERED = "registered"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"


class AffiliatePartnershipStatus(str, Enum):
    NOT_APPLIED = "not_applied"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class AffiliateCommissionStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    RESTRICTED_DASHBOARD_ONLY = "restricted_dashboard_only"


class AffiliateCommissionUnit(str, Enum):
    JPY = "JPY"
    PERCENT = "percent"


class AffiliateConditionReviewStatus(str, Enum):
    DETAIL_REVIEWED = "detail_reviewed"
    SUMMARY_ONLY = "summary_only"


class AffiliateConfirmationStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    RESTRICTED_DASHBOARD_ONLY = "restricted_dashboard_only"


_SAFE_TEXT_PATTERN = re.compile(
    r"^(?!.*(?:https?://|www\.|[^\s@]+@[^\s@]+\.[^\s@]+)).+$",
    re.I,
)
_RUNTIME_SECRET_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{7,79}$")


class AffiliateCommissionAmount(StrictModel):
    status: AffiliateCommissionStatus
    value: Decimal | None = Field(default=None, ge=0)
    unit: AffiliateCommissionUnit | None = None

    @model_validator(mode="after")
    def require_known_value_and_unit_together(self) -> Self:
        known = self.status is AffiliateCommissionStatus.KNOWN
        if known and (self.value is None or self.unit is None):
            raise ValueError("known commission requires both value and unit")
        if not known and (self.value is not None or self.unit is not None):
            raise ValueError("unavailable commission cannot retain a value or unit")
        return self


class AffiliateConfirmationRate(StrictModel):
    status: AffiliateConfirmationStatus
    percent: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_known_rate_only(self) -> Self:
        known = self.status is AffiliateConfirmationStatus.KNOWN
        if known and self.percent is None:
            raise ValueError("known confirmation rate requires a percent")
        if not known and self.percent is not None:
            raise ValueError("unavailable confirmation rate cannot retain a percent")
        return self


class AffiliateProgramResearchEntry(StrictModel):
    research_id: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    asp_partner_id: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    program_name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=120)
    commission_amount: AffiliateCommissionAmount
    commission_basis: Literal["single_rate", "maximum_observed_tier", "unknown"]
    performance_condition: str = Field(min_length=2, max_length=600)
    condition_review_status: AffiliateConditionReviewStatus
    confirmation_rate: AffiliateConfirmationRate
    partnership_status: AffiliatePartnershipStatus
    disclosure_requirement: str = Field(min_length=2, max_length=500)
    checked_on: date
    affiliate_approval_runtime_secret: str
    destination_runtime_secret: str

    @field_validator(
        "program_name",
        "category",
        "performance_condition",
        "disclosure_requirement",
    )
    @classmethod
    def reject_urls_and_personal_contacts(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not _SAFE_TEXT_PATTERN.fullmatch(normalized):
            raise ValueError("program research text cannot contain a URL or email address")
        return normalized

    @field_validator(
        "affiliate_approval_runtime_secret",
        "destination_runtime_secret",
    )
    @classmethod
    def require_runtime_secret_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not _RUNTIME_SECRET_PATTERN.fullmatch(normalized):
            raise ValueError("runtime secret reference must be an uppercase environment name")
        return normalized

    @model_validator(mode="after")
    def keep_restricted_values_out_of_the_ledger(self) -> Self:
        if (
            self.commission_amount.status
            is AffiliateCommissionStatus.RESTRICTED_DASHBOARD_ONLY
            and self.commission_basis == "unknown"
        ):
            raise ValueError("restricted commission requires its observed basis")
        return self


class AffiliateNetworkSearchCheck(StrictModel):
    partner_id: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    partner_name: str = Field(min_length=2, max_length=120)
    a8_status: Literal["not_confirmed"] = "not_confirmed"
    next_networks: tuple[Literal["moshimo", "valuecommerce"], ...]
    next_status: Literal["waiting"] = "waiting"
    checked_on: date

    @field_validator("partner_name")
    @classmethod
    def reject_urls_and_personal_contacts(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not _SAFE_TEXT_PATTERN.fullmatch(normalized):
            raise ValueError("network search text cannot contain a URL or email address")
        return normalized

    @model_validator(mode="after")
    def require_both_pending_networks(self) -> Self:
        if self.next_networks != ("moshimo", "valuecommerce"):
            raise ValueError("unconfirmed A8 partner must wait for both Japanese ASP checks")
        return self


class AffiliatePartnerLedgerEntry(StrictModel):
    partner_id: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    asp_name: str = Field(min_length=2, max_length=120)
    account_status: AffiliateAccountStatus
    program_name: str | None = Field(default=None, min_length=2, max_length=160)
    category: str | None = Field(default=None, min_length=2, max_length=120)
    commission_amount: AffiliateCommissionAmount
    performance_condition: str | None = Field(default=None, min_length=2, max_length=500)
    partnership_status: AffiliatePartnershipStatus
    disclosure_requirement: str = Field(min_length=2, max_length=500)
    checked_on: date
    affiliate_approval_runtime_secret: str
    destination_runtime_secret: str

    @field_validator(
        "asp_name",
        "program_name",
        "category",
        "performance_condition",
        "disclosure_requirement",
    )
    @classmethod
    def reject_urls_and_personal_contacts(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not _SAFE_TEXT_PATTERN.fullmatch(normalized):
            raise ValueError("partner ledger text cannot contain a URL or email address")
        return normalized

    @field_validator(
        "affiliate_approval_runtime_secret",
        "destination_runtime_secret",
    )
    @classmethod
    def require_runtime_secret_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not _RUNTIME_SECRET_PATTERN.fullmatch(normalized):
            raise ValueError("runtime secret reference must be an uppercase environment name")
        return normalized

    @model_validator(mode="after")
    def require_coherent_program_state(self) -> Self:
        program_selected = self.program_name is not None
        if not program_selected:
            if any(
                value is not None
                for value in (
                    self.category,
                    self.performance_condition,
                )
            ):
                raise ValueError("unselected partnership cannot retain program details")
            if self.commission_amount.status is not AffiliateCommissionStatus.UNKNOWN:
                raise ValueError("unselected partnership commission must remain unknown")
            if self.partnership_status is not AffiliatePartnershipStatus.NOT_APPLIED:
                raise ValueError("pending or reviewed partnership requires a program")
        elif self.category is None or self.performance_condition is None:
            raise ValueError("selected program requires category and performance condition")
        if self.partnership_status is AffiliatePartnershipStatus.APPROVED:
            if self.account_status is not AffiliateAccountStatus.APPROVED:
                raise ValueError("approved partnership requires an approved account")
        return self


class AffiliatePartnerLedger(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    property_domain: Literal["saastcolab.jp"] = "saastcolab.jp"
    tracking_ids_saved: Literal[False] = False
    advertising_urls_saved: Literal[False] = False
    personal_data_saved: Literal[False] = False
    cta_gate: Literal[
        "partner_approved+disclosure_precedes_cta+destination_configured+cta_go"
    ] = "partner_approved+disclosure_precedes_cta+destination_configured+cta_go"
    entries: tuple[AffiliatePartnerLedgerEntry, ...] = Field(min_length=1, max_length=50)
    program_research: tuple[AffiliateProgramResearchEntry, ...] = Field(
        min_length=1,
        max_length=100,
    )
    network_search_checks: tuple[AffiliateNetworkSearchCheck, ...] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def require_unique_sorted_entries(self) -> Self:
        partner_ids = tuple(entry.partner_id for entry in self.entries)
        if partner_ids != tuple(sorted(partner_ids)) or len(set(partner_ids)) != len(
            partner_ids
        ):
            raise ValueError("partner ledger entries must have unique sorted partner IDs")
        approval_secrets = tuple(
            entry.affiliate_approval_runtime_secret for entry in self.entries
        )
        destination_secrets = tuple(
            entry.destination_runtime_secret for entry in self.entries
        )
        if len(set(approval_secrets)) != len(approval_secrets):
            raise ValueError("affiliate approval runtime secret references must be unique")
        if len(set(destination_secrets)) != len(destination_secrets):
            raise ValueError("destination runtime secret references must be unique")

        research_ids = tuple(item.research_id for item in self.program_research)
        if research_ids != tuple(sorted(research_ids)) or len(set(research_ids)) != len(
            research_ids
        ):
            raise ValueError("program research entries must have unique sorted IDs")
        known_partner_ids = set(partner_ids)
        if any(
            item.asp_partner_id not in known_partner_ids
            for item in self.program_research
        ):
            raise ValueError("program research must reference an existing ASP partner")

        research_approval_secrets = tuple(
            item.affiliate_approval_runtime_secret for item in self.program_research
        )
        research_destination_secrets = tuple(
            item.destination_runtime_secret for item in self.program_research
        )
        if len(set(research_approval_secrets)) != len(research_approval_secrets):
            raise ValueError("program approval runtime secret references must be unique")
        if len(set(research_destination_secrets)) != len(research_destination_secrets):
            raise ValueError("program destination runtime secret references must be unique")
        if set(approval_secrets) & set(research_approval_secrets):
            raise ValueError("account and program approval secret references must differ")
        if set(destination_secrets) & set(research_destination_secrets):
            raise ValueError("account and program destination secret references must differ")

        search_ids = tuple(item.partner_id for item in self.network_search_checks)
        if search_ids != tuple(sorted(search_ids)) or len(set(search_ids)) != len(
            search_ids
        ):
            raise ValueError("network search checks must have unique sorted partner IDs")
        return self


class AffiliateCtaRuntimeState(StrictModel):
    partner_id: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    partner_approval_current: bool
    disclosure_precedes_cta: bool
    destination_configured: bool
    cta_go: bool


def evaluate_affiliate_cta_gate(
    entry: AffiliatePartnerLedgerEntry,
    runtime: AffiliateCtaRuntimeState,
) -> bool:
    """Return true only when ledger approval and every runtime gate agree."""

    return (
        runtime.partner_id == entry.partner_id
        and entry.account_status is AffiliateAccountStatus.APPROVED
        and entry.partnership_status is AffiliatePartnershipStatus.APPROVED
        and runtime.partner_approval_current
        and runtime.disclosure_precedes_cta
        and runtime.destination_configured
        and runtime.cta_go
    )


def evaluate_affiliate_program_cta_gate(
    account: AffiliatePartnerLedgerEntry,
    program: AffiliateProgramResearchEntry,
    runtime: AffiliateCtaRuntimeState,
) -> bool:
    """Return true only for a Human-approved program under an approved account."""

    return (
        program.asp_partner_id == account.partner_id
        and runtime.partner_id == program.research_id
        and account.account_status is AffiliateAccountStatus.APPROVED
        and program.partnership_status is AffiliatePartnershipStatus.APPROVED
        and runtime.partner_approval_current
        and runtime.disclosure_precedes_cta
        and runtime.destination_configured
        and runtime.cta_go
    )


def load_affiliate_partner_ledger(path: Path) -> AffiliatePartnerLedger:
    """Load the strict JSON ledger without network or external state access."""

    return AffiliatePartnerLedger.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "AffiliateAccountStatus",
    "AffiliateCommissionAmount",
    "AffiliateCommissionStatus",
    "AffiliateCommissionUnit",
    "AffiliateConditionReviewStatus",
    "AffiliateConfirmationRate",
    "AffiliateConfirmationStatus",
    "AffiliateCtaRuntimeState",
    "AffiliateNetworkSearchCheck",
    "AffiliatePartnerLedger",
    "AffiliatePartnerLedgerEntry",
    "AffiliatePartnershipStatus",
    "AffiliateProgramResearchEntry",
    "evaluate_affiliate_cta_gate",
    "evaluate_affiliate_program_cta_gate",
    "load_affiliate_partner_ledger",
]
