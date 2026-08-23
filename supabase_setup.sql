-- Hash Marks — Supabase setup
-- ------------------------------------------------------------
-- Run this once in Supabase: your project → SQL Editor → New query →
-- paste this whole file → Run.
--
-- This creates a single table that stores your ratings, board/games, and
-- bet log as JSON blobs, keyed by name — the same shape the app already
-- uses internally, just stored remotely instead of in browser storage.

create table if not exists app_storage (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

alter table app_storage enable row level security;

-- SECURITY NOTE, read this before running:
-- These policies allow anyone holding your site's public API key (the
-- "anon key") to read and write this table — there's no login/identity
-- check. That key lives directly in your page's source code, so in
-- practice "anyone who has your key" means "anyone who finds your exact
-- site URL and looks at the page source." For a personal tool with picks
-- and units (not financial account info), that's a reasonable tradeoff —
-- but it is NOT the same as a real per-user login system. If you ever
-- want actual access control, Supabase Auth (email/magic-link login) is
-- the next step up — ask if you want that built instead.

create policy "Allow anon read" on app_storage
  for select using (true);

create policy "Allow anon insert" on app_storage
  for insert with check (true);

create policy "Allow anon update" on app_storage
  for update using (true);
