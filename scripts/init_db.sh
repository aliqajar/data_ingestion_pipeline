#!/bin/bash
set -e

# This script initializes the TimescaleDB extension

echo "Enabling TimescaleDB extension..."

# Connect to PostgreSQL and execute SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable TimescaleDB extension
    CREATE EXTENSION IF NOT EXISTS timescaledb;
EOSQL

echo "TimescaleDB extension enabled successfully!" 