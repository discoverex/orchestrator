-- Run as postgres superuser on the shared Postgres instance.
-- Replace placeholders before execution.

CREATE USER prefect_user WITH PASSWORD 'REPLACE_ME_PREFECT_PASSWORD';
CREATE DATABASE prefect OWNER prefect_user;
GRANT ALL PRIVILEGES ON DATABASE prefect TO prefect_user;
