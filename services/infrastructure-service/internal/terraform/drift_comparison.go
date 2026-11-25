package terraform

// Only an explicit set of non-secret numeric/boolean capacity and safety fields
// crosses the API boundary. Raw state, strings, tags, URLs and credentials never do.
// For provider_drift, before/after mean recorded/observed; for desired_change they
// mean observed/desired. Missing, unknown and sensitive fields are omitted.
type DriftComparison struct {
	Field  string `json:"field"`
	Before any    `json:"before"`
	After  any    `json:"after"`
}

func marked(value any, field string) bool {
	if flag, ok := value.(bool); ok {
		return flag
	}
	if fields, ok := value.(map[string]any); ok {
		flag, present := fields[field]
		if !present {
			return false
		}
		if boolean, ok := flag.(bool); ok {
			return boolean
		}
		return true // Unknown marker shapes fail closed.
	}
	return value != nil
}

func safeDriftComparisons(before, after map[string]any, beforeSensitive, afterSensitive, unknown any) []DriftComparison {
	fields := []string{"allocated_storage", "backup_retention_period", "storage_encrypted", "multi_az", "deletion_protection", "publicly_accessible", "enable_dns_support", "enable_dns_hostnames"}
	var result []DriftComparison
	for _, field := range fields {
		if marked(beforeSensitive, field) || marked(afterSensitive, field) || marked(unknown, field) {
			continue
		}
		old, oldOK := before[field]
		next, nextOK := after[field]
		if !oldOK || !nextOK {
			continue
		}
		valid := func(value any) bool {
			if field == "allocated_storage" || field == "backup_retention_period" {
				number, ok := value.(float64)
				return ok && number >= 0 && number <= 1000000 && number == float64(int64(number))
			}
			_, ok := value.(bool)
			return ok
		}
		if valid(old) && valid(next) && old != next {
			result = append(result, DriftComparison{Field: field, Before: old, After: next})
		}
	}
	return result
}
