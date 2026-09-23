ALTER TABLE repositories ADD COLUMN IF NOT EXISTS indexing_stage VARCHAR(50) NOT NULL DEFAULT 'queued';
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS indexing_progress INTEGER NOT NULL DEFAULT 0;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS indexing_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS indexing_heartbeat_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE repositories DROP CONSTRAINT IF EXISTS uq_repositories_repository_url;
CREATE UNIQUE INDEX IF NOT EXISTS uq_repositories_workspace_url ON repositories (workspace_id, repository_url);
