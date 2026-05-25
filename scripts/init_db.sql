-- SchoolBridge PostgreSQL init script
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- After migrations, run:
-- REVOKE DELETE, UPDATE ON audit_logs FROM schoolbridge_app;
-- GRANT SELECT, INSERT ON audit_logs TO schoolbridge_app;
