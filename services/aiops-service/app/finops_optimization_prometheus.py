from __future__ import annotations

from .finops_optimization_models import (
    HPAObservation,
    KubernetesOptimizationSnapshot,
    KubernetesWorkload,
    NodeObservation,
)
from .prometheus_client import PrometheusClient


class PrometheusFinOpsCollector:
    """Read-only Kubernetes telemetry collector for FinOps analysis."""

    def __init__(self, client: PrometheusClient | None = None) -> None:
        self.client = client or PrometheusClient()

    def collect_snapshot(self) -> KubernetesOptimizationSnapshot:
        return KubernetesOptimizationSnapshot(
            workloads=self._collect_workloads(),
            hpas=self._collect_hpas(),
            nodes=self._collect_nodes(),
        )

    def _collect_workloads(self) -> list[KubernetesWorkload]:
        requests = self.client.query(
            '''sum by (namespace, pod) (kube_pod_container_resource_requests{resource="cpu",unit="core"})'''
        )
        memory_requests = self.client.query(
            '''sum by (namespace, pod) (kube_pod_container_resource_requests{resource="memory",unit="byte"})'''
        )
        limits = self.client.query(
            '''sum by (namespace, pod) (kube_pod_container_resource_limits{resource="cpu",unit="core"})'''
        )
        memory_limits = self.client.query(
            '''sum by (namespace, pod) (kube_pod_container_resource_limits{resource="memory",unit="byte"})'''
        )
        cpu_usage = self.client.query(
            '''sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!="",image!=""}[15m]))'''
        )
        memory_usage = self.client.query(
            '''sum by (namespace, pod) (container_memory_working_set_bytes{container!="",image!=""})'''
        )
        owners = self.client.query(
            '''kube_pod_owner{owner_kind=~"Deployment|StatefulSet|DaemonSet|Job|CronJob|ReplicaSet"}'''
        )
        replicaset_owners = self.client.query(
            '''kube_replicaset_owner{owner_kind="Deployment"}'''
        )

        values = {
            "cpu_request": self._pod_values(requests.value),
            "memory_request": self._pod_values(memory_requests.value),
            "cpu_limit": self._pod_values(limits.value),
            "memory_limit": self._pod_values(memory_limits.value),
            "cpu_usage": self._pod_values(cpu_usage.value),
            "memory_usage": self._pod_values(memory_usage.value),
        }
        owner_map = self._owner_map(owners.value, replicaset_owners.value)

        keys = set().union(*values.values())
        grouped: dict[tuple[str, str], dict[str, float]] = {}
        replicas: dict[tuple[str, str], set[str]] = {}

        for key in keys:
            namespace, pod = key
            workload = owner_map.get(key, pod)
            group = (namespace, workload)
            row = grouped.setdefault(group, {})
            replicas.setdefault(group, set()).add(pod)
            for metric, metric_values in values.items():
                if key in metric_values:
                    row[metric] = row.get(metric, 0.0) + metric_values[key]

        workloads: list[KubernetesWorkload] = []
        for (namespace, workload), row in sorted(grouped.items()):
            workloads.append(
                KubernetesWorkload(
                    namespace=namespace,
                    workload=workload,
                    replicas=float(len(replicas[(namespace, workload)])),
                    cpu_request_cores=row.get("cpu_request", 0.0),
                    cpu_usage_cores=row.get("cpu_usage", 0.0),
                    memory_request_bytes=row.get("memory_request", 0.0),
                    memory_usage_bytes=row.get("memory_usage", 0.0),
                    cpu_limit_cores=row.get("cpu_limit"),
                    memory_limit_bytes=row.get("memory_limit"),
                )
            )
        return workloads

    def _collect_hpas(self) -> list[HPAObservation]:
        mins = self._hpa_values(self.client.query("kube_horizontalpodautoscaler_spec_min_replicas").value)
        maxs = self._hpa_values(self.client.query("kube_horizontalpodautoscaler_spec_max_replicas").value)
        currents = self._hpa_values(self.client.query("kube_horizontalpodautoscaler_status_current_replicas").value)
        desired = self._hpa_values(self.client.query("kube_horizontalpodautoscaler_status_desired_replicas").value)
        keys = set(mins) | set(maxs) | set(currents) | set(desired)
        return [
            HPAObservation(
                namespace=namespace,
                hpa=name,
                min_replicas=int(mins.get((namespace, name), 0)),
                max_replicas=int(maxs.get((namespace, name), 0)),
                current_replicas=int(currents.get((namespace, name), 0)),
                desired_replicas=int(desired.get((namespace, name), 0)),
            )
            for namespace, name in sorted(keys)
        ]

    def _collect_nodes(self) -> list[NodeObservation]:
        alloc_cpu = self._label_values(
            self.client.query('''sum by (node) (kube_node_status_allocatable{resource="cpu",unit="core"})''').value,
            "node",
        )
        alloc_memory = self._label_values(
            self.client.query('''sum by (node) (kube_node_status_allocatable{resource="memory",unit="byte"})''').value,
            "node",
        )
        requested_cpu = self._label_values(
            self.client.query('''sum by (node) (kube_pod_container_resource_requests{resource="cpu",unit="core"})''').value,
            "node",
        )
        requested_memory = self._label_values(
            self.client.query('''sum by (node) (kube_pod_container_resource_requests{resource="memory",unit="byte"})''').value,
            "node",
        )
        usage_cpu = self._label_values(
            self.client.query(
                '''sum by (node) (rate(container_cpu_usage_seconds_total{container!=,image!=}[15m]))'''
            ).value,
            "node",
        )
        usage_memory = self._label_values(
            self.client.query('''sum by (node) (container_memory_working_set_bytes{container!="",image!=""})''').value,
            "node",
        )

        nodes = set(alloc_cpu) | set(alloc_memory) | set(requested_cpu) | set(requested_memory) | set(usage_cpu) | set(usage_memory)
        return [
            NodeObservation(
                node=node,
                cpu_allocatable_cores=alloc_cpu.get(node, 0.0),
                cpu_requested_cores=requested_cpu.get(node, 0.0),
                cpu_usage_cores=usage_cpu.get(node, 0.0),
                memory_allocatable_bytes=alloc_memory.get(node, 0.0),
                memory_requested_bytes=requested_memory.get(node, 0.0),
                memory_usage_bytes=usage_memory.get(node, 0.0),
                cpu_usage_available=node in usage_cpu,
                memory_usage_available=node in usage_memory,
            )
            for node in sorted(nodes)
        ]

    @staticmethod
    def _owner_map(owner_results, replicaset_results) -> dict[tuple[str, str], str]:
        rs_to_deployment: dict[tuple[str, str], str] = {}
        for item in replicaset_results:
            labels = item.get("metric", {})
            namespace = labels.get("namespace")
            rs = labels.get("replicaset") or labels.get("owner_name")
            deployment = labels.get("owner_name")
            if namespace and rs and deployment:
                rs_to_deployment[(namespace, rs)] = deployment

        result: dict[tuple[str, str], str] = {}
        for item in owner_results:
            labels = item.get("metric", {})
            namespace = labels.get("namespace")
            pod = labels.get("pod")
            kind = labels.get("owner_kind")
            owner = labels.get("owner_name")
            if not namespace or not pod or not owner:
                continue
            if kind == "ReplicaSet":
                owner = rs_to_deployment.get((namespace, owner), owner)
            result[(namespace, pod)] = owner
        return result

    @staticmethod
    def _pod_values(results) -> dict[tuple[str, str], float]:
        output: dict[tuple[str, str], float] = {}
        for item in results:
            labels = item.get("metric", {})
            namespace = labels.get("namespace")
            pod = labels.get("pod")
            if not namespace or not pod:
                continue
            try:
                value = float(item["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            key = (namespace, pod)
            output[key] = output.get(key, 0.0) + value
        return output

    @staticmethod
    def _hpa_values(results) -> dict[tuple[str, str], float]:
        output: dict[tuple[str, str], float] = {}
        for item in results:
            labels = item.get("metric", {})
            namespace = labels.get("namespace")
            name = labels.get("horizontalpodautoscaler")
            if not namespace or not name:
                continue
            try:
                output[(namespace, name)] = float(item["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return output

    @staticmethod
    def _label_values(results, label: str) -> dict[str, float]:
        output: dict[str, float] = {}
        for item in results:
            labels = item.get("metric", {})
            name = labels.get(label)
            if not name:
                continue
            try:
                output[name] = float(item["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return output
