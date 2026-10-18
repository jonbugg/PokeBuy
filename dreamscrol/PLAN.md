# Dreamscrol plan

A full-screen vertical feed of homes, one per swipe. Video first, price on top, likes, comments and shares. People come because it's fun to watch. Dreamscrol makes its money on what happens next: finding out what you can afford, comparing lenders, getting pre-approved, and sending an offer through your own agent.

Launch city: **Metro Detroit.**

Research date: October 18, 2026. The facts below come from two rounds of web research that read search-result summaries of statutes, regulators, MLS pages, filings and trade press, not the primary documents. Nothing here is legal advice. Section 9 lists what to ask Michigan counsel. The earlier Austin version of this plan is in git history.

---

## 1. The bet

Most people scrolling homes aren't buying yet. They watch for fun: Zillow Gone Wild has about 2.3 million Instagram followers and an HGTV show. Dreamscrol turns that attention into buyers by asking one question at the right moment: **what can you actually afford?**

The funnel:

1. **Watch.** Swipe through homes, like, save, play Guess the price, match with your partner.
2. **Budget.** Four questions, no credit check, and every home is marked "in your budget," "a stretch" or "over budget."
3. **Lenders.** Every participating local lender side by side, ranked by APR or whatever the buyer picks. The buyer applies with the lender they choose.
4. **Agent.** Link your agent, or get connected to one. The listing agent is offered first.
5. **Offer.** Build the terms, attach a pre-approval from any lender, and send it to your agent. Your agent writes and submits the real offer.

**Who actually buys** (NAR 2025 and 2026 reports):
- 4.06 million existing homes sold in 2025.
- First-time buyers were 21% of buyers, and their median age is 40. The median buyer overall is 59.

Expect a gap between views and closings. The money comes from the small share of viewers who move down the funnel.

## 2. Why Detroit

- **You're here.** You can recruit agents face to face, film sample content and show up at open houses.
- **Detroit homes already go viral.** $1,000 Land Bank homes, $38K brick fixers, Boston-Edison mansions. The Detroit Land Bank Authority runs daily auctions and "Own It Now" sales starting at $1,000.
- **It's affordable**, so first-time buyers and the "can I afford it?" question are front and center:
  - City of Detroit median sale price is about $100K (Redfin, October 2026; Realcomp put it at $105.5K in June).
  - Metro median was $300K in August 2026 (Realcomp) and $331K in September (RE/MAX), with about 27–34 days on market.
- **Sale prices are public in Michigan.** "Follow a home and see what it sold for" works for every home.
- **Taxes are a real affordability issue.** Detroit's effective homestead property tax rate is about 3% of market value, the highest of any large US city (Lincoln Institute). Taxes reset when a home sells, so buyers often see a jump. Showing the true monthly cost is a genuine service here.
- **One MLS covers most of the metro:** Realcomp, owned by seven local Realtor associations.

**The catch: Rocket is headquartered downtown.** It owns Redfin and Mr. Cooper, and offers Redfin buyers rate buydowns or credits when they use a Redfin or partner agent and Rocket financing. It's recruiting Detroit agents. UWM, the largest wholesale lender, is in Pontiac. Dreamscrol is launching on a vertically integrated competitor's home turf. The answer is to be the neutral option: every lender, every agent, the buyer's choice.

**Where to start:** a few neighborhoods, not the whole metro. For example, Corktown, Midtown/Woodbridge, Boston-Edison and Lafayette Park in the city, plus Ferndale or Royal Oak as a suburban test.

## 3. What's already out there

