# Positioning and Go-To-Market

A working plan, not a forecast. Every number here is a starting hypothesis to
be tested against real buyers.

## The strategic problem

As a general-purpose spreadsheet, this product loses. Google Sheets is free,
LibreOffice Calc is free, and Excel is already installed and has thirty years
of features. Competing on breadth means competing with three incumbents at a
price of zero.

The winnable position is narrower and defensible: **the offline financial
modeling tool for people who are not allowed to use cloud spreadsheets.**

In that frame the limitations stop being weaknesses:

| Property | As a general spreadsheet | As an offline modeling tool |
|---|---|---|
| No cloud sync | Missing feature | The entire point |
| No telemetry | Nobody notices | Passes security review |
| No macros | Missing feature | No macro attack surface |
| Deterministic, no live feeds | Limited | Reproducible and auditable |
| Small, single-purpose | Narrow | Fast, and reviewable |

The financial library, the seven models, the audit tool, and the
clone-based what-if analysis are the moat. Nothing free does all of that
well.

## Who buys it

**Primary — the constrained analyst.** Works in a regulated bank, insurer,
defence contractor, hospital group, or government supplier. Cloud
spreadsheets are blocked by policy. They already model in Excel but want a
purpose-built modeling tool, a second opinion, or something they can install
without a procurement cycle. They can expense a few hundred dollars without
approval.

**Secondary — the independent practitioner.** Fractional CFOs, boutique
corporate-finance advisors, small valuation and appraisal shops. They buy
tools that make them faster and look professional to clients. They value
the built-in models and clean PDF output.

**Tertiary — the security-conscious team.** Anyone who has been told to stop
putting financial data in cloud tools.

**Not the buyer.** Students, casual home users, and anyone whose first
question is "why not just use Excel?" Do not spend money reaching them.

## Pricing hypothesis

| Edition | Price | Terms |
|---|---|---|
| Personal | $79 one-time | 1 user, 3 devices, 1 year of updates |
| Business | $199 one-time | 1 named user, 3 devices, 2 years of updates |
| Site | $1,499 one-time | Unlimited users at one legal entity and location |

Perpetual with a paid major-version upgrade, not a subscription. The buyer
this product targets specifically dislikes recurring cloud-shaped costs, and
a perpetual licence works offline without renewal checks — which a
subscription would need, breaking the core promise.

Anchor against the alternative, which is a Microsoft 365 seat at roughly
$100 per user per year forever, plus a procurement process. A one-time $199
that expenses cleanly is an easy comparison to make.

Start higher than feels comfortable. Under-pricing a niche professional tool
signals that it is a hobby project, and raising prices later is harder than
discounting.

## Selling it

Use a merchant of record — **Paddle** or **Lemon Squeezy**. They take a
larger cut than Stripe and are worth it: they become the seller of record and
handle EU VAT, US sales tax, and global tax remittance, which is otherwise a
serious ongoing liability for a solo vendor selling internationally.

Wire the purchase flow to run `tools/licence_admin.py issue` and email the
key. Until volume justifies automating it, doing this by hand is fine and
gives you a reason to talk to every early customer.

## Finding customers

In rough order of expected return:

1. **Direct outreach.** Find people who have publicly complained about cloud
   spreadsheet restrictions in regulated work. Offer a free licence for
   feedback. Ten real conversations will teach you more than any launch.
2. **Communities.** r/FPandA, r/financialmodelling, Wall Street Oasis,
   actuarial and valuation forums. Participate genuinely for months before
   mentioning the product; these communities punish drive-by promotion.
3. **Content that ranks.** Write the pages these buyers search for: "Excel
   alternative for air-gapped networks", "offline DCF model", "spreadsheet
   with no telemetry". Long-tail, low-competition, high-intent.
4. **Compliance angle.** A short, honest security note — no network calls, no
   telemetry, no macro surface, here is how to verify it — is a document a
   sympathetic analyst can forward to their security team. That document may
   be the single highest-leverage asset you can write.
5. **Product Hunt / Hacker News.** One-day spikes of the wrong audience.
   Worth doing once, not worth building around.

## What to fix first, judged commercially

1. **Screenshots and a demo video.** Nobody buys unseen software. This is the
   highest-return remaining work, and it is not code.
2. **A landing page** with the models visible above the fold.
3. **The security note** described above.
4. **Cell comments** — reviewers annotate models constantly, and its absence
   will come up in every trial.
5. **Auto-update or an update check.** Perpetual licences still need a
   patch path.

## Honest risks

- **The market may be too small.** Validate by talking to buyers before
  investing further. If ten target users will not commit to a purchase, the
  positioning is wrong or the need is not acute.
- **A solo vendor is a procurement risk.** Enterprises ask who supports this
  in three years. A clear support policy and a documented, open file format
  are partial answers.
- **Excel is genuinely very good.** The pitch is never "better than Excel."
  It is "available where Excel is not, purpose-built for modeling."
- **Missing features surface late.** Every trial will find something. Budget
  time to respond rather than treating 1.0 as finished.

## What success looks like early

Ten paying customers who did not know you personally. That is enough to prove
someone will pay, and to tell you what to build next. Optimise for
conversations, not downloads.
