# Dreamscrol MVP spec

The prototype (`prototype.html`) shows the experience. This document covers what it takes to build the real thing for a Metro Detroit launch: stack, data model, the video pipeline, feed ranking, the mortgage and offer flow, compliance features, phases and rough costs. Strategy and the legal reasoning are in `PLAN.md`.

## 1. What the MVP must do

Buyers (no account needed to browse):
- Full-screen vertical feed of homes in the launch area. Video autoplays muted, price and monthly payment overlaid.
- Every listing has a public web page anyone can open without an account. Zillow's March 2026 rules refuse listings hidden behind a login.
- Like, comment, save, share. Saving, commenting, messaging, linking an agent and making offers ask for an account the first time.
- Listing details, "Can I afford it?" payment breakdown, request a tour or message.
- Guess the price, Couples mode, follow a home (price changes, open houses, public-record sale price), follow agents, inbox.

The money funnel:
- **Buying power:** income, monthly debts, cash for down payment and credit range give a price ceiling. No credit pull. Every card then shows "in your budget," "a stretch" or "over budget."
- **Compare lenders:** every participating lender, sorted by the buyer's choice of lowest APR, payment, fees or fastest close. No paid placement inside the comparison.
- **Pre-approval by the lender:** hand-off to the chosen lender's own application. The buyer can store the letter in Dreamscrol or upload one from any lender.
- **Agent:** link your agent, invite them, or request a free intro. The listing agent is offered first, with a dual-agency note.
- **Offer term sheet:** price, earnest money, down payment, financing, closing timeline, contingencies, co-buyer, attached pre-approval. It goes only to the buyer's own agent, who confirms a buyer agreement exists and turns it into the real purchase agreement.

