package terraform

import (
	"fmt"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestEC2StateAttribution(t *testing.T) {
	project := uuid.New()
	resource := model.InfrastructureResource{ID: uuid.New(), ProjectID: &project, Region: "us-east-1", Environment: "staging"}
	state := fmt.Sprintf(`{"values":{"root_module":{"resources":[{
		"address":"aws_instance.this","mode":"managed","type":"aws_instance",
		"values":{"arn":"arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0","id":"i-0123456789abcdef0",
		"tags":{"cloudforge:project-id":%q,"cloudforge:resource-id":%q,"cloudforge:environment":"staging"}}
	}]}}}`, project.String(), resource.ID.String())
	if got := ec2FromState(state, resource); got == nil || got.AccountID != "123456789012" || got.InstanceID != "i-0123456789abcdef0" {
		t.Fatal("verified state did not produce attribution")
	}
	for _, mismatch := range [][2]string{{project.String(), uuid.NewString()}, {"staging", "production"}, {"us-east-1", "us-east-2"}, {"managed", "data"}} {
		if ec2FromState(strings.Replace(state, mismatch[0], mismatch[1], 1), resource) != nil {
			t.Fatalf("accepted mismatched state field %q", mismatch[0])
		}
	}
}
