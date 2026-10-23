-- Defence in depth for the Django schema on Supabase. Idempotent.
-- Django connects as the table owner, which bypasses RLS, so enabling RLS with no policies
-- only closes the PostgREST/anon/authenticated doors; it does not affect the app.
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'django' LOOP
    EXECUTE format('ALTER TABLE django.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA django FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA django FROM anon, authenticated;
REVOKE USAGE ON SCHEMA django FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA django REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA django REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- Tables created by future migrations get RLS automatically.
CREATE OR REPLACE FUNCTION django.enable_rls_on_new_tables() RETURNS event_trigger
LANGUAGE plpgsql AS $$
DECLARE obj record;
BEGIN
  FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands() WHERE command_tag = 'CREATE TABLE' AND schema_name = 'django' LOOP
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', obj.object_identity);
  END LOOP;
END $$;
DROP EVENT TRIGGER IF EXISTS django_enable_rls;
CREATE EVENT TRIGGER django_enable_rls ON ddl_command_end WHEN TAG IN ('CREATE TABLE')
  EXECUTE FUNCTION django.enable_rls_on_new_tables();

REVOKE EXECUTE ON FUNCTION public.update_updated_at_column() FROM anon, authenticated, PUBLIC;
