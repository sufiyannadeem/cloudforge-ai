package database

import (
	"context"
	"testing"
)

func TestNewPoolRejectsEmptyURL(t *testing.T) {
	ctx := context.Background()

	pool, err := NewPool(ctx, "")
	if err == nil {
		if pool != nil {
			pool.Close()
		}

		t.Fatal("expected error for empty database URL")
	}

	if pool != nil {
		pool.Close()
	}
}
