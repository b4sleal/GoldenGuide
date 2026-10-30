-- LOCAL DEVELOPMENT ONLY: create GoldenGuide's databases on the Compose Postgres server.
--
-- Run by the `db-bootstrap` service on every `docker compose up`. Idempotent: databases that
-- already exist are skipped, so it is safe on a fresh or an existing volume.
--
-- In staging/production the database is created by infrastructure code (Terraform/CDK for RDS)
-- or the DBA, never by this script, and never by the application.
--
--   goldenguide       development data, used by the running stack
--   goldenguide_test  integration tests; tests may wipe it at any time
--
-- Tables are NOT created here; the provision job's Alembic migrations do that.
--
-- Usage: psql -v databases=goldenguide,goldenguide_test -f bootstrap.sql

-- For each requested name that doesn't exist yet, build a CREATE DATABASE statement...
SELECT format('CREATE DATABASE %I', name)              -- %I quotes the name safely as an identifier
FROM unnest(string_to_array(:'databases', ',')) AS name
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = name)
-- ...and execute each one. (CREATE DATABASE cannot run inside a function or DO block,
-- so psql's \gexec is the standard way to make it conditional.)
\gexec
