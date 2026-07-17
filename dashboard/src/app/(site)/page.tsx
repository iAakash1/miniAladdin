import Link from 'next/link'
import type { Metadata } from 'next'
import MacroStrip from '@/components/marketing/MacroStrip'
import NewsPreview from '@/components/marketing/NewsPreview'
import TerminalPreview from '@/components/marketing/TerminalPreview'
import Reveal from '@/components/ui/Reveal'

export const metadata: Metadata = {
  // Inherits the root default title; template would double the brand here.
  description:
    'Five weighted signals — momentum, risk-adjusted return, valuation, news sentiment and the macro cycle — combined into one risk-adjusted verdict per stock.',
  alternates: { canonical: '/' },
}

const FACTORS = [
  {
    factor: 'RSI-14',
    measures: 'Overbought and oversold pressure over the last 14 sessions',
    reads: 'Below 30 counts bullish; above 70 counts bearish',
    weight: '±2',
  },
  {
    factor: 'Sharpe ratio',
    measures: 'Return earned per unit of volatility over the trailing year',
    reads: 'Above 1.0 counts bullish; below 0 counts bearish',
    weight: '±2',
  },
  {
    factor: '21-day return',
    measures: 'Near-term momentum, one trading month',
    reads: 'Sustained gains count bullish; sustained losses bearish',
    weight: '±2',
  },
  {
    factor: 'MACD crossover',
    measures: 'Trend inflection between fast and slow moving averages',
    reads: 'Bullish or bearish cross, when present',
    weight: '±1',
  },
  {
    factor: 'Analyst target',
    measures: 'Distance to the consensus street price target',
    reads: 'Meaningful upside counts bullish; targets below price bearish',
    weight: '±2',
  },
]

const FAQ = [
  {
    q: 'Where does the data come from?',
    a: 'Macro series come from FRED (the St. Louis Fed): the 10Y–2Y Treasury spread, CPI inflation and the federal funds rate. Prices and technicals come from Yahoo Finance, fundamentals and MACD from Alpha Vantage, and headlines from financial news feeds. Every analysis states what it used.',
  },
  {
    q: 'Is this investment advice?',
    a: 'No. OmniSignal is a research and education tool. It compresses public data into a structured, repeatable readout — it does not know your situation, and a verdict is a summary of signals, not a recommendation. Decisions and their consequences remain yours.',
  },
  {
    q: 'How is the verdict computed?',
    a: 'Five factors each contribute a weighted score. The sum maps to a raw signal from Strong Sell to Strong Buy. That signal is then dampened by the Systemic Risk Multiplier — a macro-regime reading built from FRED data — so a bullish setup in a fragile macro environment gets pulled toward caution. Both the raw and the risk-adjusted signal are always shown.',
  },
  {
    q: 'Can I cancel Pro?',
    a: 'Yes, anytime. Pro is ₹100 per month through Razorpay. If you cancel, you keep Pro until the end of the billing period and then return to the free tier — nothing is deleted.',
  },
]

