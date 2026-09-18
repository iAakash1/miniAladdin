'use client'

/** Session-scoped reads for private API resources. */

import { authFetch, authSessionScope } from './persistence'
import {
  clearResourceCachePrefix,
  readResource,
  type Policy,
} from './resource'

const PRIVATE_PREFIX = 'auth:'

function sessionPrefix(scope: string): string {
  return `${PRIVATE_PREFIX}${encodeURIComponent(scope)}:`
}

/**
 * Read a protected JSON resource with the same TTL, single-flight, bounded
 * cache and failure-not-cached semantics as `readResource`.
 *
 * The key includes Clerk's session (or user) id. When neither is available,
 * caching is disabled. A private response can therefore never be reused by a
 * later browser session merely because the URL is the same.
 */
export function readAuthResource<T>(url: string, policy: Policy = 'artifact'): Promise<T> {
  const scope = authSessionScope()
  return readResource<T>(url, policy, {
    fetcher: authFetch,
    cacheKey: scope ? `${sessionPrefix(scope)}${url}` : null,
  })
}

/** Invalidate only the current session's private reads after a mutation. */
export function clearAuthResourceCache(): void {
  const scope = authSessionScope()
  if (scope) clearResourceCachePrefix(sessionPrefix(scope))
}
