-- Honest Homes — user submissions (unlock leads, project requests, inquiries).
-- Run this once in the Supabase SQL editor.
--
-- Security: Row Level Security is ENABLED with NO public policies, so the
-- anon/public API cannot read or write this table. The backend writes with the
-- service_role key (set as SUPABASE_KEY in the server env), which bypasses RLS.
-- This keeps visitor PII (name/phone) private — only you (dashboard / service
-- key) can read it.

create table if not exists public.submissions (
  id          bigserial primary key,
  type        text not null default 'lead',   -- unlock | request | inquiry
  name        text,
  phone       text,
  project     text,
  project_id  text,
  message     text,
  created_at  timestamptz not null default now()
);

create index if not exists idx_submissions_created on public.submissions (created_at desc);
create index if not exists idx_submissions_type on public.submissions (type);

alter table public.submissions enable row level security;
-- (intentionally no policies: only the service_role key can access the rows)

-- Make sure the anon/public roles can never touch visitor PII, and that the
-- backend's service_role can. These grants are explicit so the table behaves the
-- same whether or not the project has "automatically expose new tables" enabled.
revoke all on public.submissions from anon, authenticated;
grant  all on public.submissions to service_role;
grant  usage, select on sequence public.submissions_id_seq to service_role;
