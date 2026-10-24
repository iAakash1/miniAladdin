import type { Metadata } from 'next'
import Link from 'next/link'

import LegalDocument, { type LegalSection } from '@/components/legal/LegalDocument'
import { CONTACT_URL, FRED_NOTICE, FRED_TERMS_URL, REPOSITORY_URL } from '@/lib/legal'

export const metadata: Metadata = {
  title: 'Terms and Conditions',
  description:
    'The terms for using OmniSignal, an independent, experimental financial-research project: what its outputs are and are not, and how third-party data may be used.',
  alternates: { canonical: '/terms' },
}

/*
 * Every statement here describes the product as built. Where the right answer
 * is a decision only the owner (or a lawyer) can make — governing law, a
 * refund policy, a private contact address — the page says nothing rather
 * than inventing one; those are listed in docs/LEGAL_REVIEW.md.
 */

const SECTIONS: LegalSection[] = [
  {
    id: 'about',
    title: 'About OmniSignal and these Terms',
    body: (
      <>
        <p>
          OmniSignal is an independently developed, experimental software and financial-research project. It is
          created and maintained by its project owner (the &ldquo;owner&rdquo;), who publishes its source code
          at <a href={REPOSITORY_URL}>github.com/iAakash1/miniAladdin</a>. It is not offered by a bank, broker,
          investment adviser or other financial institution.
        </p>
        <p>
          These Terms apply to this website, the research terminal and the interfaces behind them (together,
          &ldquo;OmniSignal&rdquo;). By using OmniSignal you agree to them. If you do not agree, please do not use it.
          The <Link href="/privacy">Privacy notice</Link> explains what information OmniSignal handles and why.
        </p>
      </>
    ),
  },
  {
    id: 'experimental',
    title: 'Experimental features and outputs',
    body: (
      <>
        <p>
          OmniSignal is an experimental research and software platform. Its features, data integrations, analytical
          methods, model outputs and other functionality may change, be unavailable, or produce incomplete,
          inaccurate, delayed or inconsistent results.
        </p>
        <p>
          An output is not an independently verified fact because it appears in OmniSignal. Check material
          information against its primary source — the filing, the exchange or the publisher — before you rely on it.
          OmniSignal names the source of the values it shows so that you can.
        </p>
        <p>
          Experimental findings, historical performance, backtests, model scores, rankings, estimates, forecasts and
          research results do not guarantee future results. Past results are not a reliable indicator of future
          outcomes. The project may be changed, suspended or discontinued as the research and software evolve,
          subject to any legal obligations that apply.
        </p>
      </>
    ),
  },
  {
    id: 'not-advice',
    title: 'Financial information is not investment advice',
    body: (
      <>
        <p>
          Information, analyses, model outputs, rankings, signals, estimates and research results in OmniSignal are
          provided for informational, educational and experimental research purposes. They are not a representation
          that any security, instrument, strategy or transaction is suitable for any particular person or objective.
        </p>
        <p>
          Signal labels such as &ldquo;Buy&rdquo;, &ldquo;Hold&rdquo; or &ldquo;Sell&rdquo;, and the scores,
          confidence values and risk classes shown with them, are outputs of a deterministic scoring model run for
          research. They are not recommendations to buy, sell or hold anything, and they do not take your financial
          situation, objectives or tolerance for risk into account.
        </p>
        <p>
          OmniSignal does not provide personalized investment advice, portfolio management or brokerage services, and
          it does not execute trades. Its paper-trading features are simulations: no real order, money or position is
          involved.
        </p>
        <p>
          Financial markets involve risk, including the risk of substantial or total loss. Data, models and historical
          relationships can be incomplete, inaccurate or delayed, and can stop holding. You are responsible for
          evaluating information independently and for your own financial decisions. No return, level of accuracy,
          risk reduction, predictive performance or investment outcome is guaranteed.
        </p>
      </>
    ),
  },
  {
    id: 'ai',
    title: 'Explanations written by AI models',
    body: (
      <p>
        Some explanations and answers in OmniSignal are written by third-party language models from the evidence the
        engine gathered. The scores and signals themselves are computed by a deterministic engine and are not set by
        those models. A written explanation can still be wrong, incomplete or out of date. Each one cites the evidence
        it relies on so that it can be checked, and the evidence takes precedence over the prose.
      </p>
    ),
  },
  {
    id: 'third-party-data',
    title: 'Third-party data and services',
    body: (
      <>
        <p>
          OmniSignal obtains information from third-party data providers, public records, filings, market-data
          services, news services, search services and other external sources. How that information may be accessed,
          displayed, retained, redistributed or commercially used can be governed by each provider&rsquo;s own terms
          and licenses, and by law.
        </p>
        <p>
          OmniSignal does not guarantee the completeness, accuracy, timeliness, availability or continued accessibility
          of third-party information. Providers may change their services, impose rate limits, revise or withdraw
          information, or end access. When a source does not answer, OmniSignal says so rather than showing a value in
          its place.
        </p>
        <p>
          You must respect the licenses and restrictions that apply to third-party information. Nothing in these Terms
          grants you rights to third-party content beyond those the relevant provider actually grants, or that
          applicable law permits.
        </p>
        <p className="legal__notice">
          {FRED_NOTICE} Use of FRED data is subject to the{' '}
          <a href={FRED_TERMS_URL}>FRED® API Terms of Use</a>.
        </p>
      </>
    ),
  },
  {
    id: 'ownership',
    title: 'Independent project and intellectual property',
    body: (
      <>
        <p>
          Subject to applicable law and the rights of others, the owner keeps the rights the owner holds in the
          original software, interface, documentation, original research materials and other original material
          developed for OmniSignal. Nothing in these Terms transfers those rights to you.
        </p>
        <p>
          Financial data, market data, filings, news, company information, third-party software, interfaces,
          trademarks, logos and other material obtained from external sources remain subject to the rights, licenses
          and terms of their owners or providers. OmniSignal does not claim ownership of third-party material because
          it is accessed, processed, displayed, cached or analyzed by the platform. Company names and logos identify
          the companies concerned and belong to them.
        </p>
        <p>
          Access to third-party data through OmniSignal does not by itself give you a right to copy, redistribute,
          republish, commercially exploit or otherwise use that data beyond what its source permits and the law
          allows.
        </p>
        <p>
          The source code is published in a public repository. Publication does not by itself grant a license to copy,
          modify or redistribute it beyond any license that accompanies it. Some earlier versions of the repository
          were distributed with the MIT License; whatever rights that license granted for those versions are not
          affected by these Terms. Open-source libraries, fonts and other components used by OmniSignal remain under
          their own licenses.
        </p>
        <p>
          Unless it is stated here, no affiliation with, sponsorship by, endorsement by or partnership with any data
          provider, exchange, financial institution or other organization should be inferred from its name or data
          appearing in OmniSignal.
        </p>
      </>
    ),
  },
  {
    id: 'accounts',
    title: 'Accounts and security',
    body: (
      <p>
        The research terminal requires an account. Sign-in is provided by Clerk, a third-party authentication service.
        Keep your sign-in method secure and do not share your account. If you think someone else has used it, raise it
        through the contact channel below. Access may be suspended for an account used in breach of these Terms or to
        harm the service or other users.
      </p>
    ),
  },
  {
    id: 'acceptable-use',
    title: 'Acceptable use',
    body: (
      <>
        <p>When you use OmniSignal, do not:</p>
        <ul>
          <li>try to gain unauthorized access to it, to other users&rsquo; accounts or data, or to the systems and services behind it;</li>
          <li>probe, scan or test its security without the owner&rsquo;s permission, or use it to reach systems it was not built to reach;</li>
          <li>get around the free-tier limit, rate limits, sign-in or other controls;</li>
          <li>overload it, or extract its content in bulk by automated means;</li>
          <li>redistribute or republish third-party data obtained through it beyond what the source permits;</li>
          <li>use it for anything unlawful, including market manipulation or misleading others about a security.</li>
        </ul>
        <p>If you find a security problem, please report it through the contact channel below rather than exploiting it.</p>
      </>
    ),
  },
  {
    id: 'paid-access',
    title: 'Paid access',
    body: (
      <p>
        OmniSignal can be used free of charge, up to a daily limit on research runs. Pro is a one-time payment, shown
        with its price before you pay, that unlocks the paid features on your account. There is no recurring charge.
        Payments are processed by Razorpay under its own terms; OmniSignal does not receive or store your card or bank
        details. For any question about a payment, use the contact channel below.
      </p>
    ),
  },
  {
    id: 'availability',
    title: 'Availability and changes to the service',
    body: (
      <p>
        OmniSignal is run as an experimental project and may be interrupted, limited, changed or withdrawn, including
        when a data provider changes or ends its service. Features, limits and integrations may change as the research
        and software evolve, subject to any legal obligations that apply.
      </p>
    ),
  },
  {
    id: 'liability',
    title: 'Warranties and liability',
    body: (
      <>
        <p>
          To the extent permitted by applicable law, OmniSignal is provided &ldquo;as is&rdquo; and &ldquo;as
          available&rdquo;, without warranties of any kind, and the owner is not liable for loss arising from your use
          of, or reliance on, OmniSignal or its outputs, including investment or trading losses.
        </p>
        <p>
          Nothing in these Terms excludes or limits any liability that cannot be excluded or limited under applicable
          law, or affects rights you have as a consumer that cannot be waived.
        </p>
      </>
    ),
  },
  {
    id: 'ending',
    title: 'Ending your use',
    body: (
      <p>
        You can stop using OmniSignal at any time. Saved items such as watchlists, history and reports can be deleted
        from the terminal; the <Link href="/privacy#choices">Privacy notice</Link> explains how to ask for your
        account data to be removed. Access may be suspended or ended where these Terms are breached.
      </p>
    ),
  },
  {
    id: 'changes',
    title: 'Changes to these Terms',
    body: (
      <p>
        These Terms may be updated as OmniSignal changes. The date at the top of this page shows when they last
        changed. Continuing to use OmniSignal after a change means you accept the updated Terms.
      </p>
    ),
  },
  {
    id: 'contact',
    title: 'Contact',
    body: (
      <p>
        Questions about these Terms, intellectual-property concerns and security reports can be raised through the
        project&rsquo;s repository at <a href={CONTACT_URL}>github.com/iAakash1/miniAladdin/issues</a>. Issues there
        are public, so do not include personal or account details in one.
      </p>
    ),
  },
]

export default function TermsPage() {
  return (
    <LegalDocument
      eyebrow="Legal"
      title="Terms and Conditions"
      related={{ href: '/privacy', label: 'Privacy notice' }}
      sections={SECTIONS}
      summary={
        <ul>
          <li>OmniSignal is the owner&rsquo;s independent, experimental research project — not a financial institution.</li>
          <li>Its signals and scores are research outputs, not investment advice or recommendations.</li>
          <li>Third-party data stays subject to its providers&rsquo; terms; access through OmniSignal grants no extra rights.</li>
          <li>Outputs can be wrong, delayed or incomplete. Check primary sources before relying on anything.</li>
        </ul>
      }
    />
  )
}
