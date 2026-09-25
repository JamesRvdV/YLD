# YLD public launch checklist

The website has Privacy, Terms, Cookies and Billing pages for an **invite-only pilot with fictional starting data**. They are not final production documents. The following facts and operations are needed before taking real customer data or payment.

## Owner facts to provide

- Legal operator name, trading name, physical or postal address, NZBN if applicable, and a monitored contact email. Add these to the Privacy and Terms pages and an accessible site contact section. New Zealand Privacy Principle 3 calls for the collecting and holding agency's name and address and information about access and correction rights.
- Production hosting location and infrastructure, support, email and payment providers. Resend handles invitation and sign-in email; confirm its privacy disclosures and any overseas transfers. Update this page if analytics or tracking is added.
- Final paid plans: accurate features and prices, GST treatment, billing cycle, trial conversion, payment timing, cancellation method, refunds and support channel. Update the Pricing and Billing pages together before enabling checkout.
- Evidence for any quantified customer savings or research statistic before publishing it as a marketing claim. The prior “27%” and “68%” claims have been removed from the demo site.

## Product and operations before real customer use

- One-use invitation links, HTTP-only sessions, workspace separation, access checks and CSRF checks have been implemented. Complete a live deployment check of invite delivery, sign-in, tenant isolation, reset and sign-out.
- Run FastAPI and SQLite on persistent storage behind HTTPS. Add automated database backups and a restore drill. This implementation is not suitable for an ephemeral serverless filesystem.
- Decide how customers can request access, correction and deletion, and implement retention and privacy breach handling. Name a privacy officer.
- Set `YLD_PUBLIC_URL`, `YLD_DB_PATH`, `RESEND_API_KEY` and a verified `YLD_EMAIL_FROM` on the server. Keep secrets out of the browser and repository.
- Add an explicit subscription agreement step only when the final paid terms and checkout exist. Do not start recurring billing from a demo login or a preselected option.
- Review the production terms and privacy wording with New Zealand legal counsel using the actual legal entity, vendors and customer model.

## Reference guidance

- [Privacy Act Principle 3 — collection notice](https://www.privacy.org.nz/privacy-principles/3/)
- [Business.govt.nz — information customers must be told](https://www.business.govt.nz/operations/customer-complaints/information-you-must-tell-customers)
- [Commerce Commission — unfair contract terms and subscription rollovers](https://www.comcom.govt.nz/business/your-obligations-as-a-business/unfair-contract-terms/)
- [Consumer Protection — Fair Trading Act](https://www.consumerprotection.govt.nz/general-help/consumer-laws/fair-trading-act)
- [Office of the Privacy Commissioner — notifiable breaches](https://www.privacy.org.nz/responsibilities/privacy-breaches/notify-us/)
- [Department of Internal Affairs — commercial electronic messages](https://www.dia.govt.nz/Spam---Commercial-electronic-messaging-in-New-Zealand)