export default function LandingPage() {
  return (
    <>
      {/* ---------- Hero ---------- */}
      <section style={{ padding: 'clamp(64px, 10vw, 128px) 0 clamp(48px, 7vw, 88px)' }}>
        <div className="container hero-grid">
          <div>
            <p className="eyebrow" style={{ marginBottom: 20 }}>
              Equity research terminal
            </p>
            <h1 className="display" style={{ marginBottom: 24 }}>
              Five signals.
              <br />
              <em>One verdict.</em>
            </h1>
            <p className="lede" style={{ marginBottom: 36 }}>
              OmniSignal scores a stock across momentum, risk-adjusted return,
              trend, street expectations and news sentiment — then dampens the
              result by the state of the macro cycle. What you get is a single,
              explainable verdict and every number behind it.
            </p>
            <div className="hero-cta" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <Link href="/terminal" className="btn btn--primary btn--lg">
                Open the terminal
              </Link>
              <Link href="/#methodology" className="btn btn--secondary btn--lg">
                Read the methodology
              </Link>
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--faint)', marginTop: 18 }}>
              Free tier: five analyses a day. No card required.
            </p>
          </div>

          {/* Engine facts — quiet, factual, no illustration */}
          <aside aria-label="What the engine reads" className="hero-aside">
            <p className="label" style={{ marginBottom: 6 }}>
              Each analysis reads
            </p>
            <dl style={{ margin: 0 }}>
              {[
                ['Momentum', 'RSI-14 and 21-day return'],
                ['Risk', 'Sharpe, Sortino, drawdown, volatility'],
                ['Trend', 'MACD crossover state'],
                ['The street', 'Consensus target vs. price'],
                ['The tape', 'Headline sentiment, scored'],
                ['The regime', 'FRED macro → risk multiplier'],
              ].map(([term, detail]) => (
                <div
                  key={term}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 16,
                    padding: '11px 0',
                    borderBottom: '1px solid var(--line)',
                  }}
                >
                  <dt style={{ fontSize: '0.875rem', fontWeight: 560, whiteSpace: 'nowrap' }}>{term}</dt>
                  <dd style={{ margin: 0, fontSize: '0.875rem', color: 'var(--muted)', textAlign: 'right' }}>
                    {detail}
                  </dd>
                </div>
              ))}
            </dl>
          </aside>
        </div>
      </section>

      {/* ---------- Live macro strip ---------- */}
      <MacroStrip />

      {/* ---------- Product ---------- */}
      <section id="product" style={{ padding: 'clamp(64px, 9vw, 112px) 0' }}>
        <div className="container" style={{ maxWidth: 880 }}>
          <Reveal>
            <p className="eyebrow" style={{ marginBottom: 14, textAlign: 'center' }}>
              The terminal
            </p>
            <h2 className="h-section" style={{ textAlign: 'center', marginBottom: 18 }}>
              A full readout, not a green number
            </h2>
            <p
              className="body-copy"
              style={{ textAlign: 'center', margin: '0 auto clamp(36px, 5vw, 56px)' }}
            >
              Type a ticker. In a few seconds you get the verdict, the raw signal
              before macro dampening, price history, fundamentals, risk metrics
              and the headlines that moved sentiment — all on one screen.
            </p>
          </Reveal>
          <Reveal delay={80}>
            <TerminalPreview />
          </Reveal>
        </div>
      </section>

      {/* ---------- Methodology ---------- */}
      <section
        id="methodology"
        className="hairline-top"
        style={{ padding: 'clamp(64px, 9vw, 112px) 0', background: 'var(--surface)' }}
      >
        <div className="container" style={{ maxWidth: 880 }}>
          <Reveal>
            <p className="eyebrow" style={{ marginBottom: 14 }}>
              Methodology
            </p>
            <h2 className="h-section" style={{ marginBottom: 22 }}>
              How the verdict forms
            </h2>
            <div className="prose body-copy" style={{ marginBottom: 40 }}>
              <p>
                Every analysis runs the same five factors, in the same order,
                with the same weights. There is no discretion in the loop and
                nothing is hidden: the point of OmniSignal is not that the
                model is secret, but that it is consistent — the same stock on
                the same day always produces the same readout.
              </p>
            </div>
          </Reveal>

          <Reveal delay={60}>
            <div className="panel" style={{ overflowX: 'auto', marginBottom: 40 }}>
              <table className="data-table" style={{ minWidth: 640 }}>
                <caption className="visually-hidden">The five scoring factors and their weights</caption>
                <thead>
                  <tr>
                    <th scope="col">Factor</th>
                    <th scope="col">What it measures</th>
                    <th scope="col">How it reads</th>
                    <th scope="col" style={{ textAlign: 'right' }}>
                      Weight
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {FACTORS.map((f) => (
                    <tr key={f.factor}>
                      <td className="mono" style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>
                        {f.factor}
                      </td>
                      <td style={{ color: 'var(--muted)' }}>{f.measures}</td>
                      <td style={{ color: 'var(--muted)' }}>{f.reads}</td>
                      <td className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
                        {f.weight}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Reveal>

          <Reveal delay={100}>
            <div className="split-2" style={{ gap: 20 }}>
              <div className="card" style={{ padding: '24px 26px' }}>
                <p className="label" style={{ marginBottom: 12 }}>
                  Then: macro dampening
                </p>
                <p style={{ fontSize: '0.9375rem', lineHeight: 1.7, color: 'var(--muted)' }}>
                  The factor sum maps to a raw signal from{' '}
                  <strong style={{ color: 'var(--neg)', fontWeight: 560 }}>Strong Sell</strong> to{' '}
                  <strong style={{ color: 'var(--pos)', fontWeight: 560 }}>Strong Buy</strong>. The{' '}
                  Systemic Risk Multiplier — built from the Treasury yield
                  spread, CPI trend and the Fed funds rate — then scales it.
                  In a fragile regime (SRM above ~1.2), bullish verdicts are
                  pulled toward caution. Both signals are always shown.
                </p>
              </div>
              <div className="card" style={{ padding: '24px 26px' }}>
                <p className="label" style={{ marginBottom: 12 }}>
                  What it is not
                </p>
                <p style={{ fontSize: '0.9375rem', lineHeight: 1.7, color: 'var(--muted)' }}>
                  Not a price prediction, not a backtest promising returns, and
                  not advice. It is a disciplined summary of public data —
                  useful the way a pre-flight checklist is useful: it does not
                  fly the plane, it stops you from skipping steps.
                </p>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------- News ---------- */}
      <section id="news" className="hairline-top" style={{ padding: 'clamp(64px, 9vw, 112px) 0' }}>
        <div className="container" style={{ maxWidth: 880 }}>
          <Reveal>
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                gap: 16,
                marginBottom: 8,
                flexWrap: 'wrap',
              }}
            >
              <h2 className="h-section">Market news, as it breaks</h2>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                <span className="live-dot" aria-hidden="true" />
                <span className="label" style={{ color: 'var(--muted)' }}>
                  Live
                </span>
              </span>
            </div>
            <p className="body-copy" style={{ marginBottom: 28 }}>
              Aggregated from Yahoo Finance, MarketWatch and CNBC. The same feed
              powers sentiment scoring inside the terminal.
            </p>
          </Reveal>
          <Reveal delay={60}>
            <NewsPreview />
          </Reveal>
        </div>
      </section>

      {/* ---------- Pricing ---------- */}
      <section
        id="pricing"
        className="hairline-top"
        style={{ padding: 'clamp(64px, 9vw, 112px) 0', background: 'var(--surface)' }}
      >
        <div className="container" style={{ maxWidth: 880 }}>
          <Reveal>
            <p className="eyebrow" style={{ marginBottom: 14, textAlign: 'center' }}>
              Pricing
            </p>
            <h2 className="h-section" style={{ textAlign: 'center', marginBottom: 14 }}>
              Free to use daily. Pro when you need depth.
            </h2>
            <p className="body-copy" style={{ textAlign: 'center', margin: '0 auto clamp(36px, 5vw, 52px)' }}>
              One plan, one price. No tiers to decode.
            </p>
          </Reveal>

          <Reveal delay={60}>
            <div className="split-2" style={{ alignItems: 'stretch', maxWidth: 760, margin: '0 auto' }}>
              {/* Free */}
              <div className="card" style={{ padding: '30px 30px 26px', display: 'flex', flexDirection: 'column' }}>
                <p className="h-panel" style={{ marginBottom: 6 }}>
                  Free
                </p>
                <p style={{ marginBottom: 22 }}>
                  <span className="num" style={{ fontSize: '2rem', fontWeight: 600 }}>
                    ₹0
                  </span>
                </p>
                <ul style={{ listStyle: 'none', margin: '0 0 28px', padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {[
                    'Five analyses per day',
                    'Full verdict and factor readout',
                    'Three-month price charts',
                    'Live macro conditions',
                    'Headline sentiment (without links)',
                  ].map((f) => (
                    <li key={f} style={{ display: 'flex', gap: 10, fontSize: '0.9375rem', color: 'var(--muted)' }}>
                      <span aria-hidden="true" style={{ color: 'var(--pos)', fontWeight: 600 }}>
                        ✓
                      </span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/sign-up" className="btn btn--secondary" style={{ marginTop: 'auto' }}>
                  Start free
                </Link>
              </div>

              {/* Pro */}
              <div
                className="card"
                style={{
                  padding: '30px 30px 26px',
                  display: 'flex',
                  flexDirection: 'column',
                  borderColor: 'var(--accent)',
                  boxShadow: 'var(--shadow-2)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <p className="h-panel">Pro</p>
                  <span className="badge badge--accent">Most useful</span>
                </div>
                <p style={{ marginBottom: 22 }}>
                  <span className="num" style={{ fontSize: '2rem', fontWeight: 600 }}>
                    ₹100
                  </span>
                  <span style={{ fontSize: '0.875rem', color: 'var(--faint)' }}> / month</span>
                </p>
                <ul style={{ listStyle: 'none', margin: '0 0 28px', padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {[
                    'Unlimited analyses',
                    'All timeframes — 1M to 5Y',
                    'Full article access from sentiment',
                    'Everything in Free',
                  ].map((f) => (
                    <li key={f} style={{ display: 'flex', gap: 10, fontSize: '0.9375rem', color: 'var(--muted)' }}>
                      <span aria-hidden="true" style={{ color: 'var(--pos)', fontWeight: 600 }}>
                        ✓
                      </span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/terminal" className="btn btn--primary" style={{ marginTop: 'auto' }}>
                  Go Pro in the terminal
                </Link>
              </div>
            </div>
            <p style={{ textAlign: 'center', fontSize: '0.8125rem', color: 'var(--faint)', marginTop: 20 }}>
              Payments through Razorpay. Cancel anytime.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ---------- FAQ ---------- */}
      <section className="hairline-top" style={{ padding: 'clamp(64px, 9vw, 112px) 0 clamp(80px, 10vw, 128px)' }}>
        <div className="container" style={{ maxWidth: 720 }}>
          <Reveal>
            <h2 className="h-section" style={{ marginBottom: 28 }}>
              Questions, answered plainly
            </h2>
          </Reveal>
          <Reveal delay={60}>
            <div className="hairline-top">
              {FAQ.map((item) => (
                <details key={item.q} className="faq-item">
                  <summary>{item.q}</summary>
                  <div className="faq-body">{item.a}</div>
                </details>
              ))}
            </div>
          </Reveal>
        </div>
      </section>
    </>
  )
}
