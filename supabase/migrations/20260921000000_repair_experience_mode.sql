-- PROD-DEFECT-002: idempotent repair for deployments that did not apply the
-- original experience-mode migration. This migration contains no data or
-- credentials and is safe to apply after either predecessor.

alter table public.user_preferences
    add column if not exists experience_mode text;

alter table public.user_preferences
    drop constraint if exists user_preferences_experience_mode_check;

alter table public.user_preferences
    add constraint user_preferences_experience_mode_check
    check (
        experience_mode is null
        or experience_mode in ('beginner', 'intermediate', 'advanced')
    );
