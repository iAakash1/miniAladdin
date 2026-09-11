-- RBAC role + experience mode.
--
-- Two independent dimensions, deliberately stored as two columns on two
-- tables rather than one "account type" field, because they answer different
-- questions and conflating them is how "advanced user" quietly becomes
-- "administrator".
--
--   profiles.role                 WHAT a caller is allowed to do (authorization)
--   user_preferences.experience_mode  HOW the interface is presented
--
-- Entitlement (FREE/PRO) is a third dimension and is not stored here: it
-- lives in Clerk metadata, set server-side after Razorpay verification, and
-- must not be inferred from either column below.
--
-- Additive and safe to re-run. Existing rows take the defaults, which is the
-- point: nobody becomes an administrator by migration, and nobody loses the
-- interface they already use.

-- ── role ────────────────────────────────────────────────────────────────────
-- Default 'user'. There is no application path that writes 'admin' — role
-- elevation is an operational act (a direct service-role update, or the
-- ADMIN_CLERK_USER_IDS bootstrap variable read by src/services/authz.py), so
-- a compromised session cannot grant itself one.
alter table public.profiles
    add column if not exists role text not null default 'user';

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'profiles_role_check'
    ) then
        alter table public.profiles
            add constraint profiles_role_check check (role in ('user', 'admin'));
    end if;
end
$$;

-- ── experience mode ─────────────────────────────────────────────────────────
-- Nullable on purpose: NULL means "this user has never chosen", which is what
-- the onboarding prompt keys off. It is NOT the same as having chosen
-- 'advanced', and the resolver defaults an unset value to 'advanced' so an
-- existing user keeps the terminal they already work in.
alter table public.user_preferences
    add column if not exists experience_mode text;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'user_preferences_experience_mode_check'
    ) then
        alter table public.user_preferences
            add constraint user_preferences_experience_mode_check
            check (experience_mode is null or experience_mode in ('beginner', 'advanced'));
    end if;
end
$$;

-- Administrators are rare and looked up per request; the partial index keeps
-- that lookup cheap without carrying an entry for every ordinary user.
create index if not exists profiles_role_admin_idx
    on public.profiles (clerk_user_id)
    where role = 'admin';
