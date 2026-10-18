# Dreamscrol MVP spec

The prototype (`prototype.html`) shows the experience. This document covers what it takes to build the real thing: stack, data model, the video pipeline, feed ranking, compliance features, phases and rough costs.

## 1. What the MVP must do

Buyers (no account needed to browse):
- Full-screen vertical feed of homes in one metro. Video autoplays muted, price and monthly payment overlaid.
- Every listing has a public web page anyone can open without an account. Zillow's March 2026 rules refuse listings hidden behind a login, so a gated listing could hurt agents.
- Like, comment, save, share. Saving, commenting and messaging ask for an account the first time.
- Listing details, "Can I afford it?" payment estimate, request a tour or message.
- Guess the price, Couples mode (pair two accounts, match on mutual likes).
- Follow a home (price changes, open houses, sale outcome) and follow agents.
- Inbox for alerts, replies and partner activity.

Agents:
- Sign up with license number, verified against the state license database.
- Upload raw phone clips. The server cuts a 30–60 second vertical video with a hook, captions, room labels, music and the price overlay.
- Before posting, confirm the listing is filed in the MLS (Active, Coming Soon or Flex). A public post counts as public marketing under NAR's Clear Cooperation Policy.
- Broker name and license number required; the broker name is drawn at least half the size of the largest contact info (TREC 535.155). Texas agents' profiles carry the IABS and Consumer Protection Notice links.
- Every message and tour request on their listing goes to them.
- Seller report per listing: views, saves, shares, tour requests, traffic sources, common questions. One tap to send it to the sellers.
- Invite sellers to add "From the sellers" clips, which the agent approves.

Owners (phase 2):
- FSBO: ownership check against county records plus ID check. Free to post in Texas until a Texas attorney clears a fee (see `PLAN.md`, section 4).
- "Not for sale… unless?": owner names a price, picks who can see it, and chooses whether to hide the exact address.

Out of scope for MVP: MLS/IDX feed, live open houses, multiple metros, web version beyond share links.

## 2. Recommended stack

| Layer | Choice | Why |
|---|---|---|
| App | React Native with Expo | One codebase for iOS and Android. `expo-video` handles a paged, preloaded video feed well. |
| Backend | Supabase (Postgres, auth, storage, row-level security, edge functions) | Relational data fits listings, follows and leads. PostGIS for "near me". Fast to start, no lock-in beyond Postgres. |
| Video | Cloudflare Stream or Mux | Upload, transcode to adaptive HLS, thumbnails, signed playback. Building this yourself isn't worth it. |
| Auto-edit | Server job: ffmpeg for cutting and overlays, Claude (vision) to label rooms, pick the opening shot and write captions | Agents shoot raw clips. The edit is the product's main time-saver for them. |
| Moderation | Fast keyword filter plus a Claude classifier for comments, captions and live chat | Fair housing and abuse. Keyword filter blocks the obvious cases instantly; the classifier catches coded language. |
| Identity checks | Stripe Identity or Persona for owner ID | Owner verification for FSBO and off-market posts. |
| Payments | Stripe | Boosts and Pro subscriptions; FSBO fees only once cleared. |
| Notifications | Expo push notifications | Price drops, sale outcomes, partner likes, replies. |
| Analytics | PostHog | Watch time, swipe-through, funnel to lead. |

## 3. Data model (first pass)

```
users            id, phone/email, created_at
profiles         user_id, handle, display_name, role (buyer | agent | owner), avatar
agents           user_id, state, license_no, license_verified_at, brokerage_name, brokerage_license_no
couples          id, user_a, user_b, created_at                 -- one active pair per user

listings         id, kind (agent | fsbo | offmarket), status (active | pending | sold | withdrawn),
                 owner_user_id, agent_user_id null, address, unit, hide_exact_address bool,
                 geo (PostGIS point), neighborhood, metro,
                 price, previous_price, beds, baths, sqft, year_built, lot_size, hoa_monthly,
                 open_houses jsonb, caption, created_at, sold_price null, sold_price_shareable bool
listing_media    id, listing_id, kind (main | seller_clip), stream_asset_id, duration_s,
                 rooms jsonb [{label, start_s}], approved_by_agent bool
listing_collabs  listing_id, user_id, role (seller)
verifications    id, user_id, listing_id, type (license | county_record | id), status, evidence_ref

likes            user_id, listing_id, created_at
saves            user_id, listing_id, created_at
follows_agent    user_id, agent_user_id
follows_home     user_id, listing_id
comments         id, listing_id, user_id, body, moderation (ok | blocked | review), created_at
guesses          user_id, listing_id, guess, accuracy, created_at
matches          couple_id, listing_id, created_at              -- written when both partners like

events           user_id null, anon_id, listing_id, type (impression | watch | rewatch | share | details),
                 watch_ms, position_s, created_at                -- feeds ranking and seller reports
leads            id, listing_id, from_user_id, type (tour | message | interest), body,
                 routed_to_user_id (always the listing agent or owner), status
boosts           id, listing_id, paid_by, starts_at, ends_at, amount
notifications    id, user_id, type, payload jsonb, read_at
```

Rules enforced in the database (row-level security):
- Leads on a listing can only be routed to that listing's agent or owner. This is the "your listing, your leads" promise, so it should be a hard rule rather than a setting.
- Seller clips aren't public until the listing agent approves them.
- `sold_price` is only shown when `sold_price_shareable` is true. Texas doesn't disclose sale prices publicly, so the agent or seller has to opt in.

## 4. Video pipeline

