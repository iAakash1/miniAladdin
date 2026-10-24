import type { Metadata } from 'next'
import Link from 'next/link'

import LegalDocument, { type LegalSection } from '@/components/legal/LegalDocument'
import { CONTACT_URL } from '@/lib/legal'

export const metadata: Metadata = {
  title: 'Privacy notice',
  description: 'What information OmniSignal handles, why, who processes it, and what you can do about it.',
  alternates: { canonical: '/privacy' },
}

/*
 * Written from the code, not from a template: every item below corresponds to
 * something the application does (Clerk sign-in, the Supabase tables keyed to
 * the Clerk user id, Razorpay identifiers in account metadata, browser
 * storage keys, request logs, /api/ask). Nothing is promised that the code does
 * not establish — in particular there is no automatic deletion of saved data
 * when a sign-in account is removed, and the page says so.
 */

const SECTIONS: LegalSection[] = [
  {
    id: 'scope',
    title: 'Who this covers',
    body: (
      <p>
        This notice describes the information OmniSignal, an independent experimental project run by its project owner,
        handles when you visit the website or use the research terminal. It should be read with
        the <Link href="/terms">Terms and Conditions</Link>.
      </p>
    ),
  },
  {
    id: 'collected',
    title: 'What OmniSignal handles',
    body: (
      <>
        <dl className="legal__defs">
          <dt>Account</dt>
          <dd>
            When you create an account, Clerk (the sign-in service) holds your email address, any name or profile
            details your sign-in method provides, and an account identifier. OmniSignal receives that identifier and
            uses it to tell your saved work apart from everyone else&rsquo;s.
          </dd>
          <dt>Research you save</dt>
          <dd>
            Watchlists, analysis history, saved reports, paper-trading positions, research sessions and notes, and
            your display preferences, stored in a database under your account identifier.
          </dd>
          <dt>Questions you type</dt>
          <dd>Questions asked in the terminal&rsquo;s explanation features, and the companies and terms you search for.</dd>
          <dt>Payments</dt>
          <dd>
            If you buy Pro, Razorpay processes the payment. OmniSignal keeps the Razorpay order and payment identifiers
            and the fact that your account has Pro. It never receives your card or bank details.
          </dd>
          <dt>Request logs</dt>
          <dd>
            Each request to the backend is logged with a request identifier, the method and path, the response status,
            its duration and, when you are signed in, your account identifier. These logs are used to keep the service
            working and to investigate faults and abuse.
          </dd>
          <dt>Browser storage</dt>
          <dd>
            Your browser stores your theme and display choices, the count of today&rsquo;s free research runs, and
            recently viewed items, locally on your device. Clerk sets the cookies that keep you signed in.
          </dd>
        </dl>
        <p>OmniSignal does not use advertising or third-party analytics trackers, and it does not sell personal information.</p>
      </>
    ),
  },
  {
    id: 'shared',
    title: 'Who else processes it',
    body: (
      <>
        <p>OmniSignal relies on these services, each of which processes information under its own terms:</p>
        <ul>
          <li><strong>Clerk</strong> — sign-in and account management.</li>
          <li><strong>Supabase</strong> — the database that holds the research you save.</li>
          <li><strong>Vercel</strong> — hosting for the website.</li>
          <li><strong>Google Cloud</strong> — hosting for the research backend, and its request logs.</li>
          <li><strong>Razorpay</strong> — payments, if you buy Pro.</li>
          <li>
            <strong>Data providers</strong> (market data, filings, news and search services) — they receive the
            tickers, companies and search terms needed to answer a request, sent under the project&rsquo;s credentials,
            not your account details.
          </li>
          <li>
            <strong>AI model providers</strong> (currently DeepSeek and Groq, when configured) — they receive the
            evidence gathered for a company and any question you type, to write an explanation. Do not type personal
            information into a question.
          </li>
        </ul>
        <p>These services may process information in countries other than yours.</p>
      </>
    ),
  },
  {
    id: 'retention',
    title: 'How long it is kept',
    body: (
      <p>
        Research you save is kept until you delete it or ask for it to be removed. Payment identifiers are kept with
        your account. Request logs are kept for the retention periods set in the hosting services. Information held by
        Clerk, Razorpay and the other services above is kept under their own policies.
      </p>
    ),
  },
  {
    id: 'choices',
    title: 'Your choices',
    body: (
      <>
        <p>
          You can delete individual watchlists, history entries, saved reports, paper positions and research sessions
          from the terminal. To ask for all of your saved data and your account to be removed, or to ask what
          OmniSignal holds about you, use the contact channel below.
        </p>
        <p>
          Deleting your sign-in account does not, by itself, remove the research saved in the database under it, so
          please ask for that as well. Depending on where you live, you may have further rights over your personal
          information.
        </p>
      </>
    ),
  },
  {
    id: 'security',
    title: 'Security',
    body: (
      <p>
        Your browser reaches the research backend only through the website&rsquo;s authenticated server, and the
        database answers only that backend: its row-level security denies every other client. Data-provider and
        payment credentials are kept on the
        servers and never sent to your browser. No system is perfectly secure; if you find a problem, please report it
        through the contact channel below.
      </p>
    ),
  },
  {
    id: 'changes',
    title: 'Changes to this notice',
    body: <p>This notice will be updated when what OmniSignal handles changes. The date at the top shows the latest revision.</p>,
  },
  {
    id: 'contact',
    title: 'Contact',
    body: (
      <p>
        Raise privacy questions and requests through the project&rsquo;s repository
        at <a href={CONTACT_URL}>github.com/iAakash1/miniAladdin/issues</a>. Issues there are public: describe your
        request without including your email address or other personal details, and the owner will arrange a private
        way to confirm it is yours.
      </p>
    ),
  },
]

export default function PrivacyPage() {
  return (
    <LegalDocument
      eyebrow="Legal"
      title="Privacy notice"
      related={{ href: '/terms', label: 'Terms and Conditions' }}
      sections={SECTIONS}
      summary={
        <ul>
          <li>Your account comes from Clerk; your saved research is stored under your account identifier.</li>
          <li>No advertising or analytics trackers. Personal information is not sold.</li>
          <li>Questions you type may be sent to AI model providers to write an answer.</li>
          <li>You can delete saved items yourself, and ask for everything to be removed.</li>
        </ul>
      }
    />
  )
}
