import type { ReactNode } from 'react'

type WaitlistPromptProps = {
  eyebrow: string
  title: ReactNode
  onWaitlist: () => void
}

export default function WaitlistPrompt({ eyebrow, title, onWaitlist }: WaitlistPromptProps) {
  return <section className="waitlist-prompt">
    <span>{eyebrow}</span>
    <div>
      <h2>{title}</h2>
      <button type="button" onClick={onWaitlist}>JOIN THE WAITLIST <span aria-hidden="true">↗</span></button>
    </div>
  </section>
}
