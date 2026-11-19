package model

import (
	"errors"
	"regexp"
)

var ErrInvalidStrategy = errors.New("invalid deployment strategy: use rolling, blue-green or canary; rolling limits must be 0..2 with at least one nonzero")

type DeploymentStrategy struct {
	Type           string   `json:"type"`
	MaxSurge       int      `json:"max_surge"`
	MaxUnavailable int      `json:"max_unavailable"`
	ReadinessGates []string `json:"readiness_gates,omitempty"`
}

func (s DeploymentStrategy) Normalized() DeploymentStrategy {
	if s.Type == "" {
		s.Type = "rolling"
		s.MaxSurge = 1
		return s
	}
	return s
}
func (s DeploymentStrategy) Progressive() bool { return s.Type == "blue-green" || s.Type == "canary" }
func (s DeploymentStrategy) Validate() error {
	s = s.Normalized()
	if len(s.ReadinessGates) > 4 {
		return ErrInvalidStrategy
	}
	seen := map[string]bool{}
	for _, gate := range s.ReadinessGates {
		if len(gate) > 253 || !regexp.MustCompile(`^[a-z0-9]([a-z0-9.-]*[a-z0-9])?/[A-Za-z0-9]([A-Za-z0-9_.-]*[A-Za-z0-9])?$`).MatchString(gate) || seen[gate] {
			return ErrInvalidStrategy
		}
		seen[gate] = true
	}
	switch s.Type {
	case "rolling":
		if s.MaxSurge < 0 || s.MaxSurge > 2 || s.MaxUnavailable < 0 || s.MaxUnavailable > 2 || s.MaxSurge+s.MaxUnavailable == 0 {
			return ErrInvalidStrategy
		}
	case "blue-green", "canary":
		if s.MaxSurge != 0 || s.MaxUnavailable != 0 {
			return ErrInvalidStrategy
		}
	default:
		return ErrInvalidStrategy
	}
	return nil
}
