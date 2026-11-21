package terraform

import (
	"regexp"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var pricingInstanceClass = regexp.MustCompile(`^db\.[a-z0-9-]+\.[a-z0-9-]+$`)

// PlanPricingBasis exposes only bounded catalog selectors, never plan values
// such as credentials or subnet IDs. Estimates cover the named component only.
func PlanPricingBasis(resource model.InfrastructureResource) *model.PlanPricingBasis {
	config := resource.Configuration
	switch resource.ResourceType {
	case resourceEC2:
		instance, _ := stringValue(config, "instance_type")
		if ec2InstanceTypePattern.MatchString(instance) {
			return &model.PlanPricingBasis{ResourceType: "aws_instance", Unit: "instance-month:" + instance, Quantity: 1}
		}
	case resourceRDS:
		engine, ok := stringValue(config, "engine")
		if !ok {
			engine = "postgres"
		}
		class, ok := stringValue(config, "instance_class")
		if !ok {
			class = "db.t4g.micro"
		}
		if rdsEnginePattern.MatchString(engine) && pricingInstanceClass.MatchString(class) {
			mode := "single-az"
			if boolValue(config, "multi_az", false) {
				mode = "multi-az"
			}
			return &model.PlanPricingBasis{ResourceType: "aws_db_instance", Unit: "instance-month:" + engine + ":" + class + ":" + mode, Quantity: 1}
		}
	case resourceEKS:
		types, err := stringSliceValue(config, "node_instance_types")
		if err == nil && len(types) == 0 {
			types = []string{"t3.medium"}
		}
		count := intValue(config, "desired_capacity", 2)
		if err == nil && len(types) == 1 && ec2InstanceTypePattern.MatchString(types[0]) && count > 0 && count <= 100 {
			return &model.PlanPricingBasis{ResourceType: "aws_eks_node_group", Unit: "node-month:" + types[0], Quantity: count}
		}
	}
	return nil
}
