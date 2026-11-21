import assert from "node:assert/strict";
import test from "node:test";
import { executionModeLabel } from "../src/lib/deployment-mode.ts";

test("execution provenance distinguishes simulated, Kubernetes and historical unknown", () => {
  assert.equal(executionModeLabel("simulated"), "Simulated");
  assert.equal(executionModeLabel("kubernetes"), "Kubernetes");
  assert.equal(executionModeLabel("unknown"), executionModeLabel(undefined));
  assert.equal(executionModeLabel(undefined), "Execution mode unknown");
});
