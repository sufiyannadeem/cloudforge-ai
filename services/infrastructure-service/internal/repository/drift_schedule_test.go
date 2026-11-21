package repository

import (
	"encoding/json"
	"errors"
	"testing"
)

func TestScheduledDriftDoesNotInventHealthyEvidence(t *testing.T) {
	for _, test := range []struct {
		raw    string
		err    error
		status string
		review bool
	}{
		{"[]", nil, "observed", false}, {`[{"severity":"high"}]`, nil, "observed", true},
		{"null", nil, "unavailable", true}, {"", nil, "unavailable", true}, {"{}", nil, "unavailable", true}, {"[]", errors.New("provider unavailable"), "unavailable", true},
	} {
		scan, review := scheduledEvidence(json.RawMessage(test.raw), test.err)
		if scan.Status != test.status || review != test.review || scan.Actor != "service:drift-scheduler" {
			t.Fatal("invalid evidence classification")
		}
	}
}
