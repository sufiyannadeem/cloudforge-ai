"""Targeted configuration regressions for the application workload examples."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def deployments():
    documents = yaml.safe_load_all(
        (ROOT / "deploy/kubernetes/cloudforge-secrets-example.yml").read_text()
    )
    return {
        doc["metadata"]["name"]: doc["spec"]["template"]["spec"]
        for doc in documents if isinstance(doc, dict) and doc.get("kind") == "Deployment"
    }


def test_application_roots_are_read_only_with_persistent_plans_and_scoped_caches():
    workloads = deployments()
    assert len(workloads) == 6
    for spec in workloads.values():
        volumes = {volume["name"]: volume for volume in spec.get("volumes", [])}
        for container in spec["containers"]:
            assert container["securityContext"]["readOnlyRootFilesystem"] is True
            for mount in container.get("volumeMounts", []):
                assert mount["name"] in volumes
                assert mount["mountPath"] != "/"
        if volumes:
            assert spec["securityContext"]["fsGroup"] == spec["securityContext"]["runAsUser"]

    infrastructure = workloads["infrastructure-service"]
    mounts = {mount["mountPath"]: mount["name"] for mount in infrastructure["containers"][0]["volumeMounts"]}
    workspace = next(volume for volume in infrastructure["volumes"] if volume["name"] == mounts["/var/lib/cloudforge/terraform"])
    assert workspace["persistentVolumeClaim"]["claimName"] == "cloudforge-terraform-workspaces"
    frontend_mounts = {mount["mountPath"] for mount in workloads["frontend"]["containers"][0]["volumeMounts"]}
    assert {"/tmp", "/app/.next/cache"} <= frontend_mounts


def test_deployer_permissions_remain_project_scoped_and_minimal():
    documents = list(yaml.safe_load_all(
        (ROOT / "deploy/kubernetes/project-deployment-rbac-example.yml").read_text()
    ))
    role, binding = documents
    assert role["kind"] == "Role" and binding["kind"] == "RoleBinding"
    assert binding["subjects"] == [{"kind":"ServiceAccount", "name":"cloudforge-deployment-service", "namespace":"cloudforge"}]
    assert binding["roleRef"] == {"apiGroup":"rbac.authorization.k8s.io", "kind":"Role", "name":role["metadata"]["name"]}
    assert role["metadata"]["namespace"] == binding["metadata"]["namespace"] == "cf-PROJECT_UUID"
    permissions = {(tuple(rule["apiGroups"]), tuple(rule["resources"])): set(rule["verbs"]) for rule in role["rules"]}
    assert permissions[(("apps",), ("replicasets",))] == {"list"}
    assert permissions[(("apps",), ("deployments",))] == {"get", "list", "watch", "create", "patch"}
    assert permissions[(("",), ("services",))] == {"get", "create", "patch"}
    forbidden_resources = {"*", "secrets", "pods/exec", "nodes", "namespaces", "roles", "rolebindings"}
    forbidden_verbs = {"*", "delete", "deletecollection", "bind", "escalate", "impersonate"}
    for (_groups, resources), verbs in permissions.items():
        assert not forbidden_resources.intersection(resources)
        assert not forbidden_verbs.intersection(verbs)
    assert "KSV-0048" not in (ROOT / ".trivyignore").read_text()
    assert "KSV-0056" not in (ROOT / ".trivyignore").read_text()


def test_rbac_exceptions_are_limited_to_the_reviewed_role_manifest():
    exceptions = yaml.safe_load(
        (ROOT / "deploy/kubernetes/trivy-rbac-exceptions.yaml").read_text()
    )
    assert set(exceptions) == {"misconfigurations"}
    assert {entry["id"] for entry in exceptions["misconfigurations"]} == {"KSV-0048", "KSV-0056"}
    for entry in exceptions["misconfigurations"]:
        assert entry["paths"] == ["deploy/kubernetes/project-deployment-rbac-example.yml"]
        assert entry["statement"]
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    scans = [step["with"] for job in workflow["jobs"].values() for step in job.get("steps", [])
             if step.get("uses", "").startswith("aquasecurity/trivy-action@")]
    assert all(scan["version"] == "v0.76.2" for scan in scans)
    assert next(scan for scan in scans if scan["scan-type"] == "fs")["trivyignores"] == "deploy/kubernetes/trivy-rbac-exceptions.yaml"


def test_raw_workloads_have_bounded_storage_and_minimal_api_tokens():
    for name, pod in deployments().items():
        assert pod['automountServiceAccountToken'] is (name=='deployment-service')
        for container in pod['containers']:
            assert container['resources']['requests']['ephemeral-storage']=='128Mi'
            assert container['resources']['limits']['ephemeral-storage']=='4Gi'
