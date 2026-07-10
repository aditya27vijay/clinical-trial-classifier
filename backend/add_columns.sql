-- Add missing columns to molecules
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS resolution_method VARCHAR(30);
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS resolution_conflict BOOLEAN DEFAULT FALSE;
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS is_combination BOOLEAN DEFAULT FALSE;
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS combination_components JSON;
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS drugbank_id VARCHAR(20);
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30);
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS first_studied DATE;
ALTER TABLE molecules ADD COLUMN IF NOT EXISTS last_active DATE;

CREATE INDEX IF NOT EXISTS ix_molecules_drugbank_id ON molecules (drugbank_id);

-- Add missing columns to molecule_trials
ALTER TABLE molecule_trials ADD COLUMN IF NOT EXISTS sponsor VARCHAR(300);
ALTER TABLE molecule_trials ADD COLUMN IF NOT EXISTS status VARCHAR(50);
ALTER TABLE molecule_trials ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE molecule_trials ADD COLUMN IF NOT EXISTS completion_date DATE;
ALTER TABLE molecule_trials ADD COLUMN IF NOT EXISTS why_stopped TEXT;