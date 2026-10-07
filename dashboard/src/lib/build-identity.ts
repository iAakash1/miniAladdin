/**
 * Which build is answering.
 *
 * Public by design and limited to values that identify a build without
 * granting anything: commit, branch, environment, Vercel deployment id and
 * build time. Never a token, a URL with credentials, or an environment dump.
 *
 * `commit` reads "unknown" for a build with no git metadata — a CLI deploy, a
 * local build — and is never guessed. Absent values are null, not empty
 * strings, so a consumer can tell "not recorded" from "recorded as blank".
 */
export interface BuildIdentity {
  service: 'frontend'
  commit: string
  ref: string | null
  environment: string | null
  deployment: string | null
  built_at: string | null
}

type Env = Record<string, string | undefined>

const present = (value: string | undefined): string | null => (value && value.trim() ? value.trim() : null)

export function buildIdentity(env: Env): BuildIdentity {
  return {
    service: 'frontend',
    commit: present(env.NEXT_PUBLIC_BUILD_SHA) ?? 'unknown',
    ref: present(env.NEXT_PUBLIC_BUILD_REF),
    environment: present(env.NEXT_PUBLIC_BUILD_ENV),
    deployment: present(env.NEXT_PUBLIC_BUILD_DEPLOYMENT),
    built_at: present(env.NEXT_PUBLIC_BUILD_TIME),
  }
}
