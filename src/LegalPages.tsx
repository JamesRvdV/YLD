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
    intro: 'How YLD handles invite-only access and your kitchen workspace.',
    content: <>
      <Section title="Who this covers"><p>YLD is a Christchurch, New Zealand restaurant prep planning prototype. This policy covers this website and its invite-only workspaces. The legal operator and privacy contact must be identified before a public service launches; see the contact section below.</p></Section>
      <Section title="Information we collect"><p>When you are invited or sign in, we receive your email address, workspace name, and password. When you use a workspace, we receive covers, dish costs and prices, and prepared and sold quantities you enter or import in a sales CSV. The server may process technical request information, including an IP address, as part of serving the site.</p><p>Supply of these details is voluntary, but the relevant feature cannot work without them. Each new workspace starts empty and receives service data only when a workspace owner imports a CSV. Upload only business sales data you are authorised to share. Do not include customer names, staff details, or other personal or sensitive information in a CSV.</p></Section>
      <Section title="How we use it"><p>We use your email address to send admin invitations and identify your workspace. Your password is used to authenticate sign-in. Planning and service data are used to calculate forecasts, show history, and improve later recommendations. We use technical request information to operate and troubleshoot the service. We do not use workspace entries for advertising or sell personal information.</p></Section>
      <Section title="Storage and sharing"><p>The backend stores accounts, workspace data, password hashes, hashed invitation links, sessions, and test subscription status in SQLite or a private Postgres schema. Workspaces are separated in the application; invited members of the same workspace can see its data. We send your email address, workspace name, and invitation message to Resend to deliver invitation email. If a workspace owner opens Stripe test checkout, we send their email address and a workspace identifier to Stripe, which handles the test payment details. The hosting provider may process technical information when the service is deployed. Provider locations and any overseas disclosures must be confirmed before taking real customer data.</p></Section>
      <Section title="Retention and security"><p>Workspace data and account details remain in the database until they are changed or removed by the operator. Importing a new CSV replaces that workspace’s dishes and service history. Invitations expire after 48 hours and sessions after seven days. We store a one-way password hash, use one-use invitation links, and set an HTTP-only session cookie. Do not use this pilot for personal or sensitive information.</p></Section>
      <Section title="Your rights"><p>Under New Zealand's Privacy Act 2020, you can ask for access to and correction of personal information we hold about you. You may also raise a privacy concern with us and, if unresolved, contact the Office of the Privacy Commissioner.</p></Section>
      <Section title="Children and changes"><p>YLD is intended for business users, not children. We may update this policy as the service changes and will show the new date on this page. Material changes to a live service should be communicated to affected users.</p></Section>
      <Section title="Contact"><p>For privacy questions, contact us at <a href="mailto:hello@arro.co.nz">hello@arro.co.nz</a>. The operator's legal name and address must be published here before accepting real customer information.</p></Section>
    </>,
  },
  terms: {
    title: 'Terms of use',
    intro: 'The rules for using this YLD website and its invite-only workspaces.',
    content: <>
      <Section title="The service"><p>YLD provides an invite-only restaurant prep planning service. New workspaces start empty and require a service-history import. It is not yet a paid self-service subscription. By using your workspace, you agree to use it lawfully and in line with these terms.</p></Section>
      <Section title="Your inputs"><p>You are responsible for the information you enter or import and for checking every recommendation before using it in a kitchen. Upload only sales data you are authorised to share; do not include personal, sensitive, or unlawful material. Members invited into the same workspace can see its data. You retain your rights in information you provide and allow YLD to process it to operate the service.</p></Section>
      <Section title="Forecasts and decisions"><p>Forecasts, ranges, savings estimates, and comparisons are estimates based on the available inputs and recorded service history. They are not guarantees of demand, profit, safety, or waste reduction. You remain responsible for food safety, purchasing, staffing, and service decisions.</p></Section>
      <Section title="Acceptable use"><p>Do not interfere with the site, attempt unauthorised access, submit malicious code, or use the service in a way that harms others. We may restrict access to protect the service or other users.</p></Section>
      <Section title="Availability and ownership"><p>We may change the pilot service. A workspace owner can import a CSV, which replaces that workspace’s dishes and service history. The YLD name, interface, and software remain the property of their respective owners. You may use the site for its intended purpose but may not copy or resell the software without permission.</p></Section>
      <Section title="Liability and legal rights"><p>We aim to keep the information accurate and the service available, but make no promise that it will be uninterrupted or error free. To the extent permitted by law, YLD is not responsible for business decisions made from the service's estimates. Nothing in these terms excludes rights or remedies that cannot lawfully be excluded, including any applicable rights under New Zealand law.</p></Section>
      <Section title="Changes and governing law"><p>We may update these terms and will show the new date here. New Zealand law governs these terms. The operator's legal name, address, and contact details must be added before these terms are used for a public paid service.</p></Section>
    </>,
  },
  cookies: {
    title: 'Cookies and storage',
    intro: 'What this version of YLD puts in your browser.',
    content: <>
      <Section title="Current use"><p>YLD sets one essential HTTP-only session cookie after you set a password from an invitation or sign in with your password. It lasts for up to seven days and is used to keep you signed in. It is sent only to YLD and uses SameSite=Lax; on an HTTPS deployment it is also marked Secure. The application does not currently set advertising or analytics cookies.</p></Section>
      <Section title="Your choices"><p>Signing out removes the session cookie and ends that session. You can also clear cookies in your browser settings, though that will not remove entries saved in your workspace. Your browser may cache ordinary site files.</p></Section>
      <Section title="Changes"><p>If analytics, advertising, or other optional tracking is introduced, we will update this notice and provide any choice required before using it. Third-party hosting may have its own technical logging practices, which will be described when a production host is selected.</p></Section>
    </>,
  },
  billing: {
    title: 'Billing and cancellations',
    intro: 'The current status of YLD plans, trials, charges, and refunds.',
    content: <>
      <Section title="No live checkout"><p>YLD has no live payment collection or paid self-service subscription. The plans shown on the pricing page are proposed offerings and cannot be purchased through this site today. An invited workspace owner may see a Stripe test checkout; it uses test payment methods and creates no real charge. A separately agreed paid pilot, if offered, will have its own written price, scope, and payment terms.</p></Section>
      <Section title="Before paid plans launch"><p>We will publish the final price in NZD, whether GST is included, billing frequency, trial start and end rules, when a card will be charged, cancellation steps, and refund terms before taking payment. A customer will need to actively agree to recurring charges. No payment or cancellation obligation arises from using the current site.</p></Section>
      <Section title="Problems and statutory rights"><p>If paid services become available, any refund terms will respect applicable rights under New Zealand law. There are no charges through this website to refund. The operator's billing contact must be published before a paid launch.</p></Section>
    </>,
  },
}

export function LegalFooter({ className = '' }: { className?: string }) {
  return <footer className={`legal-footer ${className}`}><span>YLD. / CHRISTCHURCH, NZ</span><nav aria-label="Legal information">{legalLinks.map(link => <a key={link.path} href={link.path}>{link.label}</a>)}</nav><a href="/">Home</a></footer>
}

export default function LegalPage({ page, nav }: { page: LegalPage; nav: ReactNode }) {
  const item = pages[page]
  return <div className="legal-page">{nav}<main className="legal-main"><span className="legal-kicker">YLD / LEGAL</span><h1>{item.title}</h1><p className="legal-intro">{item.intro}</p><p className="legal-date">Last updated {updated}</p><div className="legal-content">{item.content}</div></main><LegalFooter /></div>
}
