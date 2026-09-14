# Supabase Database Migrations

This folder contains raw SQL files for applying schema changes to the Supabase database. This project uses Django ORM for core logic but relies on Supabase for analytics and agent interactions. 

## Process

When you need to make schema changes that belong in Supabase (e.g., changes to the `public` schema rather than the Django-managed `django` schema), follow this consistent process:

1. **Create a SQL file**: Name it sequentially, e.g., `002_add_new_feature.sql`.
2. **Apply Locally**: Run the SQL commands against your local Supabase instance using `psql` or the Supabase Studio UI.
3. **Deploy**: Apply the SQL file by hand before deploying the corresponding backend changes to production.

This aligns with the migration mechanism used in the `Aeropt-agent/db/migrations/` directory.

Django's `manage.py migrate` is exclusively used for the internal `django` schema.
