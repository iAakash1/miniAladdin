# Authorization

## Roles and permissions

| Permission | USER | ADMIN |
|---|:--:|:--:|
| `analyze` | ✓ | ✓ |
| `use_beginner` | ✓ | ✓ |
| `use_advanced` | ✓ | ✓ |
| `use_explore` | ✓ | ✓ |
| `manage_own_watchlists` | ✓ | ✓ |
| `manage_own_portfolio` | ✓ | ✓ |
| `view_own_history` | ✓ | ✓ |
| `view_admin_diagnostics` | | ✓ |
| `view_agent_evaluation` | | ✓ |
| `manage_system` | | ✓ |

Admin is additive. An operator is not a user with *different* financial
permissions — there are none. There is also no permission to read another
user's data, because no such permission exists: per-user scoping is enforced
in the repositories by filtering on the Clerk-verified id, and a permission
anyone could be granted is the wrong shape for that guarantee.

## How a role is resolved

1. `ADMIN_CLERK_USER_IDS` — the bootstrap path. A fresh deployment has no
   administrator, so nobody could promote the first one.
2. `profiles.role` in Supabase.
3. Otherwise `USER`.

**It fails to the floor.** No database, no profile row, an unrecognised role
string, a query that raises — every unknown resolves to `USER`. A module that
failed towards `ADMIN` would be one outage away from handing out an operator
console.

## Role elevation

There is no API that writes a role. The preferences allowlist has no `role`
field, and the migration defaults every existing row to `user`. Elevation is
an operational act: a direct service-role update, or the bootstrap variable.

## Enforcement

`require_permission(Permission.X)` is a FastAPI dependency. 401 for an
anonymous caller, 403 for a signed-in caller without the capability — a
different answer because it is a different problem, and telling them apart is
the difference between "sign in" and "ask an operator".

Frontend role checks draw navigation. They are not the boundary: every route
re-checks its own permission on every request, and `/api/admin/diagnostics`
refuses an ordinary account that constructs the request by hand.

## Bootstrapping the first administrator

```bash
ADMIN_CLERK_USER_IDS=user_abc123,user_def456
```

Then, to make it durable, set the row directly with the service-role key:

```sql
update public.profiles set role = 'admin' where clerk_user_id = 'user_abc123';
```
