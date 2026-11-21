ALTER TABLE auth_users ADD COLUMN email TEXT
    CHECK (octet_length(email) <= 254 AND email ~ '^[^[:space:]@<>]+@[^[:space:]@<>]+[.][^[:space:]@<>]+$');
