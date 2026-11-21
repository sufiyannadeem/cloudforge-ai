package terraform

import (
	"encoding/json"
	"strings"
)

func provisionedResourceID(state, resourceType string) string {
	primary := map[string]string{
		resourceEC2: "aws_instance", resourceVPC: "aws_vpc", resourceS3: "aws_s3_bucket",
		resourceRDS: "aws_db_instance", resourceEKS: "aws_eks_cluster", resourceLB: "aws_lb",
	}[resourceType]
	if primary == "" {
		return ""
	}
	var decoded struct {
		Values struct {
			Root struct {
				Resources []struct {
					Address      string
					Mode         string
					Type         string
					ProviderName string `json:"provider_name"`
					Values       struct{ ID string }
				}
			} `json:"root_module"`
		}
	}
	if json.Unmarshal([]byte(state), &decoded) != nil {
		return ""
	}
	for _, resource := range decoded.Values.Root.Resources {
		if resource.Address == primary+".this" && resource.Type == primary && resource.Mode == "managed" &&
			resource.ProviderName == "registry.terraform.io/hashicorp/aws" && strings.TrimSpace(resource.Values.ID) != "" {
			return resource.Values.ID
		}
	}
	return ""
}

type stateModule struct {
	Resources    []struct{ Mode string }
	ChildModules []stateModule `json:"child_modules"`
}

func hasEmptyManagedState(raw string) bool {
	var state struct {
		FormatVersion string `json:"format_version"`
		Values        struct {
			Root stateModule `json:"root_module"`
		}
	}
	return json.Unmarshal([]byte(raw), &state) == nil &&
		strings.HasPrefix(state.FormatVersion, "1.") && !state.Values.Root.hasManagedResources()
}

func (module stateModule) hasManagedResources() bool {
	for _, resource := range module.Resources {
		if resource.Mode != "data" {
			return true
		}
	}
	for _, child := range module.ChildModules {
		if child.hasManagedResources() {
			return true
		}
	}
	return false
}
