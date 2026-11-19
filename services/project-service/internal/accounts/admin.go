package accounts

import (
	"context"
	"crypto/rand"
	"errors"
	"io"
	"net/mail"
	"regexp"
	"strings"
)

func legacyRole(role string) string {
	switch role {
	case SRE:
		return SRE
	case "viewer", "devops", "admin", PlatformEngineer:
		return Developer
	default:
		return ""
	}
}

// Admin is invoked locally by an operator with database access.
func (s *Store) Admin(ctx context.Context, args []string, input io.Reader) error {
	usage := errors.New("usage: account bootstrap|deactivate|activate|revoke USER, or account create|set-role|import-legacy USER ROLE, or account set-email USER EMAIL; use an empty EMAIL to clear it; bootstrap/create/import-legacy read the password from stdin")
	if len(args) < 2 || len(args) > 3 {
		return usage
	}
	action, username := args[0], normalizeUsername(args[1])
	if !usernamePattern.MatchString(username) {
		return errors.New("invalid username")
	}

	var role string
	switch action {
	case "set-email":
		if len(args) != 3 {
			return usage
		}
		email, err := optionalEmail(args[2])
		if err != nil {
			return err
		}
		result, err := s.db.Exec(ctx, "UPDATE auth_users SET email = $2 WHERE username = $1", username, email)
		if err == nil && result.RowsAffected() != 1 {
			return errors.New("account not found")
		}
		return err
	case "bootstrap", "activate", "deactivate", "revoke":
		if len(args) != 2 {
			return usage
		}
		role = PlatformEngineer
	case "create", "set-role", "import-legacy":
		if len(args) != 3 {
			return usage
		}
		role = args[2]
		if action == "import-legacy" {
			role = legacyRole(role)
		}
		if !validRole(role) {
			return errors.New("unsupported account role")
		}
	default:
		return usage
	}

	switch action {
	case "bootstrap", "create", "import-legacy":
		raw, err := io.ReadAll(io.LimitReader(input, 1026))
		if err != nil {
			return errors.New("could not read password from stdin")
		}
		password := strings.TrimSuffix(strings.TrimSuffix(string(raw), "\n"), "\r")
		if len(password) < 15 || len(password) > 1024 || strings.ContainsAny(password, "\r\n\x00") {
			return errors.New("password must be one line of 15 to 1024 bytes")
		}
		return s.create(ctx, username, role, password, action == "bootstrap")
	default:
		return s.update(ctx, username, action, role)
	}
}

func (s *Store) create(ctx context.Context, username, role, password string, bootstrap bool) error {
	salt := make([]byte, 32)
	if _, err := rand.Read(salt); err != nil {
		return err
	}
	hash, err := hashPassword(password, salt)
	if err != nil {
		return err
	}
	tx, err := s.db.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if bootstrap {
		// Block competing inserts until this empty-store check commits.
		if _, err := tx.Exec(ctx, `LOCK TABLE auth_users IN SHARE ROW EXCLUSIVE MODE`); err != nil {
			return err
		}
	}
	tag, err := tx.Exec(ctx, `
		INSERT INTO auth_users (username, role, password_hash, password_salt)
		SELECT $1::text, $2::text, $3::bytea, $4::bytea
		WHERE NOT $5::boolean OR NOT EXISTS (SELECT 1 FROM auth_users)
		ON CONFLICT (username) DO NOTHING
	`, username, role, hash, salt, bootstrap)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return errors.New("account already exists or bootstrap has closed")
	}
	return tx.Commit(ctx)
}

func (s *Store) update(ctx context.Context, username, action, role string) error {
	tag, err := s.db.Exec(ctx, `
		UPDATE auth_users
		SET session_version = session_version + 1,
		    role = CASE WHEN $2 = 'set-role' THEN $3 ELSE role END,
		    active = CASE WHEN $2 = 'activate' THEN TRUE WHEN $2 = 'deactivate' THEN FALSE ELSE active END,
		    failed_logins = 0, login_locked_until = NULL
		WHERE username = $1
	`, username, action, role)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return errors.New("account not found")
	}
	return nil
}

var emailShape = regexp.MustCompile(`^[A-Za-z0-9.!#$%&'*+/=?^_{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$`)

func optionalEmail(input string) (*string, error) {
	if input == "" {
		return nil, nil
	}
	if len(input) <= 254 && strings.IndexByte(input, '@') <= 64 && emailShape.MatchString(input) {
		if address, err := mail.ParseAddress(input); err == nil && address.Address == input && address.Name == "" {
			return &input, nil
		}
	}
	return nil, errors.New("invalid email address")
}
