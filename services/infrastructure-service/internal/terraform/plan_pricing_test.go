package terraform

import (
	"testing"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestPlanPricingBasisIncludesOnlySpecificKnownUnits(t *testing.T) {
	r := model.InfrastructureResource{ResourceType: "aws_rds", Configuration: map[string]any{
		"engine": "postgres", "instance_class": "db.t4g.micro", "multi_az": true, "password": "private",
	}}
	got := PlanPricingBasis(r)
	if got == nil || *got != (model.PlanPricingBasis{ResourceType: "aws_db_instance", Unit: "instance-month:postgres:db.t4g.micro:multi-az", Quantity: 1}) {
		t.Fatalf("unexpected estimate scope: %+v", got)
	}
	r.ResourceType = "aws_eks"
	r.Configuration = map[string]any{"node_instance_types": []string{"t3.medium", "t3.large"}, "desired_capacity": 2}
	if PlanPricingBasis(r) != nil {
		t.Fatal("mixed instance types must not produce a single rate")
	}
	r.Configuration["node_instance_types"] = []string{"t3.medium"}
	if got := PlanPricingBasis(r); got == nil || got.Quantity != 2 || got.Unit != "node-month:t3.medium" {
		t.Fatalf("unexpected worker estimate scope: %+v", got)
	}
}
