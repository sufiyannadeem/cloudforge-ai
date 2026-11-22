// Each request completes well inside the HTTP API integration timeout.
export async function waitForTerraformJob(response: Response, resourceUrl: string): Promise<Response> {
  if (response.status !== 202) return response;
  const job = await response.json() as { id: string };
  if (!/^[0-9a-f-]{36}$/.test(job.id)) throw new Error("Invalid operation receipt");
  const deadline = Date.now() + 41 * 60_000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const poll = await fetch(`${resourceUrl}/jobs/${job.id}`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
    if (!poll.ok) throw new Error("Operation status unavailable. Refresh before retrying.");
    const state = await poll.json() as { status: string; response?: unknown; response_code?: number };
    if (state.status === "interrupted") throw new Error("Operation interrupted. Reconcile Terraform state before retrying.");
    if (state.status === "succeeded" || state.status === "failed") {
      return new Response(JSON.stringify(state.response), { status: state.response_code ?? 500,
        headers: { "Content-Type": "application/json" } });
    }
  }
  throw new Error("Operation status timed out. Refresh before retrying.");
}
