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

type Migration struct {
	Name string
	SQL  string
}

func Run(ctx context.Context, db *pgxpool.Pool) error {
	if err := createMigrationTable(ctx, db); err != nil {
		return fmt.Errorf("create migration table: %w", err)
	}

	migrations, err := loadMigrations()
	if err != nil {
		return fmt.Errorf("load migrations: %w", err)
	}

	for _, currentMigration := range migrations {
		applied, err := isMigrationApplied(
			ctx,
			db,
			currentMigration.Name,
		)

		if err != nil {
			return fmt.Errorf(
				"check migration %s: %w",
				currentMigration.Name,
				err,
			)
		}

		if applied {
			continue
		}

		if err := applyMigration(ctx, db, currentMigration); err != nil {
			return fmt.Errorf(
				"apply migration %s: %w",
				currentMigration.Name,
				err,
			)
		}
	}

	return nil
}

func createMigrationTable(
	ctx context.Context,
	db *pgxpool.Pool,
) error {
	const query = `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version VARCHAR(255) PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`

	_, err := db.Exec(ctx, query)

	return err
}

func loadMigrations() ([]Migration, error) {
	entries, err := fs.ReadDir(migrationFiles, "migrations")
	if err != nil {
		return nil, err
	}

	var migrations []Migration

	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}

		filePath := "migrations/" + entry.Name()

		sqlBytes, err := migrationFiles.ReadFile(filePath)
		if err != nil {
			return nil, fmt.Errorf(
				"read %s: %w",
				entry.Name(),
				err,
			)
		}

		migrations = append(migrations, Migration{
			Name: entry.Name(),
			SQL:  string(sqlBytes),
		})
	}

	sort.Slice(migrations, func(i, j int) bool {
		return migrations[i].Name < migrations[j].Name
	})

	return migrations, nil
}

func isMigrationApplied(
	ctx context.Context,
	db *pgxpool.Pool,
	version string,
) (bool, error) {
	const query = `
		SELECT EXISTS (
			SELECT 1
			FROM schema_migrations
			WHERE version = $1
		)
	`

	var exists bool

	err := db.QueryRow(ctx, query, version).Scan(&exists)

	return exists, err
}

func applyMigration(
	ctx context.Context,
	db *pgxpool.Pool,
	currentMigration Migration,
) error {
	tx, err := db.Begin(ctx)
	if err != nil {
		return err
	}

	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, currentMigration.SQL); err != nil {
		return err
	}

	const insertQuery = `
		INSERT INTO schema_migrations (version)
		VALUES ($1)
	`

	if _, err := tx.Exec(
		ctx,
		insertQuery,
		currentMigration.Name,
	); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return err
	}

	return nil
}
