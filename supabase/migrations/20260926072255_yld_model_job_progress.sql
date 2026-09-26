-- Persist the worker's current step so the dashboard never guesses progress.
ALTER TABLE yld.model_jobs
  ADD COLUMN IF NOT EXISTS stage text NOT NULL DEFAULT 'queued';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'model_jobs_stage_check'
      AND conrelid = 'yld.model_jobs'::regclass
  ) THEN
    ALTER TABLE yld.model_jobs
      ADD CONSTRAINT model_jobs_stage_check
      CHECK (stage IN ('queued', 'analyzing', 'training', 'validating', 'promoting', 'complete'));
  END IF;
END $$;
