-- Add the third presentation density without changing existing preferences.
-- Role and entitlement remain independent columns/systems.

alter table public.user_preferences
    drop constraint if exists user_preferences_experience_mode_check;

alter table public.user_preferences
    add constraint user_preferences_experience_mode_check
    check (
        experience_mode is null
        or experience_mode in ('beginner', 'intermediate', 'advanced')
    );
