# Esports Business

A Discord bot with branded dashboard and marketplace panels, private support tickets, HTML transcripts, and simple moderation. Python 3.11+ is required.

## Included

- **Watching 1,234 members!** status, refreshed on startup and every minute using Discord's latest approximate total member count (including bots). No extra privileged intent is required.
- Dashboard with Guidelines, Marketplace, Ticket Support, and a **disabled Careers** button.
- Your original banner and footer images on all public panels.
- Marketplace prices from your reference, with a button to open a purchase ticket.
- Exactly three ticket choices: **General Support**, **Ownership Support**, and **Paid Ad/SPGW**.
- Private ticket channels with **Claim** and **Close** buttons and equivalent slash commands.
- One open ticket per member per category, saved across restarts.
- Transcript summary embeds with downloadable HTML-in-ZIP files sent to your transcript channel **before** the ticket is deleted. ZIP downloads prevent Discord from displaying raw HTML source in chat.
- `/warn`, `/warnings`, `/clearwarn`, `/timeout`, `/untimeout`, `/kick`, `/ban`, `/unban`, and `/purge`.

## Your server configuration

| Setting | ID |
| --- | --- |
| Server | `1254579248237379604` |
| Dashboard | `1564325646761467956` |
| Marketplace | `1564325648208629820` |
| Ticket support panel | `1564325660313391316` |
| Transcripts | `1565667801908387853` |
| General Support category | `1565668518480056430` |
| Ownership Support category | `1565668743307067432` |
| Paid Ad/SPGW category | `1565668672192909382` |
| Staff role (General Support and Paid Ad/SPGW) | `1564325589827977330` |
| Ownership Support role | `1569278707833503776` |

These values are already set in `config.json`. IDs are strings to preserve their full precision.

## Start the bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications), select your bot application, and name it **Esports Business**. The code cannot change the application's display name.
2. On **Bot**, reset any token previously pasted into chat. Enable **Message Content Intent**, which allows ticket transcripts to contain message text. The bot does not require the privileged Server Members or Presence intents.
3. Install the application in your server with the `bot` and `applications.commands` scopes. Give it **View Channels**, **Send Messages**, **Read Message History**, **Embed Links**, **Attach Files**, **Manage Channels**, **Manage Roles** (needed to update channel permission overwrites), **Manage Messages**, **Moderate Members**, **Kick Members**, and **Ban Members**. Move its role above members it should moderate and above the configured staff role. Administrator permission is not required.
4. Download or clone this repository and open a terminal in its folder.
5. Install the dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

6. Copy `.env.example` to `.env`. Replace the placeholder with your **new** bot token:

   ```dotenv
   DISCORD_TOKEN=your_new_token_goes_here
   ```

   Keep `.env` private. It is excluded by `.gitignore`. On a host, set `DISCORD_TOKEN` in its private environment/secret settings instead. **Do not put a real token in GitHub, config.json, or bot.py.**

7. Start the bot:

   ```sh
   python bot.py
   ```

8. As a server administrator, run **`/setup`** in Discord. It checks the channels/categories and posts the three panels. Run it again to update existing panels rather than create duplicates. Slash commands register directly in your server during startup.

The bot stays online only while this process is running. This repository contains the code; GitHub does not run it automatically.

## Staff and privacy

General Support and Paid Ad/SPGW use staff role `1564325589827977330`. **Ownership Support uses only role `1569278707833503776` for staff access.** The ticket opener and bot retain access, and Discord administrators always bypass channel restrictions. On startup and `/setup`, existing bot-created ownership tickets in the configured ownership category have their permissions replaced to match this restriction.

Ticket channels explicitly deny `@everyone` access and allow only the opener, the bot, the configured roles, and administrators. Category permissions are not inherited. Staff roles provide ticket access; moderation commands still require the corresponding Discord moderation permissions.

