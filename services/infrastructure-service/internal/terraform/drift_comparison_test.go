package terraform

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDriftComparisonsWithholdSecretsUnknownAndUnapprovedFields(t *testing.T) {
	raw := `{"format_version":"1.2","resource_changes":[{"mode":"managed","type":"aws_db_instance","change":{"actions":["update"],"before":{"allocated_storage":20,"storage_encrypted":false,"password":"secret-before","multi_az":false,"backup_retention_period":1,"deletion_protection":false},"after":{"allocated_storage":40,"storage_encrypted":true,"password":"secret-after","multi_az":true,"backup_retention_period":7,"deletion_protection":{"nested":"secret"}},"after_sensitive":{"multi_az":true},"after_unknown":{"backup_retention_period":true}}}]}`
	findings, err := classifyDrift(raw)
	if err != nil || len(findings) != 1 {
		t.Fatalf("classification: %v", err)
	}
	comparisons := findings[0].Comparisons
	if len(comparisons) != 2 || comparisons[0].Before != float64(20) || comparisons[0].After != float64(40) || comparisons[1].After != true {
		t.Fatalf("safe comparisons: %+v", comparisons)
	}
	data, _ := json.Marshal(findings)
	if strings.Contains(string(data), "secret") || strings.Contains(string(data), "password") {
		t.Fatal("state secret leaked")
	}
	for _, marker := range []any{true, "invalid", map[string]any{"allocated_storage": []any{true}}} {
		result := safeDriftComparisons(map[string]any{"allocated_storage": float64(20)}, map[string]any{"allocated_storage": float64(40)}, marker, nil, nil)
		if len(result) != 0 {
			t.Fatal("malformed/sensitive marker accepted")
		}
	}
}
