import type { ReactNode } from 'react'

export type LegalPage = 'privacy' | 'terms' | 'cookies' | 'billing'

export const legalLinks: { path: string; label: string }[] = [
  { path: '/privacy', label: 'Privacy' },
  { path: '/terms', label: 'Terms' },
  { path: '/cookies', label: 'Cookies' },
  { path: '/billing', label: 'Billing' },
]

const updated = '26 September 2026'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="legal-section"><h2>{title}</h2>{children}</section>
}

const pages: Record<LegalPage, { title: string; intro: string; content: ReactNode }> = {
  privacy: {
    title: 'Privacy policy',
    intro: 'How the YLD demo handles information about you and your kitchen.',
    content: <>
      <Section title="Who this covers"><p>YLD is a Christchurch, New Zealand restaurant prep planning prototype. This policy covers this website and its local demo API. The legal operator and privacy contact must be identified before a public service launches; see the contact section below.</p></Section>
      <Section title="Information we collect"><p>When you use the demo, we receive the email address and password entered on the login form. The demo starts with a shared sample account. We also receive the covers, demand settings, dish costs and prices, and prepared and sold quantities you enter. The server may process technical request information, including an IP address, as part of serving the site.</p><p>Supply of these details is voluntary, but the relevant feature cannot work without them. Please use sample or non-sensitive business data. Do not enter customer names, staff details, or confidential records into the shared demo.</p></Section>
      <Section title="How we use it"><p>We use login details to check access, and planning and service data to calculate forecasts, show history, and improve later demo recommendations. We use technical request information to operate and troubleshoot the service. We do not use demo entries for advertising or sell personal information.</p></Section>
      <Section title="Storage and sharing"><p>The backend stores the demo account, dish costs, and service history in a local SQLite database. The demo uses a shared dataset, so changes to dish costs and actuals can be seen by other people using the same instance. Hosting and infrastructure providers may process technical data if this site is deployed through them. We will identify material providers and any overseas disclosures before a production launch.</p></Section>
      <Section title="Retention and security"><p>Demo data remains in the local database until it is changed or the database is reset. This prototype is not configured as a private production account system. Please do not use it for real confidential operations.</p></Section>
      <Section title="Your rights"><p>Under New Zealand's Privacy Act 2020, you can ask for access to and correction of personal information we hold about you. You may also raise a privacy concern with us and, if unresolved, contact the Office of the Privacy Commissioner. The shared demo account may make it difficult to identify which planning entries belong to a particular person.</p></Section>
      <Section title="Children and changes"><p>YLD is intended for business users, not children. We may update this policy as the service changes and will show the new date on this page. Material changes to a live service should be communicated to affected users.</p></Section>
      <Section title="Contact"><p>The operator's legal name, address, and monitored privacy email have not yet been provided. These details must be published here before accepting real customer information.</p></Section>
    </>,
  },
  terms: {
    title: 'Terms of use',
    intro: 'The rules for using this YLD website and its current demo.',
    content: <>
      <Section title="The service"><p>YLD provides a restaurant prep planning demonstration using fictional starting data. It is currently a shared local prototype, not an individual production account or a paid subscription. By using the demo, you agree to use it lawfully and in line with these terms.</p></Section>
      <Section title="Your inputs"><p>You are responsible for the information you enter and for checking every recommendation before using it in a kitchen. Do not enter personal, sensitive, confidential, or unlawful material. Demo data can be overwritten and may be visible to other users of the same instance. You retain your rights in information you provide and allow YLD to process it to operate the demo.</p></Section>
      <Section title="Forecasts and decisions"><p>Forecasts, ranges, savings estimates, and comparisons are estimates based on the available inputs and sample history. They are not guarantees of demand, profit, safety, or waste reduction. You remain responsible for food safety, purchasing, staffing, and service decisions.</p></Section>
      <Section title="Acceptable use"><p>Do not interfere with the site, attempt unauthorised access, submit malicious code, or use the demo in a way that harms others. We may restrict access to protect the service or other users.</p></Section>
      <Section title="Availability and ownership"><p>We may change or stop the demo and reset its data. The YLD name, interface, and software remain the property of their respective owners. You may use the site for its intended purpose but may not copy or resell the software without permission.</p></Section>
      <Section title="Liability and legal rights"><p>We aim to keep the information accurate and the demo available, but make no promise that it will be uninterrupted or error free. To the extent permitted by law, YLD is not responsible for business decisions made from the demo's estimates. Nothing in these terms excludes rights or remedies that cannot lawfully be excluded, including any applicable rights under New Zealand law.</p></Section>
      <Section title="Changes and governing law"><p>We may update these terms and will show the new date here. New Zealand law governs these terms. The operator's legal name, address, and contact details must be added before these terms are used for a public paid service.</p></Section>
    </>,
  },
  cookies: {
    title: 'Cookies and storage',
    intro: 'What this version of YLD puts in your browser.',
    content: <>
      <Section title="Current use"><p>The YLD application does not currently set cookies or use browser storage for analytics, advertising, or login. The login form checks the shared demo credentials but does not create a persistent browser session.</p></Section>
      <Section title="Your choices"><p>Your browser may store ordinary cached site files; you can clear those through browser settings. Clearing browser data does not remove entries already saved in the shared demo database.</p></Section>
      <Section title="Changes"><p>If analytics, advertising, or other optional tracking is introduced, we will update this notice and provide any choice required before using it. Third-party hosting may have its own technical logging practices, which will be described when a production host is selected.</p></Section>
    </>,
  },
  billing: {
    title: 'Billing and cancellations',
    intro: 'The current status of YLD plans, trials, charges, and refunds.',
    content: <>
      <Section title="No live checkout"><p>This version of YLD is a free demo. It has no checkout, payment collection, active subscription, or 14-day trial. The plans shown on the pricing page are proposed offerings and cannot be purchased through this site today.</p></Section>
      <Section title="Before paid plans launch"><p>We will publish the final price in NZD, whether GST is included, billing frequency, trial start and end rules, when a card will be charged, cancellation steps, and refund terms before taking payment. A customer will need to actively agree to recurring charges. No payment or cancellation obligation arises from using this demo.</p></Section>
      <Section title="Problems and statutory rights"><p>If paid services become available, any refund terms will respect applicable rights under New Zealand law. For now, there are no demo charges to refund. The operator's billing contact must be published before a paid launch.</p></Section>
    </>,
  },
}

export function LegalFooter({ className = '' }: { className?: string }) {
  return <footer className={`legal-footer ${className}`}><span>YLD. / CHRISTCHURCH, NZ</span><nav aria-label="Legal information">{legalLinks.map(link => <a key={link.path} href={link.path}>{link.label}</a>)}</nav><a href="/">Home</a></footer>
}

export default function LegalPage({ page }: { page: LegalPage }) {
  const item = pages[page]
  return <div className="legal-page"><header className="legal-header"><a className="legal-brand" href="/">YLD<span>.</span></a><a href="/">BACK TO SITE ↗</a></header><main className="legal-main"><span className="legal-kicker">YLD / LEGAL</span><h1>{item.title}</h1><p className="legal-intro">{item.intro}</p><p className="legal-date">Last updated {updated}</p><div className="legal-content">{item.content}</div></main><LegalFooter /></div>
}
