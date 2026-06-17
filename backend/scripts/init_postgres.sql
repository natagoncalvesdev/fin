-- Schema do Fin (PostgreSQL)
-- Uso: psql -U postgres -f backend/scripts/init_postgres.sql

CREATE USER fin WITH PASSWORD 'fin';

CREATE DATABASE fin OWNER fin;

GRANT ALL PRIVILEGES ON DATABASE fin TO fin;

-- Tabelas criadas automaticamente pelo SQLAlchemy (create_all).
-- Referência:
--   usuario, categoria, conta, entrada, cartao, compra_cartao,
--   debito, reservado, fatura_cartao,
--   veiculo, veiculo_historico, veiculo_abastecimento, manutencao_veiculo
