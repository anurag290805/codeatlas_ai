-- Existing rows remain quarantined (workspace_id IS NULL) until an operator
-- verifies their rightful account. Never backfill all legacy rows to one
-- shared/public workspace.
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS ix_repositories_workspace_id ON repositories (workspace_id);
-- PostgreSQL production migration: replace the old global uniqueness rule.
ALTER TABLE repositories DROP CONSTRAINT IF EXISTS uq_repositories_repository_url;
ALTER TABLE repositories ADD CONSTRAINT uq_repositories_workspace_url UNIQUE (workspace_id, repository_url);

-- Controlled example:
-- UPDATE repositories SET workspace_id = '<verified-workspace-id>'
-- WHERE id IN (<verified-repository-ids>) AND workspace_id IS NULL;
