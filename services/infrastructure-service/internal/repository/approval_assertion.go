package repository

import "context"

// ConsumeApprovalAssertion reserves a signed approval nonce across service instances.
func (r *ResourceRepository) ConsumeApprovalAssertion(ctx context.Context, nonce string, expiresAt int64) (bool, error) {
	tag, err := r.pool.Exec(ctx, `
		WITH cleanup AS (
			DELETE FROM infrastructure_approval_assertions WHERE expires_at <= clock_timestamp()
		)
		INSERT INTO infrastructure_approval_assertions (nonce, expires_at)
		SELECT $1, to_timestamp($2::double precision)
		WHERE to_timestamp($2::double precision) > clock_timestamp()
		ON CONFLICT (nonce) DO NOTHING
	`, nonce, float64(expiresAt))
	return err == nil && tag.RowsAffected() == 1, err
}
