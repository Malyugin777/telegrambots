-- Add api_source column to action_logs table
ALTER TABLE action_logs ADD COLUMN IF NOT EXISTS api_source VARCHAR(20);
CREATE INDEX IF NOT EXISTS ix_action_logs_api_source ON action_logs(api_source);
