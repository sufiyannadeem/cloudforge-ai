package terraform

import (
	"context"
	"encoding/json"
	"path/filepath"
	"regexp"
	"time"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var ec2ARN = regexp.MustCompile(`^arn:aws:ec2:([a-z0-9-]+):([0-9]{12}):instance/(i-(?:[0-9a-f]{8}|[0-9a-f]{17}))$`)

// EC2Attribution reads only the instance managed by the approved, service-generated workspace.
func (r *Runner) EC2Attribution(ctx context.Context, resource model.InfrastructureResource) *model.EC2Attribution {
	if resource.ResourceType != "aws_ec2" || resource.ProjectID == nil ||
		r.validatePlanPath(resource.ID, resource.PlanPath, planFileName) != nil {
		return nil
	}
	readCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	data, err := r.runWithOutput(readCtx, filepath.Dir(resource.PlanPath), "show", "-json")
	if err != nil {
		return nil
	}
	return ec2FromState(data, resource)
}

func ec2FromState(data string, resource model.InfrastructureResource) *model.EC2Attribution {
	if resource.ProjectID == nil {
		return nil
	}
	var state struct {
		Values struct {
			Root struct {
				Resources []struct {
					Address, Mode, Type string
					Values              struct {
						ARN  string
						ID   string
						Tags map[string]string
					}
				}
			} `json:"root_module"`
		}
	}
	if json.Unmarshal([]byte(data), &state) != nil {
		return nil
	}
	var result *model.EC2Attribution
	for _, item := range state.Values.Root.Resources {
		if item.Address != "aws_instance.this" || item.Mode != "managed" || item.Type != "aws_instance" {
			continue
		}
		matches := ec2ARN.FindStringSubmatch(item.Values.ARN)
		tags := item.Values.Tags
		if result != nil || len(matches) != 4 || matches[1] != resource.Region || matches[3] != item.Values.ID ||
			tags["cloudforge:project-id"] != resource.ProjectID.String() ||
			tags["cloudforge:resource-id"] != resource.ID.String() ||
			tags["cloudforge:environment"] != resource.Environment {
			return nil
		}
		result = &model.EC2Attribution{AccountID: matches[2], InstanceID: matches[3]}
	}
	return result
}
