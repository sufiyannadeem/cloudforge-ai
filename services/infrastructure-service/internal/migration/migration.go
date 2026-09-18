package migration

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

type Runner struct {
	pool *pgxpool.Pool
}

func NewRunner(pool *pgxpool.Pool) *Runner {
	return &Runner{
		pool: pool,
	}
}

func (r *Runner) Run(ctx context.Context) error {
	if r.pool == nil {
		return fmt.Errorf("database pool cannot be nil")
	}

	if err := r.createMigrationsTable(ctx); err != nil {
		return err
	}

	files, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return fmt.Errorf("discover migration files: %w", err)
	}

	sort.Strings(files)

	for _, file := range files {
		if err := r.applyMigration(ctx, file); err != nil {
			return fmt.Errorf("apply migration %s: %w", file, err)
		}
	}

	return nil
}

func (r *Runner) createMigrationsTable(ctx context.Context) error {
	const query = `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version VARCHAR(255) PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`

	if _, err := r.pool.Exec(ctx, query); err != nil {
		return fmt.Errorf("create schema_migrations table: %w", err)
	}

	return nil
}

func (r *Runner) applyMigration(ctx context.Context, file string) error {
	version := strings.TrimPrefix(file, "migrations/")

	var applied bool

	err := r.pool.QueryRow(
		ctx,
		`SELECT EXISTS (
			SELECT 1 FROM schema_migrations WHERE version = $1
		)`,
		version,
	).Scan(&applied)

	if err != nil {
		return fmt.Errorf("check migration status: %w", err)
	}

	if applied {
		return nil
	}

	sqlBytes, err := migrationFiles.ReadFile(file)
	if err != nil {
		return fmt.Errorf("read migration file: %w", err)
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin migration transaction: %w", err)
	}

	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, string(sqlBytes)); err != nil {
		return fmt.Errorf("execute migration SQL: %w", err)
	}

	if _, err := tx.Exec(
		ctx,
		`INSERT INTO schema_migrations (version) VALUES ($1)`,
		version,
	); err != nil {
		return fmt.Errorf("record migration: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit migration transaction: %w", err)
	}

	return nil
}
