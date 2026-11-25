"""Run the SLO coverage fixture with the existing Prometheus image.

Use services/aiops-service/.venv/bin/python monitoring/prometheus/test-slo-evidence.py.
The fixture scales the production seven-day window to five minutes and its
90% sample threshold to 18. Freshness and ratio expressions remain identical.
"""
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

root = Path(__file__).resolve().parent
wanted = {
    "cloudforge:slo_availability:7d",
    "cloudforge:slo_request_success:7d",
    "cloudforge:slo_latency_compliance:7d",
}


def prepare_fixture(path):
    """Scale the actual recording rules for the unchanged bounded SLO fixture."""
    source = yaml.safe_load((root / "rules/cloudforge-recording.yml").read_text())
    rules = [rule for group in source["groups"] for rule in group["rules"] if rule.get("record") in wanted]
    assert len(rules) == len(wanted)
    for rule in rules:
        assert "[7d]" in rule["expr"] and ">= 36288" in rule["expr"]
        rule["record"] = rule["record"].replace(":7d", ":5m")
        rule["expr"] = rule["expr"].replace("[7d]", "[5m]").replace(">= 36288", ">= 18")
    (path / "slo-evidence-rules.yml").write_text(yaml.safe_dump({
        "groups": [{"name": "slo-evidence", "interval": "15s", "rules": rules}],
    }))
    (path / "slo-evidence.test.yml").write_text((root / "slo-evidence.test.yml").read_text())


def main():
    image = os.environ.get("PROMETHEUS_TEST_IMAGE", "prom/prometheus:v3.5.0")
    with tempfile.TemporaryDirectory(prefix="cloudforge-slo-evidence-") as directory:
        path = Path(directory)
        path.chmod(0o755)
        prepare_fixture(path)
        subprocess.run([
            "docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/promtool", "-v", f"{path}:/fixtures:ro", "-w", "/fixtures",
            image, "test", "rules", "slo-evidence.test.yml",
        ], check=True)


if __name__ == "__main__":
    main()
