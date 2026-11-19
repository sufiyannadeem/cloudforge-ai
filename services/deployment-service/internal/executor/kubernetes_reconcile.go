package executor

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// Reconcile verifies both objects from the original apply using only read operations.
func (k *KubernetesExecutor) Reconcile(ctx context.Context, id uuid.UUID) error {
	deployment, err := k.deploymentGetter.GetByID(ctx, id)
	if err != nil {
		return err
	}
	if strings.TrimSpace(deployment.Namespace) == "" {
		deployment.Namespace = k.defaultNamespace
	}
	if err := validateDeploymentForExecution(deployment); err != nil {
		return err
	}
	if err := k.EnsureClusterConfig(ctx); err != nil {
		return err
	}
	name := sanitizeWorkloadName(deployment)
	args := []string{"get", "deployment/" + name, "service/" + name, "-n", deployment.Namespace, "-o", "json"}
	if k.kubeconfigPath != "" {
		args = append(args, "--kubeconfig", k.kubeconfigPath)
	}
	output, err := k.runner(ctx, nil, k.kubectlPath, args...)
	if err != nil {
		return fmt.Errorf("read Kubernetes deployment and service: %w", err)
	}

	var objects struct {
		Items []struct {
			Kind     string
			Metadata struct {
				Name, Namespace   string
				DeletionTimestamp *string
				Annotations       map[string]string
				Generation        int64
			}
			Spec struct {
				Replicas int
				Selector json.RawMessage
				Type     string
				Ports    []struct{ Port, TargetPort int }
				Template struct {
					Spec struct {
						Containers []struct{ Name, Image string }
					}
				}
			}
			Status struct {
				ObservedGeneration                           int64
				Replicas, UpdatedReplicas, AvailableReplicas int
			}
		}
	}
	if err := json.Unmarshal(output, &objects); err != nil {
		return fmt.Errorf("decode Kubernetes state: %w", err)
	}

	var serviceFound, rolloutReady bool
	for _, object := range objects.Items {
		if object.Metadata.Name != name || object.Metadata.Namespace != deployment.Namespace || object.Metadata.DeletionTimestamp != nil ||
			object.Metadata.Annotations["cloudforge.ai/deployment-id"] != id.String() {
			continue
		}

		switch object.Kind {
		case "Service":
			var selector map[string]string
			if err := json.Unmarshal(object.Spec.Selector, &selector); err != nil {
				continue
			}
			for _, port := range object.Spec.Ports {
				if object.Spec.Type == "ClusterIP" && len(selector) == 1 &&
					selector["app.kubernetes.io/name"] == name && port.Port == 80 && port.TargetPort == 8080 {
					serviceFound = true
				}
			}
		case "Deployment":
			replicas := object.Spec.Replicas
			if replicas <= 0 || object.Metadata.Generation <= 0 || object.Status.ObservedGeneration < object.Metadata.Generation ||
				object.Status.Replicas != replicas || object.Status.UpdatedReplicas != replicas ||
				object.Status.AvailableReplicas < replicas {
				continue
			}
			for _, container := range object.Spec.Template.Spec.Containers {
				if container.Name == "app" && container.Image == deployment.Image {
					rolloutReady = true
				}
			}
		}
	}
	if !serviceFound || !rolloutReady {
		return errors.New("matching Kubernetes deployment rollout and service were not confirmed")
	}
	return nil
}
