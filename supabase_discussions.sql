-- Honest Homes — buyer discussion table
--
-- Run this once in the Supabase SQL editor.
--
-- RLS is on with NO policies granted to anon. That is deliberate and it is the
-- same posture as the leads table: every read and write goes through the API
-- using the service key, so the table is unreachable from a browser even though
-- the posts themselves are shown publicly. Without it, `author_hash` (derived
-- from a phone number) and any post hidden by moderation would be readable by
-- anyone who found the project URL.

create table if not exists public.discussions (
    id            uuid primary key default gen_random_uuid(),
    rera_id       text        not null,
    prompt        text        not null default 'other',
    relation      text        not null default 'other',
    body          text        not null,
    author        text        not null default 'A buyer',
    -- salted sha256 of the poster's phone. Not reversible, never returned by
    -- the API; it exists to spot a repeat poster and to rate-limit abuse.
    author_hash   text,
    status        text        not null default 'visible',
    report_reason text,
    helpful       integer     not null default 0,
    created_at    timestamptz not null default now()
);

-- The only query the product makes: visible posts for one project, newest first.
create index if not exists discussions_project_idx
    on public.discussions (rera_id, status, created_at desc);

alter table public.discussions enable row level security;

-- No grants to anon or authenticated. Service key only.
revoke all on public.discussions from anon, authenticated;

-- Moderation helper: what is waiting for review.
--   select id, rera_id, left(body, 120), report_reason, created_at
--   from public.discussions where status = 'reported' order by created_at desc;
