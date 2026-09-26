from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .anomaly_models import AnomalySummary
from .anomaly_service import anomaly_detection_service


router = APIRouter(
    prefix="/api/v1/anomalies",
    tags=["AIOps Anomaly Detection"],
)


@router.get(
    "/summary",
    response_model=AnomalySummary,
)
def get_anomaly_summary(
    service: str = Query(
        default="deployment-service",
        min_length=1,
    ),
    window_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
    ),
    step_seconds: int = Query(
        default=60,
        ge=15,
        le=3600,
    ),
) -> AnomalySummary:
    """
    Evaluate current telemetry against a historical baseline.

    The response contains numerical evidence for every metric,
    including current value, baseline, deviation, z-score,
    classification, and sample count.
    """

    try:
        return anomaly_detection_service.evaluate(
            service=service,
            window_minutes=window_minutes,
            step_seconds=step_seconds,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to evaluate anomalies: {error}",
        ) from error
