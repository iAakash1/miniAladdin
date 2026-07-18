-- OmniSignal persistence layer (v3.5)
--
-- Identity model: Clerk remains the only authentication system. Every row is
-- scoped by clerk_user_id (Clerk's `user_...` id, TEXT). Supabase Auth is not
-- used, so RLS cannot key off auth.uid(); instead RLS is enabled with NO
-- policies for the anon/authenticated PostgREST roles (deny-by-default) and
-- their privileges are revoked outright. The only client is the FastAPI
-- backend using the service-role key, which enforces per-user scoping in the
-- repository layer (src/services/database/). The browser never talks to
-- Supabase directly.

-- ── profiles ────────────────────────────────────────────────────────────────
create table public.profiles (
    id            uuid primary key default gen_random_uuid(),
    clerk_user_id text not null unique,
    email         text,
    full_name     text,
    avatar_url    text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- ── watchlists ──────────────────────────────────────────────────────────────
create table public.watchlists (
    id            uuid primary key default gen_random_uuid(),
    clerk_user_id text not null,
    name          text not null,
    created_at    timestamptz not null default now()
);

create index watchlists_clerk_user_id_idx on public.watchlists (clerk_user_id);

create table public.watchlist_items (
    id           uuid primary key default gen_random_uuid(),
    watchlist_id uuid not null references public.watchlists (id) on delete cascade,
    ticker       text not null,
    added_at     timestamptz not null default now(),
    constraint watchlist_items_unique unique (watchlist_id, ticker)
);

create index watchlist_items_watchlist_id_idx on public.watchlist_items (watchlist_id);

-- ── analysis_history ────────────────────────────────────────────────────────
-- One row per completed /api/research run. quant_payload stores the COMPLETE
-- deterministic research response (scorecard, factors, macro, sentiment,
-- technicals) so any past analysis can be re-rendered and compared without
-- recomputation; ai_report duplicates the narrative block for direct access.
create table public.analysis_history (
    id              uuid primary key default gen_random_uuid(),
    clerk_user_id   text not null,
    ticker          text not null,
    company_name    text,
    verdict         text not null,
    confidence      integer,
    risk_level      text,
    composite_score double precision,
    quant_payload   jsonb,
    ai_report       jsonb,
    created_at      timestamptz not null default now()
);

create index analysis_history_user_created_idx
    on public.analysis_history (clerk_user_id, created_at desc);
create index analysis_history_user_ticker_idx
    on public.analysis_history (clerk_user_id, ticker);
create index analysis_history_ticker_idx on public.analysis_history (ticker);
create index analysis_history_created_at_idx on public.analysis_history (created_at);

-- ── saved_reports ───────────────────────────────────────────────────────────
create table public.saved_reports (
    id                  uuid primary key default gen_random_uuid(),
    analysis_history_id uuid not null references public.analysis_history (id) on delete cascade,
    clerk_user_id       text not null,
    custom_title        text,
    notes               text,
    saved_at            timestamptz not null default now(),
    constraint saved_reports_unique unique (clerk_user_id, analysis_history_id)
);

create index saved_reports_user_saved_idx
    on public.saved_reports (clerk_user_id, saved_at desc);

-- ── portfolio_positions ─────────────────────────────────────────────────────
create table public.portfolio_positions (
    id            uuid primary key default gen_random_uuid(),
    clerk_user_id text not null,
    ticker        text not null,
    shares        double precision not null check (shares > 0),
    average_price double precision not null check (average_price >= 0),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint portfolio_positions_unique unique (clerk_user_id, ticker)
);

create index portfolio_positions_user_idx on public.portfolio_positions (clerk_user_id);

-- ── user_preferences ────────────────────────────────────────────────────────
create table public.user_preferences (
    id                       uuid primary key default gen_random_uuid(),
    clerk_user_id            text not null unique,
    theme                    text,
    default_watchlist        uuid references public.watchlists (id) on delete set null,
    default_analysis_horizon text,
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now()
);

-- ── updated_at maintenance ──────────────────────────────────────────────────
create function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger profiles_set_updated_at
    before update on public.profiles
    for each row execute function public.set_updated_at();
create trigger portfolio_positions_set_updated_at
    before update on public.portfolio_positions
    for each row execute function public.set_updated_at();
create trigger user_preferences_set_updated_at
    before update on public.user_preferences
    for each row execute function public.set_updated_at();

-- ── Row-level security: deny-by-default ─────────────────────────────────────
-- RLS on + zero policies means the anon/authenticated PostgREST roles can
-- read and write NOTHING. The service-role connection (FastAPI only) bypasses
-- RLS by design; per-user scoping is enforced in the repository layer against
-- the Clerk-verified user id.
alter table public.profiles            enable row level security;
alter table public.watchlists          enable row level security;
alter table public.watchlist_items     enable row level security;
alter table public.analysis_history    enable row level security;
alter table public.saved_reports       enable row level security;
alter table public.portfolio_positions enable row level security;
alter table public.user_preferences    enable row level security;

revoke all on public.profiles,
              public.watchlists,
              public.watchlist_items,
              public.analysis_history,
              public.saved_reports,
              public.portfolio_positions,
              public.user_preferences
    from anon, authenticated;
