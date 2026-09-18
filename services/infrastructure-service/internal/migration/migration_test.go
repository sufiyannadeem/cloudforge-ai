package migration

import (
	"context"
	"testing"
)

func TestRunnerRejectsNilPool(t *testing.T) {
	runner := NewRunner(nil)

	err := runner.Run(context.Background())

	if err == nil {
		t.Fatal("expected error for nil database pool, got nil")
	}
}
