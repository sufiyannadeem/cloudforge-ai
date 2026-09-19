package workflow

import "fmt"

type Status string

const (
	StatusPending   Status = "pending"
	StatusQueued    Status = "queued"
	StatusRunning   Status = "running"
	StatusSucceeded Status = "succeeded"
	StatusFailed    Status = "failed"
	StatusCancelled Status = "cancelled"
)

func IsValidStatus(status Status) bool {
	switch status {
	case StatusPending,
		StatusQueued,
		StatusRunning,
		StatusSucceeded,
		StatusFailed,
		StatusCancelled:
		return true
	default:
		return false
	}
}

func CanTransition(from, to Status) bool {
	if !IsValidStatus(from) || !IsValidStatus(to) {
		return false
	}

	switch from {
	case StatusPending:
		return to == StatusQueued || to == StatusCancelled

	case StatusQueued:
		return to == StatusRunning || to == StatusCancelled

	case StatusRunning:
		return to == StatusSucceeded ||
			to == StatusFailed ||
			to == StatusCancelled

	case StatusSucceeded, StatusFailed, StatusCancelled:
		return false

	default:
		return false
	}
}

func ValidateTransition(from, to Status) error {
	if !CanTransition(from, to) {
		return fmt.Errorf(
			"invalid deployment status transition: %s -> %s",
			from,
			to,
		)
	}

	return nil
}
