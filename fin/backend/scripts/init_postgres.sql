-- Execute como superusuário (postgres) para criar o banco localmente.
-- Exemplo: psql -U postgres -f backend/scripts/init_postgres.sql

CREATE USER fin WITH PASSWORD 'fin';

CREATE DATABASE fin OWNER fin;

GRANT ALL PRIVILEGES ON DATABASE fin TO fin;
