package identity

import (
	"errors"
	"github.com/jackc/pgx/v5"
	"strings"
)

// ValidateDatabase confines production runtime identity and forbids TLS fallback.
// Migration credentials are accepted only by the explicit one-shot command.
func ValidateDatabase(environment, dsn, service string, migrate bool) error {
	if environment != "production" {
		return nil
	}
	expected := "cf_" + strings.ReplaceAll(service, "-", "_")
	if migrate {
		expected = "cf_migrator"
	}
	config, err := pgx.ParseConfig(dsn)
	if err != nil || config.User != expected || config.TLSConfig == nil || config.TLSConfig.InsecureSkipVerify || config.TLSConfig.ServerName == "" || strings.HasPrefix(config.Host, "/") {
		return errors.New("production requires a dedicated database principal and hostname-verified TLS")
	}
	for _, fallback := range config.Fallbacks {
		if fallback.TLSConfig == nil || fallback.TLSConfig.InsecureSkipVerify {
			return errors.New("production database TLS fallback is forbidden")
		}
	}
	return nil
}
