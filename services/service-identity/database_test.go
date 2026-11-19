package identity

import "testing"

func TestProductionDatabaseBoundary(t *testing.T) {
	for _, dsn := range []string{"postgres://cf_project@db/app?sslmode=disable", "postgres://cf_project@db/app?sslmode=require", "postgres://cf_project@db/app?sslmode=prefer", "postgres://postgres@db/app?sslmode=verify-full", "postgres://cf_deployment@db/app?sslmode=verify-full", "bad dsn"} {
		if ValidateDatabase("production", dsn, "project", false) == nil {
			t.Fatal("unsafe database accepted")
		}
	}
	if err := ValidateDatabase("production", "postgres://cf_project@db/app?sslmode=verify-full", "project", false); err != nil {
		t.Fatal(err)
	}
	if err := ValidateDatabase("production", "postgres://cf_migrator@db/app?sslmode=verify-full", "project", true); err != nil {
		t.Fatal(err)
	}
	if ValidateDatabase("production", "postgres://cf_migrator@db/app?sslmode=verify-full", "project", false) == nil {
		t.Fatal("migration identity accepted at runtime")
	}
	if err := ValidateDatabase("development", "postgres://localhost/app?sslmode=disable", "project", false); err != nil {
		t.Fatal(err)
	}
}
