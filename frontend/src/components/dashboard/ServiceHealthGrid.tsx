"use client";

import { useCallback, useEffect, useState } from "react";
import ServiceHealthCard from "@/components/dashboard/ServiceHealthCard";
import type {
  HealthCheckResponse,
  ServiceHealth,
} from "@/types/health";

interface ServiceHealthGridProps {
  initialServices: ServiceHealth[];
}

export default function ServiceHealthGrid({
  initialServices,
}: ServiceHealthGridProps) {
  const [services, setServices] =
    useState<ServiceHealth[]>(initialServices);

  const [loading, setLoading] = useState(false);
  const [lastChecked, setLastChecked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkServices = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/health-check", {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(
          `Health check failed with status ${response.status}`,
        );
      }

      const data =
        (await response.json()) as HealthCheckResponse;

      setServices(data.services);
      setLastChecked(data.checkedAt);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to check service health",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    const loadInitialHealth = async () => {
      if (!active) {
        return;
      }

      await checkServices();
    };

    void loadInitialHealth();

    return () => {
      active = false;
    };
  }, [checkServices]);

  const healthyCount = services.filter(
    (service) => service.status === "healthy",
  ).length;

  return (
    <section className="space-y-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h3 className="text-xl font-semibold text-[var(--cf-text)]">
            Platform services
          </h3>

          <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
            Live health checks for platform dependencies
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="rounded-full border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-1 text-xs font-medium text-[var(--cf-text-secondary)]">
            {healthyCount}/{services.length} healthy
          </span>

          <button
            type="button"
            onClick={() => void checkServices()}
            disabled={loading}
            className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-2 text-xs font-medium text-[var(--cf-text-secondary)] shadow-sm transition hover:border-[var(--cf-border-strong)] hover:bg-[var(--cf-surface-2)] hover:text-[var(--cf-text)] disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {loading ? "Checking..." : "Refresh"}
          </button>
        </div>
      </div>

      {lastChecked && (
        <p className="text-xs text-[var(--cf-text-muted)]">
          Last checked:{" "}
          {new Date(lastChecked).toLocaleTimeString()}
        </p>
      )}

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {services.map((service) => (
          <ServiceHealthCard
            key={service.name}
            name={service.name}
            description={service.description}
            port={service.port}
            status={service.status}
            latencyMs={service.latencyMs}
            error={service.error}
          />
        ))}
      </div>
    </section>
  );
}
