# Avocado Shack

**Source and documentation for Avocado Shack's website and Hass, Michael Wolfe's planned store assistant.**

The working website is a food catalog for in-person visits, with the North Coast Hiking Club and a newsletter signup (not open on the static build). Hass will let Michael manage it by sending texts, photos and voice notes. Hass's editing tools already work on test conversations (fixtures); the messaging connection to a phone is planned, not running. The website has a private preview but no public deployment.

## Start here

| What you need | Read this |
| --- | --- |
| Hass plan, milestones and owner setup | [Hass project plan](docs/hass/README.md) |
| Complete prioritized feature list | [Feature backlog](docs/hass/FEATURES.md) |
| Hermes's next assignment | [Hermes start instructions](docs/hass/HERMES_START.md) |
| Every message Hass understands | [Commands](docs/hass/COMMANDS.md) |
| Step-by-step texts for Michael's phone | [Phone guide](docs/hass/PHONE_GUIDE.md) |
| What Hass cannot do yet | [Known limits](docs/hass/LIMITS.md) |
| What to do when a check reports a problem | [Support path](docs/hass/SUPPORT.md) |
| The steps G does to connect the text channel | [Connecting the channel](docs/hass/CONNECT.md) |
| Release steps and the decisions still open | [Release and handover](docs/hass/HANDOVER.md) |
| Implementation and verification requirements | [Technical plan](docs/hass/IMPLEMENTATION.md) |
| Existing site's operation and private data locations | [Project handoff](HERMES_HANDOFF.txt) |
| Website files, event format and checks | [Storefront guide](storefront-mockup/README.md) |
| Decisions and actual completed work | [Build ledger](BUILD_LEDGER.md) |

Use [GitHub Issues](https://github.com/tidepool-labs/avocado-shack/issues) for the work queue. Use this repository for reviewed source, content, optimized web images and project documentation. Start new work from the latest `main`, use a `codex/` branch, and keep changes small enough to review. GitHub stores the project; it is not the website host.

## Current website

- 170 food listings and 26 maker profiles, with category/producer filters and town search.
- Product descriptions, documented locations and organic labels; maker stories expand within cards.
- Separate `/hike` page with maps, sample invitations and a dummy RSVP.
- Forms depend on where the site runs. On the static build (a plain web host), the signup and RSVP forms send and save nothing and say that signup is not open. The sample RSVP on the sample invitation sends and stores nothing anywhere. Only the separate local community server (`storefront-mockup/community-server.py`, loopback only) saves real-event signups and RSVPs, outside Git. No email delivery is connected; no real hikes are scheduled.
- Hass can already, on fixture conversations, add, edit, hide and restore products and makers, draft a real hike, ask for explicit approval, show a checked preview and undo one change without losing later edits. See the [commands](docs/hass/COMMANDS.md), the [phone guide](docs/hass/PHONE_GUIDE.md) and the [known limits](docs/hass/LIMITS.md). Approving a change saves it in the writer checkout; it does not appear on a served website by itself. No phone, live channel, owner trial or signed-off handover exists yet.
- `python3 hass/sitegen.py --publish DIR` builds an allowlisted static copy of the site into a new or empty folder outside the repository. It never serves or copies `storefront-mockup/` as a whole. Building it is not deploying it: publishing is a separate decision for G.
- Catalog only: no prices, basket, online orders, weekly boxes or merchandise.

The active code is in [`storefront-mockup/`](storefront-mockup/). The `commerce/` prototype and earlier proposals are historical. Shopify and Clover are possible later integrations, not the current backend.

## Where things live

| Location | Purpose |
| --- | --- |
| This public GitHub repository | Shared source, plans, issues and source history |
| Agent Orange: `/home/user/repos/avocado-shack` | Working checkout and private website service |
| Agent Orange: `/home/user/.local/share/avocado-shack` | Private runtime, community database and archived data; outside Git |
| Mac: `/Users/owner/Documents/ChatGPT/Avo_Shack` | Preserved original project and `handoff-backups/2026-10-20` |
| Dedicated Mac for Hass | User confirms one is available; identity, account and bridge setup remain pending |

Credentials, participant details, message history, original photo archives and private backups stay out of GitHub. Optimized images needed to render the website are already included. This repository is not a complete export of personal chats or external accounts.

The preview remains bound to `127.0.0.1:3101` on Agent Orange. Use the private SSH instructions in [the handoff](HERMES_HANDOFF.txt). Do not enable GitHub Pages or public hosting as part of ordinary development.
