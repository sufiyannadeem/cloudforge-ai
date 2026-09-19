package workflow

import "testing"

func TestCanTransition(t *testing.T) {
	tests := []struct {
		name string
		from Status
		to   Status
		want bool
	}{
		{
			name: "pending to queued",
			from: StatusPending,
			to:   StatusQueued,
			want: true,
		},
		{
			name: "queued to running",
			from: StatusQueued,
			to:   StatusRunning,
			want: true,
		},
		{
			name: "running to succeeded",
			from: StatusRunning,
			to:   StatusSucceeded,
			want: true,
		},
		{
			name: "running to failed",
			from: StatusRunning,
			to:   StatusFailed,
			want: true,
		},
		{
			name: "pending to cancelled",
			from: StatusPending,
			to:   StatusCancelled,
			want: true,
		},
		{
			name: "succeeded cannot transition",
			from: StatusSucceeded,
			to:   StatusRunning,
			want: false,
		},
		{
			name: "failed cannot transition",
			from: StatusFailed,
			to:   StatusQueued,
			want: false,
		},
		{
			name: "invalid status",
			from: Status("unknown"),
			to:   StatusRunning,
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := CanTransition(tt.from, tt.to)

			if got != tt.want {
				t.Fatalf(
					"CanTransition(%q, %q) = %v, want %v",
					tt.from,
					tt.to,
					got,
					tt.want,
				)
			}
		})
	}
}

func TestValidateTransition(t *testing.T) {
	if err := ValidateTransition(
		StatusPending,
		StatusQueued,
	); err != nil {
		t.Fatalf("expected valid transition, got error: %v", err)
	}

	if err := ValidateTransition(
		StatusSucceeded,
		StatusRunning,
	); err == nil {
		t.Fatal("expected invalid transition error")
	}
}
