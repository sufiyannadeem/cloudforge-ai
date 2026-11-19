package accounts

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type sessionStore interface {
	Login(context.Context, string, string) (Identity, string, error)
	Resolve(context.Context, string) (Identity, error)
	Logout(context.Context, string) error
}

func RegisterRoutes(mux *http.ServeMux, store sessionStore, frontendKey string) {
	keys := map[string]string{"frontend": frontendKey}
	protect := func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Cache-Control", "no-store")
			caller, ok := identity.Verify(r, "project", keys)
			if !ok || !caller.Service() {
				w.WriteHeader(http.StatusUnauthorized)
				return
			}
			next(w, r)
		}
	}
	mux.HandleFunc("POST /internal/auth/login", protect(func(w http.ResponseWriter, r *http.Request) {
		var input struct{ Username, Password string }
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192))
		if err := decoder.Decode(&input); err != nil || decoder.Decode(new(any)) != io.EOF {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		identity, token, err := store.Login(r.Context(), input.Username, input.Password)
		if writeAuthError(w, err) {
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(struct {
			Identity
			Token string `json:"token"`
		}{identity, token})
	}))
	mux.HandleFunc("POST /internal/auth/session", protect(func(w http.ResponseWriter, r *http.Request) {
		token, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
		if !ok {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		identity, err := store.Resolve(r.Context(), token)
		if writeAuthError(w, err) {
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(identity)
	}))
	mux.HandleFunc("POST /internal/auth/logout", protect(func(w http.ResponseWriter, r *http.Request) {
		token, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
		if !ok {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if writeAuthError(w, store.Logout(r.Context(), token)) {
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
}

func writeAuthError(w http.ResponseWriter, err error) bool {
	switch {
	case err == nil:
		return false
	case errors.Is(err, ErrUnauthorized):
		w.WriteHeader(http.StatusUnauthorized)
	case errors.Is(err, ErrBusy):
		w.WriteHeader(http.StatusTooManyRequests)
	default:
		w.WriteHeader(http.StatusServiceUnavailable)
	}
	return true
}
