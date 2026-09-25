CREATE INDEX IF NOT EXISTS accounts_workspace_id ON yld.accounts(workspace_id);
CREATE INDEX IF NOT EXISTS workspace_history_dish ON yld.workspace_history(workspace_id, dish_id);
