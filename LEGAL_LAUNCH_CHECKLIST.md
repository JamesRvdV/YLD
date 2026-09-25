# YLD public launch checklist

The website now has Privacy, Terms, Cookies and Billing pages for the **current shared demo**. They are not final production documents. The following facts and product changes are still needed before taking real customer data or payment.

## Owner facts to provide

- Legal operator name, trading name, physical or postal address, NZBN if applicable, and a monitored contact email. Add these to the Privacy and Terms pages and an accessible site contact section. New Zealand Privacy Principle 3 calls for the collecting and holding agency's name and address and information about access and correction rights.
- Production hosting location and infrastructure, analytics, support, email and payment providers. Update privacy disclosures for actual recipients, retention, overseas transfers and any cookies or tracking.
- Final paid plans: accurate features and prices, GST treatment, billing cycle, trial conversion, payment timing, cancellation method, refunds and support channel. Update the Pricing and Billing pages together before enabling checkout.
- Evidence for any quantified customer savings or research statistic before publishing it as a marketing claim. The prior “27%” and “68%” claims have been removed from the demo site.

## Product work before real customer use

- Replace the hard-coded shared demo credentials and add real authentication, account separation and authorization to every data endpoint. The current API accepts planning, dish and actuals requests without an authenticated session.
- Decide how customers can request access, correction and deletion, and implement data retention, backups, incident response and privacy breach handling.
- Add an explicit subscription agreement step only when the final paid terms and checkout exist. Do not start recurring billing from a demo login or a preselected option.
- Review the production terms and privacy wording with New Zealand legal counsel using the actual legal entity, vendors and customer model.

## Reference guidance

- [Privacy Act Principle 3 — collection notice](https://www.privacy.org.nz/privacy-principles/3/)
- [Business.govt.nz — information customers must be told](https://www.business.govt.nz/operations/customer-complaints/information-you-must-tell-customers)
- [Commerce Commission — unfair contract terms and subscription rollovers](https://www.comcom.govt.nz/business/your-obligations-as-a-business/unfair-contract-terms/)
- [Consumer Protection — Fair Trading Act](https://www.consumerprotection.govt.nz/general-help/consumer-laws/fair-trading-act)
- [Office of the Privacy Commissioner — notifiable breaches](https://www.privacy.org.nz/responsibilities/privacy-breaches/notify-us/)
- [Department of Internal Affairs — commercial electronic messages](https://www.dia.govt.nz/Spam---Commercial-electronic-messaging-in-New-Zealand)
