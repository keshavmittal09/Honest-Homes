-- Run this ONLY if you already created public.discussions before threading.
-- Safe to run more than once.

alter table public.discussions
    add column if not exists parent_id uuid
    references public.discussions(id) on delete set null;

create index if not exists discussions_recent_idx
    on public.discussions (status, parent_id, created_at desc);
