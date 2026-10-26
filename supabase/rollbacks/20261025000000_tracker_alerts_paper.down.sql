-- Reverses 20261025000000_tracker_alerts_paper.sql.
--
-- Not a migration: Supabase applies files in migrations/ only. Run it by hand,
-- and only after the backend that reads these columns and tables has been
-- rolled back, because it removes them. Watchlists and their items keep every
-- row; what is lost is what the forward migration added — list order, the
-- default flag, the preferred sort, item notes and tags, alerts, their trigger
-- history, the inbox, and paper-order references (the broker still holds the
-- orders themselves).

drop table if exists public.notifications;
drop table if exists public.alert_events;
drop table if exists public.price_alerts;
drop table if exists public.paper_orders;

drop index if exists public.watchlists_one_default_per_user;

alter table public.watchlist_items drop constraint if exists watchlist_items_tag_count;
alter table public.watchlist_items drop constraint if exists watchlist_items_note_length;
alter table public.watchlist_items drop column if exists tags;
alter table public.watchlist_items drop column if exists note;
alter table public.watchlist_items drop column if exists position;

alter table public.watchlists drop constraint if exists watchlists_sort_key_check;
alter table public.watchlists drop column if exists updated_at;
alter table public.watchlists drop column if exists sort_key;
alter table public.watchlists drop column if exists is_default;
alter table public.watchlists drop column if exists position;
