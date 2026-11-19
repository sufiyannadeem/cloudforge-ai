// Isolated integration client. Never installed in a production image.
package main

import (
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"os"
	"time"
)

func main() {
	if err := check(); err != nil {
		fmt.Fprintln(os.Stderr, "database boundary check failed")
		os.Exit(1)
	}
}
func check() error {
	service := os.Getenv("CHECK_SERVICE")
	dsn := os.Getenv("DATABASE_URL")
	if err := identity.ValidateDatabase("production", dsn, service, false); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	conn, err := pgx.Connect(ctx, dsn)
	if err != nil {
		return err
	}
	defer conn.Close(ctx)
	var encrypted bool
	if err = conn.QueryRow(ctx, "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").Scan(&encrypted); err != nil || !encrypted {
		return fmt.Errorf("TLS required")
	}
	allowed := map[string][]string{
		"project":        {"SELECT username FROM auth_users LIMIT 1", "INSERT INTO account_admin_audit(nonce,actor,action,username) VALUES (gen_random_uuid()::text,'fixture','verify','fixture')"},
		"infrastructure": {"SELECT id FROM infrastructure_resources LIMIT 1", "UPDATE infrastructure_resources SET status=status WHERE false"},
		"deployment":     {"SELECT username,role,active FROM auth_users LIMIT 1", "UPDATE aiops_remediation_proposals SET dispatch_consumed_at=clock_timestamp() WHERE false", "SELECT * FROM deployment_diagnostics LIMIT 1"},
		"aiops":          {"SELECT * FROM aiops_incidents LIMIT 1", "UPDATE aiops_incidents SET status=status WHERE false"},
		"finops_project": {"SELECT id FROM infrastructure_resources LIMIT 1", "SELECT project_id,username FROM project_members LIMIT 1"},
		"finops_audit":   {"INSERT INTO finops_anomaly_captures VALUES (gen_random_uuid(),'123456789012','fixture',now(),'{}')"},
	}
	queries, ok := allowed[service]
	if !ok {
		return fmt.Errorf("unknown service")
	}
	for _, sql := range queries {
		if _, err = conn.Exec(ctx, sql); err != nil {
			return err
		}
	}
	denied := []string{"CREATE TABLE forbidden_fixture(id int)", "SET ROLE cf_migrator", "UPDATE schema_migrations SET version=version WHERE false"}
	if service != "project" {
		denied = append(denied, "SELECT password_hash FROM auth_users LIMIT 1", "UPDATE auth_users SET role='platform-engineer' WHERE false", "SELECT * FROM auth_sessions LIMIT 1")
	}
	if service == "deployment" {
		denied = append(denied, "UPDATE aiops_remediation_proposals SET approved_by='forged' WHERE false")
	}
	if service == "finops_project" {
		denied = append(denied, "SELECT configuration FROM infrastructure_resources LIMIT 1", "DELETE FROM infrastructure_resources WHERE false")
	}
	if service == "finops_audit" {
		denied = append(denied, "UPDATE finops_anomaly_captures SET actor='forged' WHERE false")
	}
	for _, sql := range denied {
		_, err = conn.Exec(ctx, sql)
		if err == nil {
			return fmt.Errorf("forbidden query accepted")
		}
		if e, ok := err.(interface{ SQLState() string }); !ok || e.SQLState() != "42501" {
			return fmt.Errorf("expected permission denial")
		}
	}
	fmt.Println("verified TLS and scoped grants:", service)
	return nil
}
