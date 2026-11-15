# Esports Business

A Discord bot with branded dashboard and marketplace panels, private support tickets, HTML transcripts, and simple moderation. Python 3.11+ is required.

## Included

- Automatic welcome panels with your custom emoji, member count, Dashboard link, and 10 randomized greetings without consecutive repeats during a running session.
- New-member role assignment on join and a persistent **Verify** button that removes that role.
- **Watching 1,234 members!** status, refreshed on startup and every minute using Discord's latest approximate total member count (including bots). No extra privileged intent is required.
- Dashboard with Guidelines, Marketplace, Ticket Support, and a **disabled Careers** button.
- Your animated GIF at the top of every panel, with no bottom banners or colored side stripes. The GIF is bundled in `assets/banner.gif` so the bot does not depend on the original Discord download link.
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
| Welcome messages | `1564325669264167059` |
| New-member role (removed by Verify) | `1564362600874254368` |
| General Support category | `1565668518480056430` |
| Ownership Support category | `1565668743307067432` |
| Paid Ad/SPGW category | `1565668672192909382` |
| Staff role (General Support and Paid Ad/SPGW) | `1564325589827977330` |
| Ownership Support role | `1569278707833503776` |

These values are already set in `config.json`. IDs are strings to preserve their full precision.

## Start the bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications), select your bot application, and name it **Esports Business**. The code cannot change the application's display name.
2. On **Bot**, reset any token previously pasted into chat. Enable **Message Content Intent** for ticket transcripts and **Server Members Intent** for automatic welcomes and new-member role assignment. The Presence intent is not required.
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

## Welcome messages

New joins in your server receive a compact panel in channel `1564325669264167059`:

> Welcome @member to **Esports Business**! We hope you enjoy your stay.

The actual server name is used automatically. Each panel starts with `<:icon:1569075326540185700>` and includes a disabled **Members: 251** button showing the total count at join time, plus a **Dashboard** link to `https://discord.com/channels/1254579248237379604/1564325646761467956`. These panels have no banner images or colored side stripe.

The trailing sentence is randomly chosen from 10 messages in `welcome.py`. Consecutive welcomes use different sentences while the process is running. Old welcome messages keep their original member count; only new joins receive a welcome, with no mass greeting on startup.

Enable **Server Members Intent** under **Discord Developer Portal → your application → Bot → Privileged Gateway Intents**, save, then restart the bot. If Discord rejects the new intent, the bot reconnects with welcomes and automatic new-member role assignment disabled so the existing ticket and moderation features can stay online. Enable the intent and restart to turn join features on. Message Content Intent must remain enabled for the existing features.

The bot needs View Channel and Send Messages in the welcome channel, plus Use External Emojis if the custom icon belongs to another server. Administrators can run **`/welcome-preview`** to see a private preview; it does not post to the welcome channel or require someone to leave and rejoin. No `/setup` is needed to activate welcomes after a successful restart with the intent enabled.

## Verification

On each new join, the bot assigns role **`1564362600874254368`** before sending the welcome. **Verify** opens the verification website. Only successful official Discord sign-in removes that role from the authenticated server member. No extra role is added. Existing members are not assigned the role in bulk. Old Verify buttons also redirect and never grant access by themselves.

As an administrator, run **`/verification-setup`** in the verification channel, or choose a destination with **`/verification-setup channel:#your-channel`**. The command posts a panel with your animated banner, a verification description, and the Verify button on the right. Repeating the command updates the saved panel in that channel while its database record remains available. The button stays functional after a restart.

Give the bot **Manage Roles** and put its highest role above role `1564362600874254368`. Enable Server Members Intent for automatic assignment. The new-member role must be able to view the verification channel. Configure that role's channel restrictions in Discord to limit access before verification. Discord sign-in proves account ownership; it is not a CAPTCHA or a real-world identity check.

The website source is in `verification-site/`. Before sign-in works, add this exact redirect in the Discord application's OAuth2 settings:

`https://esports-business-verification.stellarbutterfly2.chatgpt.site/auth/discord/callback`

Configure **DISCORD_CLIENT_SECRET** and **DISCORD_BOT_TOKEN** as private runtime secrets in the website's Sites settings, then redeploy. The client secret must belong to application `1569262699140096170`, and the bot token must be its current token. Never commit credentials. The website displays a setup notice until both values are configured.

Successful role removals are logged as an embed in **`1564364557693091951`**. Give the bot View Channel, Send Messages, and Embed Links there. Already-verified visits do not create duplicate logs. A logging failure is recorded in server logs without undoing verification.

The website uses authorization-code sign-in with PKCE, signed short-lived browser cookies, and the `identify` permission only. It confirms guild membership before changing the one configured role, and revokes the user's access token after the attempt. Passwords and tokens are never requested by the page, saved to the database, or included in verification logs.

## Staff and privacy

General Support and Paid Ad/SPGW use staff role `1564325589827977330`. **Ownership Support uses only role `1569278707833503776` for staff access.** The ticket opener and bot retain access, and Discord administrators always bypass channel restrictions. On startup and `/setup`, existing bot-created ownership tickets in the configured ownership category have their permissions replaced to match this restriction.

Ticket channels explicitly deny `@everyone` access and allow only the opener, the bot, the configured roles, and administrators. Category permissions are not inherited. Staff roles provide ticket access; moderation commands still require the corresponding Discord moderation permissions.

Edit `staff_role_ids` in `config.json` and restart to change ticket staff. Ownership ticket permissions are refreshed automatically; general and paid ticket role changes apply to new channels, so update existing channels manually for those types. An empty staff list means administrators only. Keep the transcript channel restricted to trusted staff; the bot does not modify its existing permissions. Existing transcript posts are unchanged; new closures use the embed format.

## Payments and panel text

The prices from the reference are already in `config.json`. Edit `marketplace_text` or `rules_text` as needed, restart, and run `/setup` again. Your animated GIF is included unchanged. **`branding.json` is the single shared banner setting**: dashboard, marketplace, support, guidelines, verification panel, and website all use its permanent banner URL. The website reads this setting from GitHub on each page request; no expiring Discord attachment URL is used. Change the URL's `v` query when replacing `assets/banner.gif` to refresh caches. No bottom banners are used. Welcomes retain the compact layout without a banner.

On startup the bot refreshes saved verification panels and finds existing public panels in the latest 50 messages of their configured channels, without creating new posts. Run `/setup` or `/verification-setup` for panels older than that or verification panel IDs lost when ephemeral storage resets. Historical ephemeral guideline messages cannot be edited; newly opened guidelines use the current banner.

`paypal_url` is blank because the reference image's recipient was not confirmed. Add your own HTTPS PayPal link to display a payment button, then restart and rerun `/setup`. Without it, customers open a Paid Ad/SPGW ticket to arrange payment with staff. The bot does not process payments, confirm purchases automatically, or schedule advertising pings.

## Commands

| Command | Who can use it | Purpose |
| --- | --- | --- |
| `/help` | Everyone | Commands and support links |
| `/setup` | Administrators | Publish/update panels |
| `/welcome-preview` | Administrators | Preview the randomized welcome panel privately |
| `/verification-setup [channel]` | Administrators | Post/update the Verify panel in the current or selected text channel |
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

If login fails, check the new token. If Discord reports privileged intents are disallowed, enable Message Content Intent and Server Members Intent. If an action is forbidden, check channel/category overwrites and bot role position. If slash commands do not appear, check the bot invitation scopes and startup console.

Built with [discord.py](https://discordpy.readthedocs.io/en/stable/) and its [Components V2 UI](https://discordpy.readthedocs.io/en/stable/interactions/api.html#bot-ui-kit).
