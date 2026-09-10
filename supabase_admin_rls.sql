-- ============================================================
-- PARAKH Admin RLS Policies
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================
-- These policies allow users with role='admin' in the profiles
-- table to read all records (not just their own).
-- The existing owner-scoped policies remain active for inspectors.
-- ============================================================

-- Add new columns to profiles if not using Alembic migrations
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS employee_id VARCHAR(100),
  ADD COLUMN IF NOT EXISTS phone VARCHAR(30),
  ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS ix_profiles_employee_id ON public.profiles (employee_id);

-- ── Admin can read all profiles ───────────────────────────────────────────────
DROP POLICY IF EXISTS profiles_admin_read ON public.profiles;
CREATE POLICY profiles_admin_read ON public.profiles
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'admin'
    )
  );

-- ── Admin can read all inspections ────────────────────────────────────────────
DROP POLICY IF EXISTS inspections_admin_read ON public.inspections;
CREATE POLICY inspections_admin_read ON public.inspections
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'admin'
    )
  );

-- ── Admin can read all extracted_information ──────────────────────────────────
DROP POLICY IF EXISTS extracted_admin_read ON public.extracted_information;
CREATE POLICY extracted_admin_read ON public.extracted_information
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'admin'
    )
  );

-- ── Admin can read all compliance_results ────────────────────────────────────
DROP POLICY IF EXISTS compliance_admin_read ON public.compliance_results;
CREATE POLICY compliance_admin_read ON public.compliance_results
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'admin'
    )
  );

-- ── Admin can read all complaints ────────────────────────────────────────────
DROP POLICY IF EXISTS complaints_admin_read ON public.complaints;
CREATE POLICY complaints_admin_read ON public.complaints
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'admin'
    )
  );

-- ============================================================
-- To provision the first admin account:
-- 1. Create a user in Supabase Auth Dashboard
-- 2. Run:
--    INSERT INTO public.profiles (id, user_id, full_name, email, role, active)
--    VALUES (gen_random_uuid(), '<auth-user-uuid>', 'Admin Name', 'admin@example.com', 'admin', true)
--    ON CONFLICT (user_id) DO UPDATE SET role = 'admin';
-- ============================================================
