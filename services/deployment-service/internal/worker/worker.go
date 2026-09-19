package worker

import (
	"context"
	"errors"
	"log/slog"
	"sync"
)

var ErrQueueClosed = errors.New("worker queue is closed")

type Handler func(context.Context, Job) error

type Worker struct {
	jobs    chan Job
	handler Handler
	logger  *slog.Logger
	workers int
	wg      sync.WaitGroup

	mu     sync.RWMutex
	closed bool
}

type Config struct {
	QueueSize int
	Workers   int
	Handler   Handler
	Logger    *slog.Logger
}

func New(config Config) (*Worker, error) {
	if config.QueueSize <= 0 {
		return nil, errors.New("queue size must be greater than zero")
	}

	if config.Workers <= 0 {
		return nil, errors.New("workers must be greater than zero")
	}

	if config.Handler == nil {
		return nil, errors.New("handler is required")
	}

	logger := config.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &Worker{
		jobs:    make(chan Job, config.QueueSize),
		handler: config.Handler,
		logger:  logger,
		workers: config.Workers,
	}, nil
}

func (w *Worker) Start() {
	w.wg.Add(w.workers)

	for workerID := 1; workerID <= w.workers; workerID++ {
		go w.run(workerID)
	}
}

func (w *Worker) Submit(job Job) error {
	w.mu.RLock()
	defer w.mu.RUnlock()

	if w.closed {
		return ErrQueueClosed
	}

	w.jobs <- job
	return nil
}

func (w *Worker) Shutdown() {
	w.mu.Lock()

	if w.closed {
		w.mu.Unlock()
		w.wg.Wait()
		return
	}

	w.closed = true
	close(w.jobs)

	w.mu.Unlock()
	w.wg.Wait()
}

func (w *Worker) run(workerID int) {
	defer w.wg.Done()

	w.logger.Info(
		"deployment worker started",
		"worker_id",
		workerID,
	)

	for job := range w.jobs {
		err := w.handler(context.Background(), job)

		if err != nil {
			w.logger.Error(
				"deployment job failed",
				"worker_id",
				workerID,
				"job_id",
				job.ID,
				"deployment_id",
				job.DeploymentID,
				"error",
				err,
			)

			continue
		}

		w.logger.Info(
			"deployment job completed",
			"worker_id",
			workerID,
			"job_id",
			job.ID,
			"deployment_id",
			job.DeploymentID,
		)
	}

	w.logger.Info(
		"deployment worker stopped",
		"worker_id",
		workerID,
	)
}
