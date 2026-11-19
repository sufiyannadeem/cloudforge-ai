package migration

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
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

	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock(719920526321)"); err != nil {
		return err
	}
	if err := createMigrationsTable(ctx, tx); err != nil {
		return err
	}

	files, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return fmt.Errorf("discover migration files: %w", err)
	}

	sort.Strings(files)

	for _, file := range files {
		if err := applyMigration(ctx, tx, file); err != nil {
			return fmt.Errorf("apply migration %s: %w", file, err)
		}
	}

	return tx.Commit(ctx)
}

func createMigrationsTable(ctx context.Context, tx pgx.Tx) error {
	const query = `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version VARCHAR(255) PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`

	if _, err := tx.Exec(ctx, query); err != nil {
		return fmt.Errorf("create schema_migrations table: %w", err)
	}

	return nil
}

func applyMigration(ctx context.Context, tx pgx.Tx, file string) error {
	version := strings.TrimPrefix(file, "migrations/")

	var applied bool

	err := tx.QueryRow(
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

	return nil
}
