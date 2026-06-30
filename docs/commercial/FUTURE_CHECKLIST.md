# FrogsWork future work checklist

Tick items as you go: change `[ ]` to `[x]`. Add notes under each item when you start or finish it.

**How to use:** Pick one row, read the notes block, do the work, tick the box, jot what you did. Operator-only items don't need code.

---

## Brand and assets

### Splash logo (`splash-logo.png`)

- [ ] Add `client_app/assets/splash-logo.png` (512×512 PNG, transparent; see `assets/README.md`)

**Notes:** I'm deferring this until i can do it properly/get an artist to work with to do it. At most i might take my placeholder and remove teh white background so taht it has a transparent background

---



### Windows icon (`app.ico`)

- [ ] Add `client_app/assets/app.ico` (16, 32, 48, 256 px in one ICO)

**Notes:** Same as Splash logo, waiting till i can work with an artist. if i update the logo to remove the transparent background ill do it here too. But deferred for now

---



### Optional brand extras

- [ ] Marketing site favicon
- [ ] PDF header watermark (optional)
- [ ] Hide **Settings → Logo design** when final art ships (`SHOW_LOGO_DESIGN_SETTINGS = False` in `app_config.py`)

**Notes:** 

Same as the splash logo and app ico.

I do want to eventually allow users to put their logos on their invoices. and i also would like to put my logo once designed on the invoices to app users for their fees.

Once logo is finalised ill remove the setting requesting help, ill probably remove the code instead of just toggling false.

---



## Legal and acceptance



### Professional legal review

- [ ] Lawyer or vetted template review of `marketing_site/privacy.html` and `terms.html` for AU sole-trader desktop software

**Notes:** Once the app is in a shippable state and possible users, i will establish the privacy and t&c requirements myself.

---



### Welcome privacy acknowledgement

- [ ] Optional “I understand” checkbox on welcome final step (pairs with privacy blurb on `welcome_done.html`)

**Notes:** This is necessary, if i can integrate this into the installer instead of the app welcome setup that would be better. else then a i understand check box is needed.

---



### Account signup terms

- [ ] Server-side check that `accept_terms` was posted on account create (checkbox exists in UI only today)

**Notes:** 

---



### Installer terms

- [ ] “I agree to Terms and Privacy” on first run in `installer/FrogsWork.iss` (links to frogswork.com)

**Notes:** 

---



### Policy changelog

- [ ] Short changelog entry in `docs/commercial/` when privacy/terms change

**Notes:**

---



## Support (users)



### Contact form on website

- [ ] Replace mailto-only `contact.html` with a form (or hosted form) that emails you

**Notes:** 

---



### Copy diagnostics from app

- [ ] In-app **Copy diagnostics** (app version, OS; no customer/invoice data)
- [ ] Optional: open support URL with version/OS as query params
- [ ] Update support copy that mentions diagnostics (currently promises more than exists)

**Notes:**

---



### Support content gaps

- [ ] Uninstall + export PDFs article (or expand `issues.html` / `troubleshooting.html`)
- [ ] Offline vs account: when sign-in is required
- [ ] Dedicated **About** page on frogswork.com (optional)

**Notes:**

---



## Support (operator / payments)



### PayID / donations

- [ ] Add live PayID on `contact.html#developer` (or separate page)
- [ ] Optional: Stripe or Ko-fi link for tips / support development

**Notes:**

---



## Account onboarding (nice-to-have)



### Skip steps when data exists

- [x] Skip business/customer onboarding when `settings.json` / `customers.json` already populated from free-tier use

**Notes:**

---



### Less repeated copy

- [x] Trim pricing duplication between welcome and account signup flow

**Notes:**

---



## Splash and first launch (optional)



### Splash through welcome

- [ ] Keep splash visible through welcome step 1 load (optional; code already waits for paint + min duration)

**Notes:**

---



### Verify on packaged build

- [ ] Cold start on a real PC: splash shows ≥3s before wizard/home (needs `splash-logo.png` for full effect)

**Notes:**

---



## Operator go-live (not client code)



### ABN

- [ ] Obtain ABN for KorraOne / billing entity

**Notes:**

---



### Pi billing config

- [ ] Set `KORRAONE_ABN`, letterhead, BSB/account/PayID in `/etc/frogswork/billing.env` (see `production.env.example`)
- [ ] Configure `SMTP_*` for platform fee invoice emails
- [ ] Test `auto_billing.py` on staging month
- [ ] Send yourself a test platform invoice; verify PDF and payment details

**Notes:**

---



### Windows code signing

- [ ] Sign `FrogsWork-*-setup.exe` (download page still warns “not signed yet”)

**Notes:**

---



## Marketing (when you want more polish)



### FAQ page

- [ ] Add `faq.html` and link from home/pricing if home still feels dense

**Notes:**

---



### Deploy marketing updates

- [ ] Push site changes to Cloudflare / `marketing_site/` deploy

**Notes:**

---



## Already done (reference)

These came from the plan; no action unless you want to re-verify.

- [x] Near-term: send page, offline-first nav, per-line GST, perf fixes
- [x] Welcome: 3 steps, privacy on done, installer handles PDF folder
- [x] Account: password on final step
- [x] Marketing: simpler home, support hub, frogswork.com support links
- [x] Support basics: support / issues / troubleshooting / contact pages
- [x] Splash timing fix in `desktop_shell.py`
- [x] ABN go-live checklist in `DEPLOY.md`
- [x] Support email `crombie@korraone.com` in `app_config.py` and contact page

**Notes:**

---