1. Agent picks 3–15 clips in the app. Upload goes straight to the video provider using a signed upload URL.
2. A job pulls the clips, samples frames, and asks Claude to label each clip's room, score shot quality, choose the opening 2 seconds and draft a caption.
3. ffmpeg assembles a 30–60 second 9:16 cut: hook first, then rooms in walk-through order, captions and room labels burned in, licensed music bed.
4. Price, monthly payment and the brokerage name are drawn by the app, not burned into the video. That way a price drop updates instantly and the brokerage line is always present.
5. The agent previews it, can reorder or drop clips, and publishes. A version with the Dreamscrol watermark is exported for reposting to TikTok and Reels.

For homes without video, a photo slideshow with slow pans can be generated from listing photos as a fallback.

## 5. Feed ranking

Version 1 can be simple and still feel personal:

- **Candidate pool:** active listings in the viewer's metro, plus a small share of "entertainment" homes (unusual, luxury or off-market) that keep casual viewers scrolling.
- **Score** = engagement quality (watch-through rate, rewatches, saves, shares per impression) × taste match (style, price band, neighborhood, size learned from the viewer's watches and likes) × freshness (new listings and price drops get a boost) × distance.
- **Guaranteed first audience:** every new listing is shown to a set number of likely local buyers in its first 48 hours, whatever its early engagement. This is the promise to agents that Instagram can't make.
- **Exploration:** about 1 in 5 cards is outside the viewer's learned taste so the feed doesn't get stuck.
- **Couples:** homes your partner liked get a small boost for you.
- **Never use protected characteristics** (race, religion, national origin, sex, familial status, disability) or stand-ins for them in ranking, ads or filters. Rank on the home and the viewer's own behavior.

Version 2 replaces the hand-tuned score with a learned model once there's enough event data.

## 6. Compliance built into the product

| Rule | Where it shows up |
|---|---|
| State advertising rules require the brokerage name on agent ads (Texas: TREC §535.155, broker name at least half the size of the largest contact info; IABS and CPN links under §531.18 and §531.20) | Broker name and license number are required fields, drawn at a compliant size on posts and profiles. Texas profiles carry the two required links. Per-state rules table before leaving Texas. |
| Fair Housing Act §3604(c), including for owners exempt from other parts of the Act | Comment, caption and chat filter. No demographic data, school "ratings" or neighborhood labels that act as stand-ins. Point school questions to district maps. |
| Section 230 protects hosting user content but not content the platform helps create (Roommates.com); one appeals court treated a recommendation algorithm as the platform's own speech (Anderson v. TikTok, 3d Cir. 2024) | Don't add prompts or filters that ask about protected traits. AI-written captions get the same fair housing check as user text. Ranking never uses protected traits or stand-ins, and is audited. |
| Housing ad targeting (U.S. v. Meta, 2022 Justice Department settlement) | Boosts target by location and home interest only. Check that delivery doesn't skew toward or away from groups of people. |
| Charging a cut of the sale price requires a broker license; Texas's broker definition may also cover advance fees to list a home in a listings publication (Tex. Occ. Code §1101.002) | No success fees, ever. FSBO posting is free in Texas until counsel clears a fee. |
| RESPA Section 8 limits payments for mortgage referrals; CFPB's 2023 advisory opinion covers steering on comparison tools | Lenders pay fair-market advertising fees not tied to closed loans, and are shown neutrally or labeled as sponsored. |
| NAR Clear Cooperation Policy: publicly marketed listings go into the MLS within one business day; some brokerages' Zillow Preview deals keep coming-soon listings exclusive | Agents confirm the listing is filed in the MLS (Active, Coming Soon or Flex) before posting. Don't promise pre-market exclusives. |
| Texas sale-price non-disclosure | Sale prices are shown only with the agent's or seller's opt-in. |
| Music licensing | Use a licensed library cleared for social reposts. |

## 7. Build phases

| Phase | Length | What ships | Goal |
|---|---|---|---|
| 0. Validate | 2–3 weeks | The prototype in front of 20 Austin agents and 30 buyers. A waitlist page. Hand-edited videos for 10 real listings posted to TikTok and Instagram as a test. | Agents say "I'd post here." Buyers watch more than 10 homes per session. |
| 1. MVP | 8–10 weeks | Feed, agent sign-up and verification, upload with auto-edit, likes/comments/saves/shares, leads to agents, seller report, Guess, Couples, inbox, push. iOS and Android via TestFlight and Play testing. | 50 agents, 30% of new listings in the launch area, 5,000 weekly viewers. |
| 2. Owners and live | 6–8 weeks | FSBO with verification (fees once cleared), "Not for sale… unless?", seller clips, live open houses, boosts. | First revenue. |
| 3. Scale | ongoing | Broker partnership and IDX feed to fill gaps, a second metro, learned ranking, lender partnership. | City #2 reaches the same density in less time. |

## 8. Team and rough costs

- **Team for phase 1:** two senior engineers (one mobile, one backend and video), a part-time product designer, and the founder selling to agents. An agency can do phase 1 but the ranking and video pipeline are core and worth owning.
- **Video delivery is the main running cost.** Example: 10,000 weekly viewers watching 20 minutes a day is about 6 million minutes a month. At roughly $1 per 1,000 minutes delivered, that's around $6,000 a month in streaming alone. Check current provider pricing before budgeting, and keep videos short.
- **Other infrastructure** (database, functions, AI edits and moderation, push, analytics) is likely a few hundred to a couple of thousand dollars a month at that size.
- **Legal:** budget for a real-estate attorney before launch: fair housing, licensing, RESPA, MLS rules, terms of service.

## 9. Metrics to watch

- Viewers: sessions per week, homes watched per session, watch-through rate, 1-day and 7-day return rates.
- Agents: share of new listings in the launch area posted on Dreamscrol, posts per agent per month, leads per listing, how often agents send the seller report.
- Growth loop: shares per listing, installs from shared links and watermarked reposts.
- Money: lead-to-tour rate, pre-approval starts, FSBO posts, boost revenue.
