package terraform

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

var planCountLine = regexp.MustCompile(`^(?:Terraform plan: |Plan: )?[0-9]+ to add(?:, [0-9]+ to change, [0-9]+ to destroy)?\.?$`)
var planActionLine = regexp.MustCompile(`^(Create|Update|Delete|Replace|Read) (aws|terraform)_[a-z0-9_]{1,64}: [0-9]+$`)
var planResourceType = regexp.MustCompile(`^(aws|terraform)_[a-z0-9_]{1,64}$`)

const incompletePlanSummary = "Some changes could not be summarized."

// PublicPlanSummary allows only action counts and provider resource types across the API.
func PublicPlanSummary(summary string) string {
	lines := make([]string, 0)
	for _, line := range strings.Split(summary, "\n") {
		line = strings.TrimSpace(line)
		switch {
		case line == "No changes.", strings.HasPrefix(line, "No changes. "):
			lines = append(lines, "No changes.")
		case line == incompletePlanSummary, planCountLine.MatchString(line), planActionLine.MatchString(line):
			lines = append(lines, line)
		}
		if len(lines) == 48 {
			break
		}
	}
	return strings.Join(lines, "\n")
}

func summarizeTerraformPlan(output string) string {
	var plan struct {
		ResourceChanges []struct {
			Type   string
			Change struct{ Actions []string }
		} `json:"resource_changes"`
	}
	if err := json.Unmarshal([]byte(output), &plan); err != nil {
		return PublicPlanSummary(output)
	}
	counts := map[string]int{}
	unknown := false
	for _, resource := range plan.ResourceChanges {
		actions := strings.Join(resource.Change.Actions, ",")
		if actions == "no-op" {
			continue
		}
		action := map[string]string{
			"create": "Create", "update": "Update", "delete": "Delete", "read": "Read",
			"delete,create": "Replace", "create,delete": "Replace",
		}[actions]
		if action == "" || !planResourceType.MatchString(resource.Type) {
			unknown = true
			continue
		}
		counts[action+" "+resource.Type]++
	}
	if len(counts) == 0 && !unknown && plan.ResourceChanges != nil {
		return "No changes."
	}
	lines := make([]string, 0, len(counts))
	for action, count := range counts {
		lines = append(lines, fmt.Sprintf("%s: %d", action, count))
	}
	sort.Strings(lines)
	if unknown || len(lines) > 48 {
		lines = append([]string{incompletePlanSummary}, lines...)
	}
	return PublicPlanSummary(strings.Join(lines, "\n"))
}
