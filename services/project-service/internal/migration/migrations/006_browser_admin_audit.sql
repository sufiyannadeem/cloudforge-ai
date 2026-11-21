CREATE TABLE account_admin_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nonce text NOT NULL UNIQUE,
 actor text NOT NULL,
 action text NOT NULL,
 username text NOT NULL,
 project_id uuid,
 level text,
 created_at timestamptz NOT NULL DEFAULT now()
);
