DO $$
BEGIN
    CREATE ROLE forge_admin;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'role "forge_admin" already exists, skipping';
END
$$;

ALTER USER forge NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
