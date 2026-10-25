-- Tracker, alerts, notifications and paper-order references.
--
-- Additive only: existing watchlists and items keep their rows and gain
-- columns with defaults; nothing is dropped or rewritten. Every table is
-- reached only by the backend's service role, as before: row-level security is
-- enabled with no policy, so the anon and authenticated roles see nothing, and
-- every query in the repositories filters on the Clerk-verified user id.

-- ── watchlists: order, default list, preferred sort ─────────────────────────
alter table public.watchlists add column if not exists position   integer     not null default 0;
alter table public.watchlists add column if not exists is_default boolean     not null default false;
alter table public.watchlists add column if not exists sort_key   text        not null default 'manual';
alter table public.watchlists add column if not exists updated_at timestamptz not null default now();

alter table public.watchlists drop constraint if exists watchlists_sort_key_check;
alter table public.watchlists add constraint watchlists_sort_key_check
    check (sort_key in ('manual', 'symbol', 'change', 'change_pct', 'perf_1m', 'perf_1y', 'updated', 'alerts'));

-- At most one default list per user.
create unique index if not exists watchlists_one_default_per_user
    on public.watchlists (clerk_user_id) where is_default;

-- ── watchlist items: order, note, tags ──────────────────────────────────────
alter table public.watchlist_items add column if not exists position integer not null default 0;
alter table public.watchlist_items add column if not exists note     text;
alter table public.watchlist_items add column if not exists tags     text[]  not null default '{}';

alter table public.watchlist_items drop constraint if exists watchlist_items_note_length;
alter table public.watchlist_items add constraint watchlist_items_note_length
    check (note is null or char_length(note) <= 500);
alter table public.watchlist_items drop constraint if exists watchlist_items_tag_count;
alter table public.watchlist_items add constraint watchlist_items_tag_count
    check (cardinality(tags) <= 8);

-- ── price alerts ─────────────────────────────────────────────────────────────
create table if not exists public.price_alerts (
    id                  uuid primary key default gen_random_uuid(),
    clerk_user_id       text not null,
    ticker              text not null,
    kind                text not null check (kind in (
                            'cross_above', 'cross_below', 'day_move', 'period_move', 'range_exit', 'new_filing')),
    threshold           double precision,
    threshold_high      double precision,
    direction           text check (direction in ('up', 'down', 'either')),
    period_days         integer check (period_days is null or period_days between 2 and 260),
    form_types          text[] not null default '{}',
    status              text not null default 'active' check (status in ('active', 'paused', 'triggered')),
    repeat              boolean not null default false,
    armed               boolean not null default true,
    note                text check (note is null or char_length(note) <= 280),
    -- The last observation the evaluator actually used, and what it concluded.
    baseline_value      double precision,
    baseline_text       text,
    last_evaluated_at   timestamptz,
    last_observed_value double precision,
    last_observed_at    timestamptz,
    last_source         text,
    last_result         text,
    last_triggered_at   timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists price_alerts_user_idx   on public.price_alerts (clerk_user_id);
create index if not exists price_alerts_active_idx on public.price_alerts (status) where status = 'active';

-- ── alert events: one row per trigger, deduplicated by key ──────────────────
-- `event_key` names the alert and the observation that triggered it, so a
-- scheduler retry or two overlapping runs that see the same observation
-- insert one row, not two.
create table if not exists public.alert_events (
    id               uuid primary key default gen_random_uuid(),
    event_key        text not null unique,
    alert_id         uuid references public.price_alerts (id) on delete set null,
    clerk_user_id    text not null,
    ticker           text not null,
    kind             text not null,
    condition_text   text not null,
    observed_value   double precision,
    observed_text    text,
    threshold        double precision,
    source           text,
    source_timestamp timestamptz,
    freshness        text check (freshness in ('live', 'delayed', 'end_of_day', 'stale')),
    triggered_at     timestamptz not null default now()
);

create index if not exists alert_events_user_idx on public.alert_events (clerk_user_id, triggered_at desc);

-- ── notifications: the in-app inbox ─────────────────────────────────────────
create table if not exists public.notifications (
    id            uuid primary key default gen_random_uuid(),
    clerk_user_id text not null,
    event_id      uuid unique references public.alert_events (id) on delete cascade,
    kind          text not null default 'alert',
    title         text not null,
    body          text,
    link          text,
    read_at       timestamptz,
    created_at    timestamptz not null default now()
);

create index if not exists notifications_user_idx on public.notifications (clerk_user_id, created_at desc);

-- ── paper-order references ───────────────────────────────────────────────────
-- An audit and reconciliation record, not a ledger: the broker is the source
-- of truth for status, fills and positions. What this keeps is what the broker
-- cannot: which operator submitted the order, and the client order id needed
-- to find it again after a timeout.
create table if not exists public.paper_orders (
    id                 uuid primary key default gen_random_uuid(),
    clerk_user_id      text not null,
    client_order_id    text not null unique check (char_length(client_order_id) between 8 and 128),
    broker_order_id    text,
    symbol             text not null,
    side               text not null check (side in ('buy', 'sell')),
    order_type         text not null check (order_type in ('market', 'limit')),
    time_in_force      text not null,
    qty                double precision,
    notional           double precision,
    limit_price        double precision,
    origin             text check (origin in ('ticket', 'watchlist', 'research', 'position')),
    last_status        text not null default 'submitting',
    last_error         text,
    submitted_at       timestamptz not null default now(),
    last_reconciled_at timestamptz,
    updated_at         timestamptz not null default now()
);

create index if not exists paper_orders_user_idx on public.paper_orders (clerk_user_id, submitted_at desc);

alter table public.price_alerts  enable row level security;
alter table public.alert_events  enable row level security;
alter table public.notifications enable row level security;
alter table public.paper_orders  enable row level security;
