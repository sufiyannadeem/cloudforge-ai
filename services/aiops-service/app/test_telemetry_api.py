import asyncio
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from . import main
from .anomaly_service import AnomalyDetectionService
from .prometheus_client import PrometheusClient, PrometheusQueryResult
from .slo_service import DEFAULT_WINDOW, SLOService

KEY = "testing-only-frontend-to-aiops-key"
SLO = "/api/v1/slo/summary"
ANOMALIES = "/api/v1/anomalies/summary"
QUERY = "service=deployment-service&window_minutes=60&step_seconds=60"


def signed_request(path, query="", *, missing=False, key=KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": "frontend", "aud": "aiops", "method": "GET",
        "target": path + ("?" + query if query else ""),
        "sub": "operator", "role": "sre", "iat": now, "exp": now + 25,
        "nonce": "ab" * 16,
        **overrides,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    signature = hmac.new(key.encode(), payload, hashlib.sha256).hexdigest().encode()
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(b"x-cloudforge-role", b"platform-engineer")] +
        ([] if missing else [(b"x-cloudforge-identity", payload + b"." + signature)]),
    })


@pytest.fixture
def claims_store(monkeypatch):
    monkeypatch.setenv("CLOUDFORGE_FRONTEND_KEY", KEY)
    consumed = set()

    async def claim(_, nonce, expiry):
        assert expiry > int(time.time())
        if nonce in consumed:
            return False
        consumed.add(nonce)
        return True

    monkeypatch.setattr(main, "run_in_threadpool", claim)
    return consumed


@pytest.mark.parametrize("path,role", [(SLO, "platform-engineer"), (ANOMALIES, "sre")])
def test_telemetry_accepts_operator_and_rejects_replay(claims_store, path, role):
    async def endpoint(request):
        assert request.state.human_identity["role"] == role
        return JSONResponse({"accepted": True})

    request = signed_request(path, QUERY if path == ANOMALIES else "", role=role)
    assert asyncio.run(main.authorize_requests(request, endpoint)).status_code == 200
    assert asyncio.run(main.authorize_requests(request, endpoint)).status_code == 401


@pytest.mark.parametrize("path,query,overrides,status", [
    (SLO, "", {"role": "developer"}, 403),
    (ANOMALIES, QUERY, {"role": "developer"}, 403),
    (SLO, "", {"missing": True}, 401),
    (SLO, "", {"key": "another-service-key"}, 401),
    (SLO, "", {"aud": "deployment"}, 401),
    (SLO, "", {"iss": "aiops"}, 401),
    (SLO, "", {"method": "POST"}, 401),
    (SLO, "", {"target": ANOMALIES}, 401),
    (SLO, "", {"exp": 1}, 401),
    (ANOMALIES, QUERY, {"target": ANOMALIES + "?" + "&".join(reversed(QUERY.split("&")))}, 401),
    (ANOMALIES, QUERY, {"target": ANOMALIES + "?" + QUERY.replace("-service", "%2Dservice")}, 401),
])
def test_telemetry_rejects_forged_or_unscoped_identity(claims_store, path, query, overrides, status):
    async def endpoint(_):
        pytest.fail("unauthorized telemetry handler executed")

    response = asyncio.run(main.authorize_requests(signed_request(path, query, **overrides), endpoint))
    assert response.status_code == status
    assert not claims_store


def test_slo_budget_uses_the_same_window_and_observed_sli():
    expressions = []
    def scalar(expression):
        expressions.append(expression)
        return {"value": 0.985} if "http_requests_total" in expression else None

    summary = SLOService(SimpleNamespace(scalar=scalar)).evaluate()
    payload = json.loads(summary.model_dump_json())
    availability, success, latency = payload["slos"]
    assert availability["status"] == latency["status"] == "insufficient_data"
    assert availability["compliance"] is None and latency["error_budget_remaining"] is None
    assert success["window"] == DEFAULT_WINDOW
    assert success["compliance"] == 0.985
    assert success["error_budget_consumed"] == pytest.approx(
        (1 - success["compliance"]) / (1 - success["target"])
    )
    assert success["error_budget_remaining"] == 0
    assert all(f"[{DEFAULT_WINDOW}]" in expression for expression in expressions)
    assert "count_over_time" in expressions[0]
    assert all("route=~" in expression and "> 0" in expression for expression in expressions[1:])


def test_anomaly_missing_or_stale_data_is_insufficient():
    stale = SimpleNamespace(range_values=lambda **kwargs: (
        [(kwargs["start_timestamp"] + i * 60, 1.0) for i in range(6)], None,
    ))
    result = AnomalyDetectionService(stale).evaluate()
    assert all(metric.classification.value == "insufficient_data" for metric in result.metrics)
    assert all(metric.current_value is None for metric in result.metrics)
    error_expression = AnomalyDetectionService._definitions()[1].expression("deployment-service")
    assert "> 0" in error_expression and "route=~" in error_expression
    assert "vector(0)" not in error_expression and "clamp_min" not in error_expression


def test_prometheus_parses_numeric_samples_and_rejects_multiple_series(monkeypatch):
    client = PrometheusClient()
    monkeypatch.setattr(client, "query", lambda _: PrometheusQueryResult([{"value": [12345, "0.99"]}]))
    assert client.scalar("fixture") == {"timestamp": 12345, "value": 0.99}
    series = {"values": [[12345, "0.5"], [12346, "NaN"]]}
    monkeypatch.setattr(client, "query_range", lambda **_: PrometheusQueryResult([series]))
    assert client.range_values("fixture", 12345, 12346, 15) == ([(12345, 0.5)], None)
    monkeypatch.setattr(client, "query_range", lambda **_: PrometheusQueryResult([series, series]))
    values, error = client.range_values("fixture", 12345, 12346, 15)
    assert not values and error


def test_all_slos_require_full_window_evidence_and_freshness(monkeypatch):
    from . import slo_service
    monkeypatch.setattr(slo_service, "DEFAULT_WINDOW", "7d")
    monkeypatch.setattr(slo_service, "SCRAPE_INTERVAL_SECONDS", 15)
    expressions = []
    def scalar(expression):
        expressions.append(expression)
        return None

    result = SLOService(SimpleNamespace(scalar=scalar)).evaluate()
    assert all(not slo.sufficient_data and slo.compliance is None for slo in result.slos)
    for expression in expressions:
        assert 'count_over_time(up{job="deployment-service"}[7d])' in expression
        assert ">= 36288" in expression
        assert "timestamp(up" in expression and "<= 45" in expression
    assert "max(count_over_time(http_requests_total" in expressions[1]
    assert "max(count_over_time(http_request_duration_seconds_count" in expressions[2]


@pytest.mark.parametrize("count,expected", [(2, "insufficient_data"), (5, "normal")])
def test_anomaly_keeps_five_sample_minimum(count, expected):
    def range_values(**kwargs):
        end, step = kwargs["end_timestamp"], kwargs["step_seconds"]
        return [(end - (count - index - 1) * step, 100.0) for index in range(count)], None

    summary = AnomalyDetectionService(SimpleNamespace(range_values=range_values)).evaluate()
    availability = next(metric for metric in summary.metrics if metric.name == "availability")
    assert availability.sample_count == count
    assert availability.classification.value == expected
    assert AnomalyDetectionService.MINIMUM_SAMPLES == 5
