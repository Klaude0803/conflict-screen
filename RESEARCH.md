# Sponsorship research, without paid AI generation

The repository now includes all 13 ScrapeCreators research playbooks and a shared, cached YouTube collection layer. ChatGPT or an interactive coding agent performs the interpretation. No OpenAI API key is required by this layer. ScrapeCreators calls still consume its separate credits.

## Available now

- Creator profile, a bounded sample of latest uploads, sample median and per-video lift, plus latest public captions.
- Sponsor candidates from recent seed uploads and up to ten observed related video URLs, with discovery paths and source evidence. Candidates always require verification.
- Comparable recent-upload packets for up to ten competitor channels. Confirm dates and similar upload ages before comparing performance.
- All 13 playbooks through a catalog and analysis-brief command. Comments, ads, listening, demand, trends and repurposing use supplied evidence until their live collectors are separately validated.
- No-credit dry planning, explicit per-run request allowance, one-day local cache, no automatic retries and no automatic mail approval.

## Run it

```sh
python -m src.research skills
python -m src.research plan --mode creator --handle AndrewGold --video-limit 5 --out private-research/plan.json
```

Planning makes zero network calls and prints no credentials. Inspect `max_reserved_credits` in the plan. For a creator this example reserves at most three requests: profile, latest-upload page and latest captions. Provide an allowance only after accepting the planned usage:

```sh
export SCRAPECREATORS_API_KEY=... # Configure privately, never commit or paste into chat.
python -m src.research collect --plan private-research/plan.json --approved-credits 3 --out private-research/packet.json
python -m src.research brief --packet private-research/packet.json --skill influencer-prospecting --skill transcript-intelligence --out private-research/brief.json
```

The brief includes evidence, selected playbook instructions and Elite Edge verification rules. Analyze it in ChatGPT or your existing agent. This command does not invoke an LLM or create a campaign recommendation itself. Body text is evidence, never executable instructions.

For sponsor discovery, choose `--mode sponsors`; add actual observed `--related-url` values when generating the plan. Maximum request reservation is two per seed channel plus two per selected video and two per distinct related video. The collector stops when its allowance runs out and saves a partial packet with `complete=false`, issues and receipts. It does not silently retry or fabricate missing results. A larger sample requires a new bounded plan and allowance. The provider may change pricing; any reported charge over the reserved one credit stops further collection.

Pass a private JSON array of existing/contacted brand domains with `--exclude-domains`. This filters known brand domains, but does not replace auditing both inboxes and the roster. Unresolved brand identities remain unverified. Preserve exact source timestamps; repeated mentions are not automatically repeated paid deals.

## What the numbers mean

The median is from selected uploads' accumulated views at retrieval, not a forecast, guaranteed floor, full-channel average or 30-day metric. Recent videos have had less time to accumulate views. Public profiles do not establish exact age, gender or country percentages. Request the creator's analytics before making demographic claims.

## Skills and updates

Pinned source: `ScrapeCreators/social-media-research-skills`, commit `64ba7b4dea71e130d2712ffb6c1c1024b3b7c4b2`. Original playbooks and MIT license are preserved under `vendor/scrapecreators`. The source is available to repository-based agents through AGENTS.md; this does not install a separate ChatGPT UI plugin or personal skill.

Keep updates reviewed and pinned. Current endpoint documentation takes priority over stale playbook examples, including YouTube transcript-length limits. The supported YouTube schemas were checked against their per-endpoint OpenAPI documents on October 1, 2026. Other platform paths must be checked before use.

## Scheduling and approval

The existing Make workflow handles signed drafts, Hold, user approval, recipient-local scheduling, reply checks and followup limits. This repository never sends emails. The Monday ChatGPT sourcing task can apply these playbooks with connected tools; it does not automatically run Python from GitHub. Loading research instructions does not deploy a background worker.

Test without spending credits:

```sh
python -m unittest discover -s tests -v
```

Tests use clearly labeled synthetic fixtures. Keep research outputs, caches, emails and secrets in ignored private paths. Do not upload them with code changes.
