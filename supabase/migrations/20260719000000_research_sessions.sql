-- Research Sessions (v11) — investigations that survive across weeks.
--
-- Design decision worth stating: workspace state (graph centre, pins,
-- filters, camera, selection, snapshots, activity) lives in ONE jsonb
-- column rather than a dozen typed tables. It is always read and written
-- as a unit, its shape evolves with the workspace, and normalizing it
-- would mean a migration every time a panel gains a setting. The fields
-- that are actually *queried* — title, tags, status, last_opened_at —
-- stay typed columns so listing and search use indexes.
--
-- Notes are the exception: they are individually addressable, searchable
-- and cross-linked, so they get their own table.
--
-- Same identity model as the rest of the persistence layer: Clerk owns
-- identity, every row is scoped by clerk_user_id, RLS denies the
-- anon/authenticated roles outright, and the FastAPI backend is the only
-- client (see 20260718000000_persistence_layer.sql).

create table public.research_sessions (
    id              uuid primary key default gen_random_uuid(),
    clerk_user_id   text not null,
    title           text not null,
    description     text,
    tags            text[] not null default '{}',
    status          text not null default 'active',
    color           text,
    icon            text,
    -- The complete workspace: centre, pins, filters, camera, selection,
    -- snapshots, activity log. Versioned inside the blob (schema_version)
    -- so older sessions can be migrated forward in code, not SQL.
    workspace_state jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    last_opened_at  timestamptz not null default now(),
    constraint research_sessions_status_check
        check (status in ('active', 'archived'))
);

create index research_sessions_user_opened_idx
    on public.research_sessions (clerk_user_id, last_opened_at desc);
create index research_sessions_user_status_idx
    on public.research_sessions (clerk_user_id, status);
-- Tag filtering ("show my semiconductor investigations") without a scan.
create index research_sessions_tags_idx
    on public.research_sessions using gin (tags);

create table public.session_notes (
    id            uuid primary key default gen_random_uuid(),
    session_id    uuid not null references public.research_sessions (id) on delete cascade,
    clerk_user_id text not null,
    body          text not null default '',
    -- Entity / evidence / timeline / graph references, so a note stays
    -- connected to what it is about rather than being loose prose.
    refs          jsonb not null default '[]'::jsonb,
    tags          text[] not null default '{}',
    pinned        boolean not null default false,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index session_notes_session_idx
    on public.session_notes (session_id, created_at desc);
create index session_notes_user_idx on public.session_notes (clerk_user_id);
-- Full-text search across a session's notes.
create index session_notes_body_idx
    on public.session_notes using gin (to_tsvector('english', body));

create trigger research_sessions_set_updated_at
    before update on public.research_sessions
    for each row execute function public.set_updated_at();
create trigger session_notes_set_updated_at
    before update on public.session_notes
    for each row execute function public.set_updated_at();

-- Deny-by-default, exactly as the existing tables: RLS on with no
-- policies, and the PostgREST roles hold no privileges. Only the
-- service-role backend reaches these rows, and it scopes every query by
-- the Clerk-verified user id.
alter table public.research_sessions enable row level security;
alter table public.session_notes     enable row level security;

revoke all on public.research_sessions, public.session_notes
    from anon, authenticated;
