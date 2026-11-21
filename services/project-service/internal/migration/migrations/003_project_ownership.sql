ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS created_by TEXT REFERENCES auth_users(username);

CREATE INDEX IF NOT EXISTS projects_created_by_idx ON projects (created_by);

CREATE TABLE IF NOT EXISTS project_members (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    username TEXT NOT NULL REFERENCES auth_users(username) ON DELETE CASCADE,
    level TEXT NOT NULL CHECK (level IN ('maintainer', 'viewer')),
    PRIMARY KEY (project_id, username)
);

CREATE INDEX IF NOT EXISTS project_members_username_idx ON project_members (username, project_id);