Edit `staff_role_ids` in `config.json` and restart to change ticket staff. Ownership ticket permissions are refreshed automatically; general and paid ticket role changes apply to new channels, so update existing channels manually for those types. An empty staff list means administrators only. Keep the transcript channel restricted to trusted staff; the bot does not modify its existing permissions. Existing transcript posts are unchanged; new closures use the embed format.

## Payments and panel text

The prices from the reference are already in `config.json`. Edit `marketplace_text` or `rules_text` as needed, restart, and run `/setup` again. Your provided artwork is included unchanged, including its original Esports Advertising text.

`paypal_url` is blank because the reference image's recipient was not confirmed. Add your own HTTPS PayPal link to display a payment button, then restart and rerun `/setup`. Without it, customers open a Paid Ad/SPGW ticket to arrange payment with staff. The bot does not process payments, confirm purchases automatically, or schedule advertising pings.

## Commands

| Command | Who can use it | Purpose |
| --- | --- | --- |
| `/help` | Everyone | Commands and support links |
| `/setup` | Administrators | Publish/update panels |
| `/claim` | This ticket type's staff or administrators | Claim the current ticket |
| `/close` | Ticket opener, this ticket's staff, or administrators | Enter a reason, archive, then delete the ticket |
| `/warn member reason` | Manage Messages | Save a warning |
| `/warnings member` | Manage Messages | View the latest 10 warnings and total count |
| `/clearwarn warning_id` | Administrators | Remove one warning |
| `/timeout member minutes reason` | Moderate Members | Timeout for 1 minute–28 days |
| `/untimeout member` | Moderate Members | Remove a timeout |
| `/kick member reason` | Kick Members | Kick a member |
| `/ban member reason` | Ban Members | Ban without deleting message history |
| `/unban user_id` | Ban Members | Unban by numeric ID |
| `/purge amount` | Manage Messages | Delete up to 100 recent, unpinned messages |

Moderation respects both the moderator's and bot's role hierarchy. Purge is disabled in ticket, transcript, and panel channels. Warnings are saved privately; no warning DM is sent automatically.

## Transcripts and persistence

- Tickets close **manually**. There is no automatic 24-hour closure.
- Closing temporarily disables non-administrator sending, exports available history, uploads every part as a ZIP with a summary embed, then deletes the channel. Administrators bypass channel denies; avoid sending while a ticket is closing. Download and extract the ZIP to read the HTML transcript in a browser.
- If export/upload fails, the bot keeps the channel and attempts to restore permissions. If the process crashes mid-close, restarting restores the ticket for a retry. A retry after partial upload may produce duplicate archive parts.
- Transcripts include message text, author IDs, timestamps, current embeds/components, reply references, and attachment links. Deleted messages and previous edit versions cannot be recovered. Attachment links can expire; binary attachments are not downloaded.
- Local transcript backups and SQLite state live in `data/`. Keep that directory private, back it up, and use persistent storage on a host. Do not delete it while the bot is in use.
- Run **one bot process** against this database. Multiple replicas are not supported.
- Persistent buttons survive ordinary restarts because their IDs and handlers remain registered. Keep the same database to retain panel IDs, ticket records, claims, and warnings.

## Checks

```sh
python -m unittest discover -s tests -v
```

The tests run without a token and cover permissions, persistent UI, ticket state, and transcript success/failure. To verify live Discord behaviour, start with a fresh token, run `/setup`, open each ticket type with a normal member account, claim as staff, send a test message, and close. Confirm the HTML arrives in the transcript channel before the ticket disappears. Also test a nonstaff account cannot see another member's ticket.

If login fails, check the new token. If Discord reports privileged intents are disallowed, enable Message Content Intent. If an action is forbidden, check channel/category overwrites and bot role position. If slash commands do not appear, check the bot invitation scopes and startup console.

Built with [discord.py](https://discordpy.readthedocs.io/en/stable/) and its [Components V2 UI](https://discordpy.readthedocs.io/en/stable/interactions/api.html#bot-ui-kit).
