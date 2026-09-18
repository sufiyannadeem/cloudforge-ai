package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/config"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/database"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/handler"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/service"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("failed to load configuration: %v", err)
	}

	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	dbPool, err := database.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("failed to connect to database: %v", err)
	}
	defer dbPool.Close()

	if err := migration.Run(ctx, dbPool); err != nil {
		log.Fatalf("failed to run database migrations: %v", err)
	}

	log.Println("database migrations completed successfully")

	projectRepository := repository.NewProjectRepository(dbPool)
	projectService := service.NewProjectService(projectRepository)
	projectHandler := handler.NewProjectHandler(projectService)

	mux := http.NewServeMux()

	mux.HandleFunc("/health", healthHandler)
	mux.Handle("/projects", projectHandler)
	mux.Handle("/projects/", projectHandler)

	server := &http.Server{
		Addr:              ":" + cfg.ServerPort,
		Handler:           requestIDMiddleware(loggingMiddleware(mux)),
		ReadHeaderTimeout: 5 * time.Second,
	}

	serverErrors := make(chan error, 1)

	go func() {
		log.Printf(
			"project-service listening on port %s",
			cfg.ServerPort,
		)

		serverErrors <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}

	case <-ctx.Done():
		log.Println("shutdown signal received")

		shutdownCtx, cancel := context.WithTimeout(
			context.Background(),
			time.Duration(cfg.ShutdownTimeoutSeconds)*time.Second,
		)
		defer cancel()

		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("graceful shutdown failed: %v", err)

			if closeErr := server.Close(); closeErr != nil {
				log.Printf("forced server close failed: %v", closeErr)
			}
		}

		log.Println("server shutdown completed")
	}
}

func healthHandler(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.Header().Set("Allow", "GET, HEAD")
		http.Error(
			w,
			"method not allowed",
			http.StatusMethodNotAllowed,
		)
		return
	}

	w.Header().Set("Content-Type", "application/json")

	if r.Method == http.MethodHead {
		w.WriteHeader(http.StatusOK)
		return
	}

	response := map[string]string{
		"status":  "ok",
		"service": "project-service",
	}

	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("failed to write health response: %v", err)
	}
}

func requestIDMiddleware(
	next http.Handler,
) http.Handler {
	return http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		requestID := r.Header.Get("X-Request-ID")

		if requestID == "" {
			requestID = uuid.NewString()
		}

		w.Header().Set("X-Request-ID", requestID)

		ctx := context.WithValue(
			r.Context(),
			requestIDContextKey,
			requestID,
		)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

type contextKey string

const requestIDContextKey contextKey = "request_id"

func loggingMiddleware(
	next http.Handler,
) http.Handler {
	return http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		start := time.Now()

		next.ServeHTTP(w, r)

		requestID, _ := r.Context().Value(
			requestIDContextKey,
		).(string)

		log.Printf(
			"request_id=%s method=%s path=%s duration=%s",
			requestID,
			r.Method,
			r.URL.Path,
			time.Since(start),
		)
	})
}
