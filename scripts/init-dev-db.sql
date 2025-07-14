-- Development database initialization script
-- This runs when the PostgreSQL container is first created

-- Enable useful extensions for development
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create a test schema for experimentation
CREATE SCHEMA IF NOT EXISTS test_schema;

-- Set up development-friendly settings
ALTER DATABASE chronovista_dev SET timezone = 'UTC';
ALTER DATABASE chronovista_dev SET log_statement = 'all';
ALTER DATABASE chronovista_dev SET log_min_duration_statement = 0;

-- Grant permissions to dev user
GRANT ALL PRIVILEGES ON DATABASE chronovista_dev TO dev_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO dev_user;
GRANT ALL PRIVILEGES ON SCHEMA test_schema TO dev_user;

-- Create a simple function to reset all tables (useful for testing)
CREATE OR REPLACE FUNCTION reset_all_tables()
RETURNS void AS $$
BEGIN
    -- This will be useful during model development
    EXECUTE (
        SELECT string_agg('DROP TABLE IF EXISTS ' || tablename || ' CASCADE;', ' ')
        FROM pg_tables 
        WHERE schemaname = 'public'
    );
    RAISE NOTICE 'All tables dropped and reset complete';
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission on the function
GRANT EXECUTE ON FUNCTION reset_all_tables() TO dev_user;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'chronovista development database initialized successfully';
    RAISE NOTICE 'Use reset_all_tables() to clear all tables during development';
END $$;