| Who | What | Takeaway |
|---|---|---|
| realestate.com.au (Australia's #1 portal) | Personalized swipe feed of listing walkthrough videos since July 2026 | The format works, and incumbents can add it |
| Klipster (New York) | Nearly the same idea, launched October 2025 | No traction numbers published; no mortgage or owner layer |
| Scroll Home (London) | Video-first listing app, $2.6M seed | Same model, UK |
| Rocket + Redfin | Search, agents and mortgage bundled with discounts | The integrated competitor, based in Detroit |
| Zillow | Zillow Home Loans grew purchase volume 95% year over year in Q2 2026; agents get "contact agent" leads | Same funnel idea, but buyers go to paying agents and an in-house lender, which is what regulators are now questioning |
| LendingTree | Lender comparison, licensed as a mortgage broker including in Michigan | The licensing model for a lender marketplace |
| TikTok, Instagram | Where agents post video today | Only about 16% of Realtors use TikTok for work |

**What makes Dreamscrol different:**
- It's fun first: Guess the price, Couples matching, live open houses, sold-price reveals, owners' stories.
- It's neutral where others steer. Every lender is ranked the same way and none can pay to move up. Buyers can use any lender's pre-approval. Listing agents keep their leads, and introductions to buyer's agents are free.
- It shows the real monthly cost with taxes reset for a new owner, which matters most in Detroit.

## 4. What Dreamscrol does and doesn't do

The licensing lines shape the product. This is the design:

| Step | Dreamscrol does | Dreamscrol doesn't |
|---|---|---|
| Budget | Estimates buying power from the buyer's own answers | Pull credit or take a loan application |
| Lenders | Shows every participating lender, sorted by APR, payment, fees or speed (the buyer picks). Shows APR next to every rate. Charges each lender the same flat listing fee | Rank by who pays, label a "top pick," sell better placement, or put paid placements inside the comparison |
| Pre-approval | Hands the buyer to the chosen lender's own application. Stores the letter the buyer gets back | Say "get pre-approved by Dreamscrol" (that would need a Michigan mortgage broker license) |
| Agent | Lets buyers link their agent or request a free intro. Offers the listing agent first, with a note on representing both sides | Charge agents per lead, per tour or per closing (Michigan bars agents from paying unlicensed referrers) |
| Offer | Captures the buyer's terms as a term sheet and sends it to the buyer's own agent, ideally straight into the agent's forms system | Send offers to sellers or listing agents, suggest offer prices, or write the purchase agreement |
| Listings | Shows agent and owner posts with the required broker disclosures | Let agents post listings that aren't filed in the MLS |

## 5. Why agents post

1. **Their listing, their leads.** Tour requests and messages go to the listing agent. When a buyer asks for an agent, the listing agent is offered first.
2. **The ready-to-buy signal.** The seller report shows how many **pre-approved** buyers saved the home, and how many offers buyers' agents are preparing. No other channel tells a listing agent that.
3. **Free buyer introductions.** Agents get matched with buyers who already know their budget and have a lender lined up.
4. **The seller report** for listing pitches: views, saves, shares, tour requests, top questions.
5. **Guaranteed first audience** for every new listing, and posting that takes about a minute with an AI edit.
6. **Status:** follower counts and city leaderboards.

Supply is still the hardest part, because most agents don't make video. Plan for AI editing from raw phone clips and photo-to-video as a fallback.

## 6. Michigan rules that shape the product

### Listing posts and the MLS
- Realcomp requires a listing to be filed in the MLS within one business day of public marketing, and its definition includes "applications available to the general public." A Dreamscrol post counts.
- Realcomp's Coming Soon status allows no showings, including by the listing agent, and must go active within 5 business days.
- Realcomp adopted NAR's 2025 "delayed marketing" option; the delay length wasn't found. Treat delayed-marketing and office-exclusive listings as not postable until Realcomp confirms.
- **Product:** agents confirm the listing is Active or Coming Soon in the MLS (with its MLS number) before posting. No tour booking on Coming Soon.
- FSBO and "Not for sale… unless?" posts by owners are outside this rule.
- No Michigan law on private listings was found.

### Agent ads (MCL 339.2512e)
- Every ad must show the broker's name, the broker's phone number or street address, and a statement that the advertiser is a real estate broker.
- When an agent or team is named, the broker's name must be in **equal or larger type**.
- There's no special social media rule; the statute covers any ad.
- **Product:** broker name, phone and "Real Estate Broker" render automatically on every agent post and profile, with the broker name at least as large as the agent's. The prototype does this.

### Referral fees (MCL 339.2512)
- Michigan agents can't pay unlicensed people for referrals, and Michigan Realtors says "there is no gray area."
- Michigan Realtors has sued an unlicensed operator before (Remark Consultants, 2001) and won.
- **Product:** agent intros are free. Agents pay only flat subscription or advertising fees. Per-lead, per-tour and per-closing fees would need a Michigan real estate broker license.

### FSBO fees
- Unlike Texas, Michigan's broker definition (MCL 339.2501) has no clause about advance fees for listing publications.
- A flat fee for self-serve ad space looks permissible. Risk rises if Dreamscrol calls it a "listing," gives pricing opinions ("market analysis" is a broker activity), handles offers, or takes success fees.
- **Product:** FSBO stays free at launch. A flat posting or boost fee is likely fine in Michigan after counsel signs off.

### Buyer agreements and representing both sides
- Since August 17, 2024, MLS agents working with a buyer need a written buyer agreement before the first tour, including video tours. Realcomp restates this.
- Michigan requires a written agency disclosure (MCL 339.2517), and one agent can represent both sides only with written consent.
- **Product:** a linked agent confirms a buyer agreement exists before Dreamscrol books tours or routes offers. Intros to the listing agent carry a dual-agency note.

### Sale prices and taxes
- Michigan is a disclosure state. Property Transfer Affidavits are "not confidential," and Detroit publishes a property sales dataset. Filter out non-arm's-length sales.
- Taxable value resets to State Equalized Value (about half of market value) after a sale.
- **Product:** estimate taxes as a new owner would pay them, not from the seller's current bill.

### Mortgage marketplace
- **Licensing:** Michigan's Mortgage Brokers, Lenders, and Servicers Licensing Act treats anyone who "serves or offers to serve as an agent for a person in an attempt to obtain a mortgage loan" as a mortgage broker. Taking or sending applications fits that. LendingTree holds a Michigan 1st Mortgage Broker license. Three paths:
  1. **Neutral rate display plus a hand-off to each lender's own application.** Dreamscrol takes no application data. Lowest licensing exposure. **Start here.**
  2. Get a Michigan 1st Mortgage Broker license through NMLS and take applications. Staff who take applications need individual loan originator licenses.
  3. Partner with a licensed marketplace and embed it.
- A pending bill, HB 6177 (July 2026), would replace Michigan's mortgage licensing laws. Track it.
- **RESPA Section 8:** the CFPB's 2023 advisory opinion on comparison platforms appears to still be in effect.
  - It's illegal to show lenders non-neutrally in a way that steers buyers while being paid partly for that.
  - Disclosure doesn't cure it.
  - Safe pattern: neutral ranking on buyer-chosen factors, all participating lenders shown, the same fee for every lender.
  - The CFPB is barely functioning, but private class actions with triple damages (Taylor v. Zillow was refiled in August 2026), state attorneys general and the FTC are active.
- **Steering:** the October 15, 2026 Warren/Booker letter asks the FTC to look at agents steering buyers to affiliated lenders. Dreamscrol accepts pre-approvals from any lender and never rewards agents for lender choice.
- **Rate ads:** any rate shown must come with its APR, and monthly payment figures trigger extra disclosures (12 CFR 1026.24). This applies to non-lenders too.
- **Credit pulls:** if Dreamscrol ever runs soft pulls, it needs separate, logged consent. A law restricting mortgage "trigger leads" took effect around March 2026.
- **Data security:** GLBA privacy and the FTC Safeguards Rule likely apply.

### Fair housing and fair lending
- Fair Housing Act, Michigan's Elliott-Larsen Civil Rights Act, and the Equal Credit Opportunity Act. ECOA's definition of "creditor" covers anyone who regularly refers applicants to lenders.
- In Detroit, showing fewer lenders, worse rates or less mortgage marketing to city ZIP codes than to the suburbs would look like redlining.
- **Product:**
  - The same lender list and ranking for every ZIP code.
  - Comment and caption filters.
  - No demographic data or stand-ins in ranking or ads.
  - Regular audits of who sees what.

### Zillow's listing rules
Zillow's March 2026 rules no longer ban listings first marketed on a public app, but they refuse listings behind a login. Keep every listing viewable without an account.

## 7. How Dreamscrol makes money

1. **Lender listing fees.** Every participating lender pays the same flat monthly fee, or the same per-lead fee if counsel approves. No placement upsells. This is the biggest early revenue line, and it's why the funnel matters.
2. **Agent Pro subscription:** unlimited AI edits, seller reports with comparisons, live open houses, priority in the first-48-hours audience. Flat monthly, never per lead.
3. **Boosts** for agents, builders and (after counsel signs off) FSBO sellers. Location and interest targeting only, never protected traits.
4. **Builders and new construction:** paid placement for new communities.
5. **Later, licenses that unlock more:**
   - A **Michigan mortgage broker license** lets Dreamscrol take applications and earn broker compensation.
   - A **Michigan real estate broker license** makes referral fees legal.
   - Both increase regulatory weight and conflicts. Decide after the first area works.

**Not allowed without licenses:** per-lead or per-closing fees from agents, lender rankings that respond to payment, and requiring a Dreamscrol-marketplace pre-approval to make an offer.

## 8. Launch plan

**Phase 0, validate (3–4 weeks)**
- Show the prototype to 20 Detroit-area agents across brokerages. Ask what they'd post and what their brokerage allows.
- Show it to 5 local lenders and credit unions. Would they pay a flat fee to be listed next to everyone else?
- Hand-edit vertical videos for 10 real listings with agent permission, plus a few Land Bank homes. Post them on TikTok and Instagram and measure watch time, DMs and "what would my payment be?" questions.
- Ask Realcomp compliance about agent posts on third-party apps and the delayed-marketing window.
- Meet with Michigan real estate and mortgage-licensing counsel (section 9).

**Phase 1, MVP in one area (8–10 weeks):** feed, agent posting with automatic broker disclosures, budget tool, lender comparison with hand-off to lenders, agent link and intro, offer term sheets to agents, seller report with the ready-to-buy signal. See `MVP_SPEC.md`.

**Density goal before expanding:** 30% or more of new listings in the launch area on Dreamscrol, 5,000 weekly viewers, 10+ participating lenders, and offers flowing through linked agents.

**Phase 2:** FSBO with flat fees once cleared, live open houses, Pro, boosts, more neighborhoods.

**Phase 3:** a second Michigan market (Grand Rapids or Ann Arbor) before leaving the state, since the rules carry over. Decide the license questions.

## 9. Questions for Michigan counsel

Real estate:
1. Can Dreamscrol charge FSBO owners a flat fee to post or boost without a broker license under MCL 339.2501?
2. Is a free agent-intro feature, paid for by a flat agent subscription, consistent with MCL 339.2512? Where's the line between a subscription and a referral fee?
3. Does sending a buyer's term sheet only to the buyer's own agent stay outside "negotiating" under MCL 339.2501(u)?
4. Exactly what must appear on agent video posts and profiles under MCL 339.2512e?
5. Under Realcomp rules, can agents post Coming Soon or delayed-marketing listings on Dreamscrol?

Mortgage:
6. Does neutral rate display with a hand-off to each lender's own application require a Michigan mortgage broker license? What about per-lead fees from lenders? Ask DIFS for its position.
7. What does a compliant lender fee look like under RESPA Section 8 and the CFPB's 2023 opinion: flat monthly, per lead, or per application?
8. What Reg Z disclosures are needed next to the monthly payment shown on each home?
9. What ECOA and fair housing monitoring should be in place for the feed and the lender list?

Company:
10. If a lender invests, what terms avoid an affiliated business arrangement or a disguised referral payment? No placement rights, no volume-linked terms.

## 10. If you work at a mortgage lender

- Read your employment agreement's invention-assignment, confidentiality, non-compete and moonlighting clauses. Michigan doesn't appear to have a law protecting inventions made on your own time, so the contract governs.
- Get a written IP carve-out or employer acknowledgment before building further.
- Build only on personal time and equipment.
- Keep your employer neutral in the lender rankings, or off the platform, until you leave.
- If you're a licensed loan originator, check NMLS sponsorship rules. Never take compensation from your employer tied to platform referrals.

## 11. Biggest risks

| Risk | What to do about it |
|---|---|
| Agents don't post | AI edit, photo-to-video fallback, recruit in person in a small area, the ready-to-buy signal |
| Rocket/Redfin bundle discounts | Be the neutral choice: every lender, any pre-approval, listing agents keep their leads |
| Mortgage licensing | Start with hand-offs to lenders' own applications; get licensed later if the numbers justify it |
| RESPA steering claims | Neutral ranking logged and auditable, same fee for every lender, no paid placement in the comparison |
| Fair lending and fair housing in Detroit | Same lenders and rankings for every ZIP, content filters, regular audits |
| Views without deals | Measure budget completions, lender hand-offs, agent links and offers, not just views |
| A portal ships the same feed | Win one area's agents and lenders first |

## 12. Research notes

Verified (from search summaries of primary or official sources):
- Realcomp ownership, Clear Cooperation policy and Coming Soon rules: realcomp.moveinmichigan.com.
- MCL 339.2512e (ad rules), 339.2512 (referral fees), 339.2501 (broker definition), 339.2517 (agency disclosure).
- Michigan Association of Realtors v. Remark Consultants (2001).
- Property Transfer Affidavit and Detroit property sales dataset; Proposal A uncapping.
- Detroit and metro prices: Redfin, Realcomp via the Detroit News, RE/MAX of Southeast Michigan; Lincoln Institute effective tax rates.
- Detroit Land Bank Authority programs; Rocket Preferred Pricing and the Rocket–Compass alliance.
- MCL 445.1651a (mortgage broker definition); LendingTree licensing disclosures; HB 6177 of 2026.
- CFPB 2023 advisory opinion on comparison-shopping platforms; 12 CFR 1026.24; ECOA's Reg B 1002.2(l).
- Taylor v. Zillow refiled August 17, 2026; Warren/Booker letter October 15, 2026.
- Plus the first round: Clear Cooperation status, Zillow's March 2026 rule change and Preview, Section 230 cases, competitors, NAR buyer statistics.

Not verified: Realcomp's delayed-marketing period; DIFS's position on lead generators; total tax rates for Ferndale and Royal Oak; whether Zillow and Bankrate hold Michigan broker licenses.
