package worker

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
)

func testJob() Job {
	return Job{
		ID:           uuid.New(),
		DeploymentID: uuid.New(),
	}
}

func TestNewValidation(t *testing.T) {
	handler := func(context.Context, Job) error {
		return nil
	}

	tests := []struct {
		name   string
		config Config
	}{
		{
			name: "invalid queue size",
			config: Config{
				QueueSize: 0,
				Workers:   1,
				Handler:   handler,
			},
		},
		{
			name: "invalid worker count",
			config: Config{
				QueueSize: 1,
				Workers:   0,
				Handler:   handler,
			},
		},
		{
			name: "missing handler",
			config: Config{
				QueueSize: 1,
				Workers:   1,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := New(tt.config)

			if err == nil {
				t.Fatal("expected error, got nil")
			}
		})
	}
}

func TestWorkerProcessesJob(t *testing.T) {
	var processed atomic.Int32

	handler := func(ctx context.Context, job Job) error {
		processed.Add(1)
		return nil
	}

	w, err := New(Config{
		QueueSize: 2,
		Workers:   1,
		Handler:   handler,
		Logger:    slog.Default(),
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	w.Start()

	if err := w.Submit(testJob()); err != nil {
		t.Fatalf("submit failed: %v", err)
	}

	w.Shutdown()

	if processed.Load() != 1 {
		t.Fatalf("expected 1 processed job, got %d", processed.Load())
	}
}

func TestWorkerProcessesMultipleJobs(t *testing.T) {
	var processed atomic.Int32

	handler := func(ctx context.Context, job Job) error {
		processed.Add(1)
		return nil
	}

	w, err := New(Config{
		QueueSize: 5,
		Workers:   2,
		Handler:   handler,
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	w.Start()

	const jobCount = 5

	for i := 0; i < jobCount; i++ {
		if err := w.Submit(testJob()); err != nil {
			t.Fatalf("submit failed: %v", err)
		}
	}

	w.Shutdown()

	if processed.Load() != jobCount {
		t.Fatalf(
			"expected %d processed jobs, got %d",
			jobCount,
			processed.Load(),
		)
	}
}

func TestWorkerContinuesAfterHandlerError(t *testing.T) {
	var processed atomic.Int32

	handler := func(ctx context.Context, job Job) error {
		count := processed.Add(1)

		if count == 1 {
			return errors.New("simulated deployment failure")
		}

		return nil
	}

	w, err := New(Config{
		QueueSize: 2,
		Workers:   1,
		Handler:   handler,
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	w.Start()

	if err := w.Submit(testJob()); err != nil {
		t.Fatalf("first submit failed: %v", err)
	}

	if err := w.Submit(testJob()); err != nil {
		t.Fatalf("second submit failed: %v", err)
	}

	w.Shutdown()

	if processed.Load() != 2 {
		t.Fatalf(
			"expected handler to process 2 jobs, got %d",
			processed.Load(),
		)
	}
}

func TestSubmitAfterShutdown(t *testing.T) {
	handler := func(ctx context.Context, job Job) error {
		return nil
	}

	w, err := New(Config{
		QueueSize: 1,
		Workers:   1,
		Handler:   handler,
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	w.Start()
	w.Shutdown()

	err = w.Submit(testJob())

	if !errors.Is(err, ErrQueueClosed) {
		t.Fatalf("expected ErrQueueClosed, got %v", err)
	}
}

func TestShutdownWaitsForJobs(t *testing.T) {
	var (
		mu        sync.Mutex
		processed int
	)

	handler := func(ctx context.Context, job Job) error {
		time.Sleep(50 * time.Millisecond)

		mu.Lock()
		processed++
		mu.Unlock()

		return nil
	}

	w, err := New(Config{
		QueueSize: 3,
		Workers:   1,
		Handler:   handler,
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	w.Start()

	for i := 0; i < 3; i++ {
		if err := w.Submit(testJob()); err != nil {
			t.Fatalf("submit failed: %v", err)
		}
	}

	w.Shutdown()

	mu.Lock()
	defer mu.Unlock()

	if processed != 3 {
		t.Fatalf("expected 3 completed jobs, got %d", processed)
	}
}
