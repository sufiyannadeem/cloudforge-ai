package model

import "testing"

func TestStrategyValidationAndLegacyDefault(t *testing.T) {
	if got := (DeploymentStrategy{}).Normalized(); got.Type != "rolling" || got.MaxSurge != 1 {
		t.Fatal(got)
	}
	for _, s := range []DeploymentStrategy{
		{Type: "rolling", MaxSurge: 1}, {Type: "rolling", MaxUnavailable: 1}, {Type: "blue-green"}, {Type: "canary"},
		{ReadinessGates: []string{"example.test/LoadBalancerReady"}},
	} {
		if err := s.Validate(); err != nil {
			t.Fatal(s, err)
		}
	}
	for _, s := range []DeploymentStrategy{
		{Type: "unknown"}, {Type: "rolling"}, {Type: "rolling", MaxSurge: 3}, {Type: "rolling", MaxUnavailable: -1},
		{Type: "canary", MaxSurge: 1}, {Type: "blue-green", ReadinessGates: []string{"bad\ncondition"}},
		{ReadinessGates: []string{"example.test/Ready", "example.test/Ready"}},
	} {
		if s.Validate() == nil {
			t.Fatalf("accepted %#v", s)
		}
	}
}