Agents:
- Sign up with license number (verified against LARA's license lookup) and broker of record.
- Upload raw phone clips. The server cuts a 30–60 second vertical video with a hook, captions, room labels and music.
- Before posting, confirm the listing is Active or Coming Soon in Realcomp (or their MLS) and enter the MLS number. Coming Soon listings can't take tour requests.
- Broker name, broker phone and "Real Estate Broker" are drawn on every post and profile, with the broker name at least as large as the agent's (MCL 339.2512e).
- Every message and tour request on their listing goes to them.
- Seller report per listing: views, saves, shares, tour requests, traffic sources, common questions, and the ready-to-buy signal (pre-approved buyers who saved it, offers being prepared).
- Receive buyer intros for free, and receive offer term sheets from linked buyers.

Owners (phase 2):
- FSBO: ownership check against county records (Wayne, Oakland, Macomb registers of deeds) plus ID check. Free to post until Michigan counsel clears a flat fee.
- "Not for sale… unless?": owner names a price, picks who can see it, and chooses whether to hide the exact address.

Out of scope for MVP: MLS/IDX feed, live open houses, taking loan applications, multiple metros, web version beyond share links.

## 2. Recommended stack

| Layer | Choice | Why |
|---|---|---|
| App | React Native with Expo | One codebase for iOS and Android. `expo-video` handles a paged, preloaded video feed well. |
| Backend | Supabase (Postgres, auth, storage, row-level security, edge functions) | Relational data fits listings, follows, leads and offers. PostGIS for "near me." |
| Video | Cloudflare Stream or Mux | Upload, transcode to adaptive HLS, thumbnails, signed playback. |
| Auto-edit | Server job: ffmpeg for cutting, Claude (vision) to label rooms, pick the opening shot and write captions | The edit is the main time-saver for agents. |
| Moderation | Keyword filter plus a Claude classifier for comments, captions, live chat and AI-written text | Fair housing and abuse. |
| Lender quotes | Lenders submit rate sheets (or an API feed) for standard scenarios; Dreamscrol computes payments | Lets every lender be ranked on the same inputs. |
| Agent forms hand-off | Dotloop Loop-It API first, then SkySlope and zipForm | The term sheet lands in the agent's licensed forms system; Dreamscrol never produces the purchase agreement. |
| Identity checks | Stripe Identity or Persona | Owner verification for FSBO and off-market posts. |
| Payments | Stripe | Lender listing fees, Pro subscriptions, boosts. |
| Notifications | Expo push notifications | Price drops, sale outcomes, partner likes, offer status. |
| Analytics | PostHog | Watch time, funnel from view to budget to lender to offer. |

## 3. Data model (first pass)

```
users            id, phone/email, created_at
profiles         user_id, handle, display_name, role (buyer | agent | owner), avatar
agents           user_id, state, license_no, license_verified_at, broker_name, broker_phone,
                 broker_address, broker_license_no, team_name null
couples          id, user_a, user_b, created_at

listings         id, kind (agent | fsbo | offmarket), status (coming_soon | active | pending | sold | withdrawn),
                 mls_number null, owner_user_id, agent_user_id null, address, unit, hide_exact_address bool,
                 geo, neighborhood, municipality, school_district,
                 price, previous_price, beds, baths, sqft, year_built, lot_size, hoa_monthly,
                 est_new_owner_tax_rate, open_houses jsonb, caption, created_at
public_sales     parcel_id, address, sale_date, sale_price, instrument, arms_length bool  -- from public records
listing_media    id, listing_id, kind (main | seller_clip), stream_asset_id, duration_s,
                 rooms jsonb, approved_by_agent bool
listing_collabs  listing_id, user_id, role (seller)
verifications    id, user_id, listing_id, type (license | county_record | id), status, evidence_ref

likes, saves, follows_agent, follows_home, comments (with moderation), guesses, matches   -- as before

budgets          user_id, income, monthly_debts, down_payment, credit_band, first_time bool,
                 max_price, housing_cap, computed_at                -- buyer's own answers, never shared without consent
lenders          id, name, nmls_id, mi_license_no, listing_fee_plan, active bool
rate_quotes      lender_id, product (conv30 | fha30 | va30 | reno), credit_band, ltv_band,
                 rate, apr, points, lender_fees, est_days_to_close, quoted_at
lender_handoffs  id, user_id, lender_id, listing_id null, created_at   -- what was shown, in what order, why
ranking_logs     id, user_id, sort_key, inputs jsonb, result_order jsonb, created_at  -- proof of neutral ranking
preapprovals     id, user_id, lender_name, source (handoff | upload), amount, expires_at, file_ref

buyer_agents     buyer_user_id, agent_user_id, linked_at, agreement_confirmed_at null, via (link | invite | intro)
intros           id, buyer_user_id, agent_user_id, listing_id null, is_listing_agent bool, status, created_at
offer_terms      id, buyer_user_id, agent_user_id, listing_id, price, earnest, down_payment, financing,
                 close_days, inspection bool, appraisal bool, co_buyer_user_id null, preapproval_id null,
                 status (with_agent | sent_to_forms | submitted | withdrawn), forms_ref null, created_at

events           user_id null, anon_id, listing_id, type, watch_ms, position_s, created_at
leads            id, listing_id, from_user_id, type (tour | message | interest), routed_to_user_id, status
boosts           id, listing_id, paid_by, starts_at, ends_at, amount, targeting jsonb
notifications    id, user_id, type, payload jsonb, read_at
```

Rules enforced in the database:
- Leads on a listing route only to that listing's agent or owner.
- `offer_terms` can only be addressed to an agent in `buyer_agents` for that buyer. There is no path that sends terms to a listing agent or owner.
- Tours of MLS listings with a linked agent require `agreement_confirmed_at`, and so do offer submissions.
- Lender ranking reads only the buyer's sort key and inputs plus `rate_quotes`. It never reads `listing_fee_plan`. Every ranking is written to `ranking_logs`.
- Seller clips aren't public until the listing agent approves them.

## 4. Video pipeline

1. Agent picks 3–15 clips. Upload goes straight to the video provider with a signed URL.
2. A job samples frames and asks Claude to label rooms, score shots, choose the opening 2 seconds and draft a caption. The caption goes through the fair housing filter.
3. ffmpeg assembles a 30–60 second 9:16 cut with captions, room labels and a licensed music bed.
4. Price, monthly payment and broker disclosures are drawn by the app, not burned in. A price drop updates instantly, and the disclosure is always present and sized correctly.
5. The agent previews, reorders and publishes. A watermarked export with the broker disclosure burned in is made for TikTok and Reels reposts.

Photo-to-video slideshows are the fallback for homes without footage.

## 5. Feed ranking

- **Candidate pool:** active listings in the launch area, plus a small share of entertainment homes (Land Bank fixers, mansions, off-market) that keep casual viewers scrolling.
- **Score** = engagement quality × taste match × freshness × distance. Taste match is style, price band, neighborhood and size learned from the viewer's own behavior.
- **Budget fit** (once a buyer sets one) lightly boosts homes in range, but over-budget homes still appear. The feed is entertainment too.
- **Guaranteed first audience:** every new listing reaches a set number of likely local buyers in its first 48 hours.
- **Exploration:** about 1 in 5 cards is outside learned taste.
- **Never use protected characteristics or stand-ins.** Audit for differences between city and suburban ZIP codes in what listings, lenders and mortgage prompts people see.

## 6. Mortgage and offer flow details

**Buying power**
- Housing cap = the lesser of 28% of gross monthly income, or 43% minus other monthly debts.
- Solve for the price where principal, interest, estimated new-owner taxes and insurance fit under the cap, at an example rate for the buyer's credit band.
- Show the example rate with its APR. Label it an estimate, not an offer.

**New-owner taxes**
- Estimate as roughly half of market value (State Equalized Value) times the local homestead millage. Store a rate per municipality and school district.
- Detroit's effective homestead rate is about 3% of market value; inner-ring suburbs are often lower.

**Lender comparison**
- Every active lender that has a quote for the buyer's scenario is shown.
- The default sort is lowest APR; the buyer can change it.
- Each card shows rate, APR, points, lender fees, estimated payment, reviews and days to close.
- Lenders pay the same flat fee. No badges like "Top pick." Any lender ads live outside the comparison, labeled.

**Rate and payment disclosures**
- Any rate shown carries its APR.
- The monthly payment on each card is a triggering term under 12 CFR 1026.24. Its assumptions (rate, APR, down payment, term) need to be one tap away and clearly linked. Confirm the exact treatment with counsel.

**Hand-off**
- "Go to [Lender]'s application" opens the lender's own flow. Dreamscrol passes only what the buyer agrees to share (budget answers), and logs the hand-off.
- Dreamscrol doesn't collect application data or pull credit. Taking applications would need a Michigan mortgage broker license.

**Offers**
- The buyer builds a term sheet and picks their linked agent. Dreamscrol creates a loop in the agent's forms system (Dotloop first) with the property, parties and terms, or emails a PDF term sheet if the agent has no integration.
- Status updates come back from the agent.
- No AI price suggestions: offering market analysis for pay is a broker activity in Michigan.

## 7. Compliance built into the product

| Rule | Where it shows up |
|---|---|
| Realcomp Clear Cooperation: listings publicly marketed (including on public apps) go into the MLS within one business day; Coming Soon allows no showings | MLS number and status required before an agent posts; no tour requests on Coming Soon; delayed-marketing listings blocked until Realcomp confirms |
| MCL 339.2512e: broker name, broker phone or address, and "real estate broker" on every ad; broker name at least as large as the agent's or team's | Required agent fields; rendered on posts, profiles and burned into watermarked exports |
| MCL 339.2512: agents can't pay unlicensed people for referrals | Intros are free; agents pay only flat subscriptions or ad fees |
| MCL 339.2501: market analysis, negotiating and listing for pay are broker activities | No price advice, no offer transmission to sellers, FSBO product framed as advertising |
| Buyer agreements before touring (NAR settlement rules, Realcomp); MCL 339.2517 agency disclosure and dual agency consent | Agent confirms buyer agreement before tours and offers; dual-agency note on listing-agent intros |
| Michigan Mortgage Brokers, Lenders, and Servicers Licensing Act | Hand-off to lenders' own applications; no application taking without a license |
| RESPA Section 8 and the CFPB's 2023 comparison-platform opinion | Neutral ranking on buyer-chosen factors, all participating lenders, same fee for every lender, ranking logs |
| Reg Z advertising (12 CFR 1026.24) and Reg N | APR beside every rate; assumptions linked from payment figures; no misleading claims |
| ECOA/Reg B (referrers count as creditors), Fair Housing Act, Elliott-Larsen | Same lender list and ranking for every ZIP; feed and ad delivery audits; content filters |
| Section 230 limits (Roommates.com; Anderson v. TikTok) | No prompts or filters about protected traits; AI text filtered like user text |
| GLBA privacy and FTC Safeguards Rule | Budget answers and pre-approval letters encrypted, consent before sharing with a lender, breach plan |
| Michigan sale prices are public; taxable value resets after a sale | Sold prices from public records (arm's-length only); taxes estimated for a new owner |
| Zillow's March 2026 listing rules refuse login-walled listings | Public web page for every listing |
| Music licensing | Licensed library cleared for social reposts |

## 8. Build phases

| Phase | Length | What ships | Goal |
|---|---|---|---|
| 0. Validate | 3–4 weeks | Prototype in front of 20 Detroit-area agents, 5 lenders and 30 buyers. Hand-edited videos for 10 listings and a few Land Bank homes on TikTok and Instagram. Counsel and Realcomp questions answered. | Agents say "I'd post here." Lenders say "I'd pay a flat fee to be listed." |
| 1. MVP | 10–12 weeks | Feed, agent verification with automatic disclosures, auto-edit, social features, budget tool, lender comparison and hand-off, agent link and intro, offer term sheets to agents (Dotloop), seller report with ready-to-buy signal, inbox, push. | 50 agents, 10 lenders, 30% of new listings in the launch area, 5,000 weekly viewers, first offers routed. |
| 2. Owners and live | 6–8 weeks | FSBO (fees once cleared), "Not for sale… unless?", seller clips, live open houses, boosts, Pro. | Revenue from lenders, Pro and boosts. |
| 3. Scale | ongoing | More neighborhoods, then Grand Rapids or Ann Arbor. Decide on mortgage broker and real estate broker licenses. Learned ranking. | Second market reaches density faster. |

## 9. Team and rough costs

- **Team for phase 1:** two senior engineers (mobile; backend and video), a part-time designer, the founder selling to agents and lenders, and outside counsel for real estate and mortgage licensing.
- **Video delivery is the main running cost.** 10,000 weekly viewers watching 20 minutes a day is about 6 million minutes a month. At roughly $1 per 1,000 minutes delivered, that's about $6,000 a month. Check current pricing and keep videos short.
- **Other infrastructure** is likely a few hundred to a couple of thousand dollars a month at that size.
- **Legal:** Michigan real estate and mortgage-licensing counsel before launch. A Michigan 1st Mortgage Broker license, if pursued later, also brings NMLS filings, a net-worth requirement and individual loan originator licenses for staff who take applications.

## 10. Metrics to watch

- Viewers: sessions per week, homes watched per session, watch-through, 1-day and 7-day return.
- Funnel: budget completions, lender comparisons viewed, hand-offs per lender, pre-approvals stored, agents linked, intros accepted, offers routed.
- Agents: share of new listings posted, leads per listing, seller reports sent.
- Lenders: hand-offs and stated funded loans per lender (to justify the flat fee).
- Fairness: lender list, rates shown and mortgage prompts by ZIP code, city vs. suburbs.
- Growth: shares per listing, installs from shared links and watermarked reposts.
