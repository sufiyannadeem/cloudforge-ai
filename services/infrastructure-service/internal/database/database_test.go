package database

import (
	"context"
	"testing"
)

func TestNewPoolRejectsEmptyDatabaseURL(t *testing.T) {
	ctx := context.Background()

	_, err := NewPool(ctx, Config{
		DatabaseURL: "",
	})

	if err == nil {
		t.Fatal("expected error for empty database URL, got nil")
	}
}
