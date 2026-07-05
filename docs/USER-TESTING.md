# FrogsWork user testing (personal notes)

Checklist for family sessions, LinkedIn outreach, and billing smoke-test.

**Remote testers:** https://frogswork.com/user-test (enable intake in [admin](https://api.frogswork.com/admin) first).

---

## Order

1. **Family (in-person):** sister, then parents, then accountant
2. **LinkedIn (remote):** after sister retry fixes obvious blockers
3. **Billing (you only):** subscribe / login / portal / cancel on your PC

No subscribe flow during family or LinkedIn tests (trial limits are high enough).

---

## Family session (about 60 to 75 min)

**Before:** Clean PC (uninstall FrogsWork, delete `%APPDATA%\FrogsWork\`). Open `https://frogswork.com/user-test` (or the marketing site home if you prefer unguided start). Screen record with consent if they are comfortable.

**Facilitator:** Do **not** prompt them to return to the guide unless they are stuck for several minutes. The page has a sticky reminder at the top. Let the guide carry that instruction.

### Roles (do not mix these up)

| Role | Identity |
|------|----------|
| **Your business** | **Greenfield Café**, with sample logo, GST registered |
| **Customer** | **Riverside Office**, 8 Harbour Street, Fremantle WA 6160 |

### Part 1: Unguided (15 to 25 min, stay quiet)

Say once:

> Imagine you run a small business and a friend mentioned this invoicing app. You're on the website now. See if it looks like something you'd use, and if you want to try it, go ahead and get it working. Talk me through what you're thinking. I won't help unless you're stuck for a few minutes. When you're done exploring, come back to the guide tab and continue.

SmartScreen: **observe-fail** (help only after 3 to 5 minutes).

### Part 2: Guided scenarios (same as remote guide)

- **A:** Business = Greenfield Café (GST). Customer = Riverside Office. $300 ex GST ($330 total), change due date rule, invoice + PDF
- **B:** Prepare to send (manual email from their mail app), test email to crombie@korraone.com (`test -` + app subject), **Mark as sent**
- **C:** Fix Greenfield Café address and ABN in business details (15 Creek Road, Fremantle WA 6160; ABN 51 824 753 556)
- **D:** Greenfield Café logo, new invoice to Riverside Office, check PDF
- **E:** Past invoices, mark Riverside Office paid ($330)
- **F:** Dashboard totals (amount due with ex GST in brackets)

**Accountant:** Review PDF for AU sole trader.

---

## Billing session (you only)

See DEPLOY.md / admin. Exhaust trial; EARLY100 or card + cancel.

---

## Email templates (LinkedIn)

### 1: Initial ask

**Subject:** Quick favour: 30 min user test of my invoicing app?

Hi [Name],

I'm building **FrogsWork**, invoicing for Australian sole traders (https://frogswork.com). I'm looking for a few people to try it on their own Windows PC.

**About 45 to 60 minutes:** follow the steps on a link I'll send and submit written feedback at the end (no account or payment). A screen recording is optional but helpful if you're comfortable.

Interested? Reply and I'll send the link. No worries if not.

Thanks,  
[Your name]

### 2: After they opt in

**Subject:** FrogsWork user test link

Hi [Name],

Thanks for helping.

**Open this on your Windows PC:** https://frogswork.com/user-test

The page walks you through install, invoice tasks, dashboard, uninstall, and **Submit**. Written feedback is required; a screen recording is optional (Win + G if you want to record, mic not needed).

Please finish by [date].

Thanks again,  
[Your name]

**Before sending:** turn **Accepting submissions** ON at https://api.frogswork.com/admin. Turn OFF when done recruiting.

---

## Debrief mapping (operator)

Remote testers submit **7 text fields** (two feedback steps on the page). All must be non-empty; **None** is fine when a topic does not apply. Admin **Answers** JSON keys map to the full debrief like this:

| Stored key | Debrief topics |
|------------|----------------|
| `getting_started` | 1 hardest start, 2 install safety/confusion, 3 first-open expectations |
| `invoice_workflow` | 4 slow/unclear invoice step, 5 finding PDF, 6 fixing details |
| `confidence_trust` | 7 real-customer confidence, 8 PDF professionalism, 9 mistake worry |
| `expectations_gaps` | 10 expected behaviour, 11 missing features, 12 where invoices saved |
| `overall` | 15 use for real jobs, 16 first change, 17 Part 1 vs Part 2 preference |
| `pricing_trial` | 13 cost/account assumptions, 14 pricing/trial surprises |
| `anything_else` | Catch-all |

Older submissions may still use legacy keys (`hardest_step`, `broken_unsafe`, etc.).

---

Cloudflare setup: [DEPLOY.md](DEPLOY.md) → Remote user testing.
