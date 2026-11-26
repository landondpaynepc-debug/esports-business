# Royal Services verification

Official Discord OAuth sign-in, hosted as a Sites server application. Website: https://esports-business-verification.stellarbutterfly2.chatgpt.site

## Activate

1. In Discord Developer Portal, application `1569262699140096170` → OAuth2 → Redirects, add exactly `https://esports-business-verification.stellarbutterfly2.chatgpt.site/auth/discord/callback`.
2. In this website's private runtime settings, set `DISCORD_CLIENT_SECRET` and `DISCORD_BOT_TOKEN` for that application. Redeploy to apply them. Do not put these values in GitHub, frontend code, or the hosting manifest.
3. Put the bot role above unverified role `1564362600874254368`, with Manage Roles. Give it access to verification log channel `1564364557693091951` with Send Messages and Embed Links.
4. In Discord run `/verification-setup` in the desired verification channel. Enable Server Members Intent for new-member role assignment.

The landing page shows an unavailable notice until both secrets exist. Check the actual OAuth flow with a normal server member after setup; local tests use mocked Discord responses and never change live members.

Only the `identify` scope is requested. Signed 10-minute browser state, PKCE, issuer checking, server-side token exchange, and fresh guild membership checks protect role changes. The authenticated Discord ID determines the member; incoming user/role/guild IDs are never trusted. Access tokens are kept only in request memory and revoked afterwards. Signed result cookies expire after 5 minutes and cannot authorize any role change. This is account sign-in, not a CAPTCHA. Successful removals post a log embed; already-verified visits do not spam logs.

All banners use the main repository's `branding.json` and `assets/banner.jpg`. There are no copied banner files or bottom banners. Update the banner URL version in that file when changing the banner. Bot panels update on startup where their messages can be found; the site reads shared branding on each page load.

## Development

Use Node 22.13+ (Node 24 recommended), `npm ci`, `npm run dev`, and `npm run build`. Preserve the supplied Sites build integration. Production output is a Worker in `dist/server/index.js`; no static hosting mode is configured. OAuth requires the registered public HTTPS origin and is intentionally not redirected to an unregistered localhost origin. `node --test tests/verification.test.mjs` checks the OAuth flow without real credentials.

The root bot repository contains this complete site source for review and backup. Sites publication uses its own linked source repository and the project ID in `.openai/hosting.json`; use the Sites workflow to deploy website source changes. Updating `branding.json` in the bot repository does not require a website rebuild.
