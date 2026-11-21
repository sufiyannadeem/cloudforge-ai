from __future__ import annotations

from threading import RLock

from .terraform_pricing_models import (
    TerraformPricingRateCard,
    TerraformPricingRateCardListResponse,
    TerraformPricingRateCardResponse,
)


class TerraformPricingConflictError(ValueError):
    """Raised when a pricing identity already exists."""


class TerraformPricingNotFoundError(LookupError):
    """Raised when a pricing identity does not exist."""


class TerraformPricingService:
    """
    In-memory pricing evidence registry.

    C.8 deliberately does not persist pricing records and does not retrieve
    pricing from AWS or another external pricing API.

    Every record must be supplied explicitly as evidence.
    """

    GENERATED_BY = "cloudforge-finops-pricing-v1"

    def __init__(self) -> None:
        self._records: dict[
            tuple[str, str, str],
            TerraformPricingRateCard,
        ] = {}
        self._lock = RLock()

    @staticmethod
    def _key(
        resource_type: str,
        region: str,
        unit: str,
    ) -> tuple[str, str, str]:
        return (
            resource_type.strip(),
            region.strip().lower(),
            unit.strip().lower(),
        )

    def create(
        self,
        pricing: TerraformPricingRateCard,
    ) -> TerraformPricingRateCardResponse:
        key = self._key(
            pricing.resource_type.value,
            pricing.region,
            pricing.unit,
        )

        with self._lock:
            if key in self._records:
                raise TerraformPricingConflictError(
                    "pricing evidence already exists for "
                    f"{pricing.resource_type.value}/"
                    f"{pricing.region}/"
                    f"{pricing.unit}"
                )

            stored = pricing.model_copy(deep=True)
            self._records[key] = stored

        return TerraformPricingRateCardResponse.model_validate(
            stored.model_dump()
        )

    def get(
        self,
        resource_type: str,
        region: str,
        unit: str,
    ) -> TerraformPricingRateCardResponse:
        key = self._key(
            resource_type,
            region,
            unit,
        )

        with self._lock:
            pricing = self._records.get(key)

            if pricing is None:
                raise TerraformPricingNotFoundError(
                    "pricing evidence not found for "
                    f"{resource_type}/{region}/{unit}"
                )

            return TerraformPricingRateCardResponse.model_validate(
                pricing.model_dump()
            )

    def list(
        self,
        resource_type: str | None = None,
        region: str | None = None,
    ) -> TerraformPricingRateCardListResponse:
        normalized_resource_type = (
            resource_type.strip()
            if resource_type is not None
            else None
        )

        normalized_region = (
            region.strip().lower()
            if region is not None
            else None
        )

        with self._lock:
            records = list(self._records.values())

        filtered: list[TerraformPricingRateCardResponse] = []

        for pricing in records:
            if (
                normalized_resource_type is not None
                and pricing.resource_type.value != normalized_resource_type
            ):
                continue

            if (
                normalized_region is not None
                and pricing.region.lower() != normalized_region
            ):
                continue

            filtered.append(
                TerraformPricingRateCardResponse.model_validate(
                    pricing.model_dump()
                )
            )

        filtered.sort(
            key=lambda item: (
                item.resource_type.value,
                item.region.lower(),
                item.unit.lower(),
            )
        )

        return TerraformPricingRateCardListResponse(
            records=filtered,
            count=len(filtered),
            generated_by=self.GENERATED_BY,
        )
