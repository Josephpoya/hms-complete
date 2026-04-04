-- HMS database initialisation
-- Runs once when the PostgreSQL container is first started.

-- Sequences for human-readable IDs (used for MRN and invoice numbers)
CREATE SEQUENCE IF NOT EXISTS patients_mrn_seq START 1;
CREATE SEQUENCE IF NOT EXISTS billing_invoice_seq START 1;

-- Revoke default public schema create permission
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Grant required permissions to application user
GRANT USAGE  ON SCHEMA public TO hms_user;
GRANT CREATE ON SCHEMA public TO hms_user;

-- Install extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- Query performance analysis
CREATE EXTENSION IF NOT EXISTS btree_gist;           -- Required for exclusion constraints (appointment overlap)
