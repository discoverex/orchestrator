-- Optional utility when Prefect metadata uses an external/shared Postgres instance.
-- Current default stack uses VM-local `prefect-db` container and does not require this script.
-- Run as postgres superuser and replace placeholders before execution.

CREATE USER prefect_user WITH PASSWORD 'REPLACE_ME_PREFECT_PASSWORD';
CREATE DATABASE prefect OWNER prefect_user;
GRANT ALL PRIVILEGES ON DATABASE prefect TO prefect_user;
