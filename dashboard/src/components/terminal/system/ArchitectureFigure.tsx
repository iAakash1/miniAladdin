/**
 * The production request path, drawn from the deployment as it is built:
 * the browser never holds a backend credential, the proxy exchanges a
 * short-lived platform token for a short-lived Google identity, and the API
 * itself is private. Nothing here is a status reading — it is the design.
 */
const HOPS: Array<{ k: string; v: string; note?: string; tone?: 'private' | 'identity' }> = [
  { k: 'Browser', v: 'the terminal', note: 'holds a Clerk session, never a backend key' },
  { k: 'Vercel · Next.js', v: 'pages and the /api proxy', note: 'verifies the session server-side' },
  { k: 'Vercel OIDC', v: 'short-lived platform token', tone: 'identity' },
  { k: 'Workload Identity Federation', v: 'token exchanged for a Google identity', note: 'no service-account key exists', tone: 'identity' },
  { k: 'Cloud Run · private', v: 'OmniSignal research API', note: 'not publicly invokable', tone: 'private' },
]

export default function ArchitectureFigure() {
  return (
    <figure className="arch" aria-label="Production request path">
      <ol className="arch-path">
        {HOPS.map((h) => (
          <li key={h.k} className="arch-hop" data-tone={h.tone}>
            <span className="arch-hop__k">{h.k}</span>
            <span className="arch-hop__v">{h.v}</span>
            {h.note ? <span className="arch-hop__n">{h.note}</span> : null}
          </li>
        ))}
      </ol>
      <div className="arch-below">
        <div className="arch-box">
          <span className="arch-box__k">Secret Manager</span>
          <span className="arch-box__v">provider and model credentials, read per secret by the API&apos;s runtime service account</span>
        </div>
        <div className="arch-box">
          <span className="arch-box__k">Evidence fabric</span>
          <span className="arch-box__v">market data, filings, news, macro and search vendors, each behind its own client and rate limit</span>
        </div>
        <div className="arch-box">
          <span className="arch-box__k">Deterministic engine</span>
          <span className="arch-box__v">sets signal, confidence and risk; the narrative model reads its output and cannot change it</span>
        </div>
      </div>
      <figcaption className="arch-cap">
        Every hop narrows what the next one can do: a browser session becomes a server check, a platform token becomes a
        short-lived Google identity, and only that identity can invoke the private API.
      </figcaption>
    </figure>
  )
}
