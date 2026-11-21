import assert from "node:assert/strict";
import test from "node:test";
import { getSLOBurnRates } from "../src/lib/slo-api.ts";

test("availability burn distinguishes insufficient, measured zero, and exhausted budget", async (t) => {
  const recorded = {
    "5m": { samples: 20, scrapeAge: 46, rate: "0" },
    "30m": { samples: 108, scrapeAge: 15, rate: "0" },
    "1h": { samples: 240, scrapeAge: 15, rate: "20" },
    "6h": { samples: 270, scrapeAge: 15, rate: "0" },
  };
  const thresholds = { "5m": 18, "30m": 108, "1h": 216, "6h": 1296 };
  t.mock.method(globalThis, "fetch", async (url) => {
    const query = new URL(url, "https://console.example").searchParams.get("query");
    if (!query.startsWith("cloudforge:slo_availability_burn:")) {
      return Response.json({ data: { result: [] } });
    }
    const selected = /^cloudforge:slo_availability_burn:(\w+)\{job="deployment-service",service="deployment-service"\}/.exec(query);
    assert.ok(selected);
    const window = selected[1];
    const { samples, scrapeAge, rate } = recorded[window];
    const coverage = /count_over_time\(up\{[^}]+\}\[(\w+)\]\)\) >= (\d+)/.exec(query);
    assert.equal(coverage?.[1], window);
    assert.equal(Number(coverage?.[2]), thresholds[window]);
    assert.match(query, /timestamp\(up\{[^}]+\}\)\) <= 45/);
    assert.match(query, /timestamp\(cloudforge:slo_availability_burn:[^)]+\) <= 60/);
    const result = samples >= Number(coverage[2]) && scrapeAge <= 45 ? [{ value: [100, rate] }] : [];
    return Response.json({ data: { result } });
  });

  const { availability } = await getSLOBurnRates();
  assert.deepEqual(availability, { "5m": null, "30m": 0, "1h": 20, "6h": null });
});
