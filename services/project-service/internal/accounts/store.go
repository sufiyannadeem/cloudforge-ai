package accounts

import (
	"context"
	"crypto/pbkdf2"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	PlatformEngineer = "platform-engineer"
	SRE              = "sre"
	Developer        = "developer"
	passwordRounds   = 600_000
)

var (
	usernamePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9._@-]{0,127}$`)
	ErrUnauthorized = errors.New("invalid credentials or session")
	ErrBusy         = errors.New("authentication busy")
)

type accountDatabase interface {
	Begin(context.Context) (pgx.Tx, error)
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
	QueryRow(context.Context, string, ...any) pgx.Row
}

type Store struct {
	db       accountDatabase
	hashJobs chan struct{}
}

type Identity struct {
	Username  string  `json:"username"`
	Email     *string `json:"email"`
	Role      string  `json:"role"`
	ExpiresAt int64   `json:"expiresAt"`
}

func NewStore(db *pgxpool.Pool) *Store {
	return &Store{db: db, hashJobs: make(chan struct{}, 4)}
}

func validRole(role string) bool {
	return role == PlatformEngineer || role == SRE || role == Developer
}

func normalizeUsername(username string) string {
	return strings.ToLower(strings.TrimSpace(username))
}

func hashPassword(password string, salt []byte) ([]byte, error) {
	return pbkdf2.Key(sha256.New, password, salt, passwordRounds, 32)
}

func sessionHash(token string) ([32]byte, bool) {
	raw, err := base64.RawURLEncoding.Strict().DecodeString(token)
	return sha256.Sum256(raw), err == nil && len(raw) == 32 && len(token) == 43
}

func (s *Store) Login(ctx context.Context, username, password string) (Identity, string, error) {
	username = normalizeUsername(username)
	if !usernamePattern.MatchString(username) || len(password) == 0 || len(password) > 1024 {
		return Identity{}, "", ErrUnauthorized
	}
	select {
	case s.hashJobs <- struct{}{}:
		defer func() { <-s.hashJobs }()
	default:
		return Identity{}, "", ErrBusy
	}

	tx, err := s.db.Begin(ctx)
	if err != nil {
		return Identity{}, "", err
	}
	defer tx.Rollback(ctx)

	var identity Identity
	var salt, stored []byte
	var version int64
	var active, locked bool
	err = tx.QueryRow(ctx, `
		SELECT role, password_salt, password_hash, session_version, active,
		       COALESCE(login_locked_until > clock_timestamp(), FALSE)
		FROM auth_users WHERE username = $1 FOR UPDATE
	`, username).Scan(&identity.Role, &salt, &stored, &version, &active, &locked)
	if errors.Is(err, pgx.ErrNoRows) {
		// Use the same work factor for unknown usernames.
		_, _ = hashPassword(password, make([]byte, 32))
		return Identity{}, "", ErrUnauthorized
	}
	if err != nil {
		return Identity{}, "", err
	}
	actual, err := hashPassword(password, salt)
	if err != nil {
		return Identity{}, "", err
	}
	if !active || locked {
		return Identity{}, "", ErrUnauthorized
	}
	if subtle.ConstantTimeCompare(actual, stored) != 1 {
		_, err := tx.Exec(ctx, `
			UPDATE auth_users
			SET failed_logins = CASE WHEN failed_logins >= 9 THEN 0 ELSE failed_logins + 1 END,
			    login_locked_until = CASE WHEN failed_logins >= 9 THEN clock_timestamp() + interval '15 minutes' END
			WHERE username = $1
		`, username)
		if err != nil {
			return Identity{}, "", err
		}
		if err := tx.Commit(ctx); err != nil {
			return Identity{}, "", err
		}
		return Identity{}, "", ErrUnauthorized
	}
	if _, err := tx.Exec(ctx, `UPDATE auth_users SET failed_logins = 0, login_locked_until = NULL WHERE username = $1`, username); err != nil {
		return Identity{}, "", err
	}
	// Bound retained expired rows without adding a separate maintenance process.
	if _, err := tx.Exec(ctx, `DELETE FROM auth_sessions WHERE expires_at <= clock_timestamp()`); err != nil {
		return Identity{}, "", err
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return Identity{}, "", err
	}
	digest := sha256.Sum256(raw)
	identity.Username = username
	err = tx.QueryRow(ctx, `
		INSERT INTO auth_sessions (token_hash, username, user_version, expires_at)
		VALUES ($1, $2, $3, clock_timestamp() + interval '8 hours')
		RETURNING floor(extract(epoch FROM expires_at))::bigint
	`, digest[:], username, version).Scan(&identity.ExpiresAt)
	if err != nil {
		return Identity{}, "", err
	}
	if err := tx.Commit(ctx); err != nil {
		return Identity{}, "", err
	}
	return identity, base64.RawURLEncoding.EncodeToString(raw), nil
}

func (s *Store) Resolve(ctx context.Context, token string) (Identity, error) {
	digest, ok := sessionHash(token)
	if !ok {
		return Identity{}, ErrUnauthorized
	}
	var identity Identity
	err := s.db.QueryRow(ctx, `
		SELECT u.username, u.email, u.role, floor(extract(epoch FROM s.expires_at))::bigint
		FROM auth_sessions s JOIN auth_users u ON u.username = s.username
		WHERE s.token_hash = $1 AND s.user_version = u.session_version
		  AND s.expires_at > clock_timestamp() AND u.active
	`, digest[:]).Scan(&identity.Username, &identity.Email, &identity.Role, &identity.ExpiresAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Identity{}, ErrUnauthorized
	}
	return identity, err
}

func (s *Store) Logout(ctx context.Context, token string) error {
	digest, ok := sessionHash(token)
	if !ok {
		return ErrUnauthorized
	}
	_, err := s.db.Exec(ctx, `DELETE FROM auth_sessions WHERE token_hash = $1`, digest[:])
	return err
}
