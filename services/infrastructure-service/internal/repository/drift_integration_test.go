package repository

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestDriftHistoryFencesStaleScans(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	repo := newTestRepository()
	resource := newTestResource()
	resource.Status = model.ResourceStatusActive
	if err := repo.Create(ctx, resource); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, err := testPool.Exec(context.Background(), "DELETE FROM infrastructure_resources WHERE id=$1", resource.ID)
		if err != nil {
			t.Error(err)
		}
	})
	resource, err := repo.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatal(err)
	}
	scan := DriftScan{Actor: "sre", Status: "observed", Findings: []byte("[]")}
	saved, err := repo.RecordDrift(ctx, resource.ID, resource.UpdatedAt, scan)
	if err != nil || saved.ID == 0 || saved.ScannedAt.IsZero() {
		t.Fatalf("record scan: %+v, %v", saved, err)
	}
	history, err := repo.DriftHistory(ctx, resource.ID)
	if err != nil || len(history) != 1 || history[0].Actor != scan.Actor || string(history[0].Findings) != "[]" {
		t.Fatalf("read history: %+v, %v", history, err)
	}
	other, err := repo.DriftHistory(ctx, uuid.New())
	if err != nil || len(other) != 0 {
		t.Fatalf("other resource history: %+v, %v", other, err)
	}
	if _, err := repo.RecordDrift(ctx, resource.ID, resource.UpdatedAt.Add(-time.Second), scan); !errors.Is(err, ErrResourceConflict) {
		t.Fatalf("stale scan: %v", err)
	}
}
