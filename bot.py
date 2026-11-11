"""Esports Business. Run one instance with `python bot.py`."""
import asyncio
import copy
import json
import logging
import os
import re
import zipfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from panels import CloseForm, TicketControls, panel, respond, RED
from storage import Store
from transcripts import export_transcript

BASE = Path(__file__).resolve().parent
log = logging.getLogger('esports')


def load_config():
    cfg = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))
    int(cfg['guild_id'])
    for value in cfg['channels'].values():
        int(value)
    for kind in ('general', 'ownership', 'paid'):
        int(cfg['tickets'][kind]['category_id'])
        for role in cfg['tickets'][kind]['staff_role_ids']:
            int(role)
    url = cfg.get('paypal_url', '')
    if url:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('paypal.me', 'www.paypal.me', 'paypal.com', 'www.paypal.com'):
            raise ValueError('paypal_url must be a genuine HTTPS PayPal URL, or left empty.')
    return cfg


def is_staff(member, kind, config):
    if member.guild_permissions.administrator:
        return True
    roles = {int(value) for value in config['tickets'][kind]['staff_role_ids']}
    return any(role.id in roles for role in member.roles)


def ticket_overwrites(guild, owner, staff_roles):
    """Explicit overwrites: do not inherit a publicly visible category's access."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True, embed_links=True,
            manage_channels=True, manage_roles=True),
    }
    if owner is not None:
        overwrites[owner] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True, embed_links=True,
            create_public_threads=False, create_private_threads=False)
    for role in staff_roles:
        if role == guild.default_role:
            raise ValueError('The @everyone role cannot be a ticket staff role.')
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True, embed_links=True,
            create_public_threads=False, create_private_threads=False)
    return overwrites


def serialize_overwrites(overwrites):
    return json.dumps([
        {'id': target.id, 'type': 'role' if isinstance(target, discord.Role) else 'member',
         'allow': value.pair()[0].value, 'deny': value.pair()[1].value}
        for target, value in overwrites.items()
    ])


async def restore_overwrites(channel, serialized):
    overwrites = {}
    for item in json.loads(serialized):
        target = channel.guild.get_role(item['id']) if item['type'] == 'role' else channel.guild.get_member(item['id'])
        if target is None and item['type'] == 'member':
            try:
                target = await channel.guild.fetch_member(item['id'])
            except discord.NotFound:
                continue
        if target is not None:
            overwrites[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(item['allow']), discord.Permissions(item['deny']))
    await channel.edit(overwrites=overwrites, reason='Restore ticket after interrupted closure')


class GuildTree(app_commands.CommandTree):
    async def interaction_check(self, interaction):
        return await self.client.valid_interaction(interaction)

    async def on_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await respond(interaction, 'You or the bot do not have the permissions needed for this command.')
            return
        if isinstance(error, app_commands.CommandOnCooldown):
            await respond(interaction, f'Please try again in {error.retry_after:.0f} seconds.')
            return
        original = getattr(error, 'original', error)
        if isinstance(original, discord.Forbidden):
            await respond(interaction, 'Discord denied this action. Check the bot permissions and role position.')
        else:
            log.error('Command failed', exc_info=(type(original), original, original.__traceback__))
            await respond(interaction, 'The command failed. Check the bot console for details, then try again.')


class EsportsBot(discord.Client):
    def __init__(self, config, database=None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.config = config
        self.store = Store(database or BASE / 'data' / 'bot.sqlite3')
        self.tree = GuildTree(self)
        self.locks = {}
        self.setup_lock = asyncio.Lock()
        self.started = False
        self.ready_for_tickets = False
        from moderation import register_moderation
        register_moderation(self)
        self.register_commands()

    def lock(self, key):
        return self.locks.setdefault(key, asyncio.Lock())

    def assets(self):
        return [discord.File(BASE / 'assets' / name, filename=name) for name in ('banner.png', 'footer.png')]

    async def setup_hook(self):
        for kind in ('dashboard', 'marketplace', 'support'):
            self.add_view(panel(self, kind))
        self.add_view(TicketControls(self))
        guild = discord.Object(id=int(self.config['guild_id']))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.member_count_status.start()

    @tasks.loop(minutes=1)
    async def member_count_status(self):
        if not self.is_ready():
            return
        try:
            # Fetch fresh counts without requiring the privileged Members intent.
            guild = await self.fetch_guild(int(self.config['guild_id']), with_counts=True)
            count = guild.approximate_member_count
            if count is not None:
                await self.change_presence(activity=discord.Activity(
                    type=discord.ActivityType.watching, name=f'{count:,} members!',
                ))
        except (discord.HTTPException, discord.ConnectionClosed, OSError):
            log.warning('Could not refresh the member-count status; retrying next minute.', exc_info=True)

    @member_count_status.before_loop
    async def before_member_count_status(self):
        await self.wait_until_ready()

    async def on_ready(self):
        if self.started:
            return
        self.started = True
        log.info('Connected as %s. Recovering any interrupted ticket closures.', self.user)
        try:
            await self.recover_closures()
            await self.sync_ownership_permissions()
            self.ready_for_tickets = True
            log.info('Ready. Run /setup in server %s to publish the panels.', self.config['guild_id'])
        except Exception:
            self.started = False
            log.exception('Startup initialization failed. Check the exception below and restart after fixing it.')

    async def close(self):
        task = self.member_count_status.get_task()
        self.member_count_status.cancel()
        if task is not None:
            with suppress(asyncio.CancelledError):
                await task
        await super().close()
        self.store.close()

    async def valid_interaction(self, interaction):
        if interaction.guild_id != int(self.config['guild_id']) or not isinstance(interaction.user, discord.Member):
            await respond(interaction, 'This bot is configured for the Esports Business server only.')
            return False
        if not self.ready_for_tickets:
            await respond(interaction, 'The bot is starting or needs an administrator to check its console. Please try again shortly.')
            return False
        return True

    async def channel(self, channel_id, expected=discord.TextChannel):
        channel = await self.fetch_channel(int(channel_id))
        if not isinstance(channel, expected) or channel.guild.id != int(self.config['guild_id']):
            raise ValueError(f'{channel_id} must be a {expected.__name__} in the configured server.')
        return channel

    async def preflight(self):
        found = {}
        for name, channel_id in self.config['channels'].items():
            channel = await self.channel(channel_id)
            perms = channel.permissions_for(channel.guild.me)
            required = ('view_channel', 'send_messages', 'read_message_history', 'attach_files', 'embed_links')
            missing = [p for p in required if not getattr(perms, p)]
            if missing:
                raise ValueError(f'#{channel.name}: bot is missing {", ".join(missing)}.')
            found[name] = channel
        for kind, settings in self.config['tickets'].items():
            category = await self.channel(settings['category_id'], discord.CategoryChannel)
            perms = category.permissions_for(category.guild.me)
            missing = [p for p in ('view_channel', 'manage_channels', 'manage_roles') if not getattr(perms, p)]
            if missing:
                raise ValueError(f'{settings["label"]} category: bot needs {", ".join(missing)}.')
            self.staff_roles(category.guild, kind)
        return found

    def staff_roles(self, guild, kind):
        roles = []
        for role_id in self.config['tickets'][kind]['staff_role_ids']:
            role = guild.get_role(int(role_id))
            if role is None or role == guild.default_role or role.managed:
                raise ValueError(f'Invalid staff role {role_id} for {kind}. Use an ordinary staff role.')
            roles.append(role)
        return roles

    async def sync_ownership_permissions(self):
        """Restrict existing bot-created ownership tickets, even if local state was lost."""
        category = await self.channel(self.config['tickets']['ownership']['category_id'], discord.CategoryChannel)
        guild = category.guild
        roles = self.staff_roles(guild, 'ownership')
        # The gateway has already populated known text channels before on_ready.
        # Fetching ALL channels fails if Discord returns any newer, unsupported type.
        for channel in list(guild.text_channels):
            if not isinstance(channel, discord.TextChannel) or channel.category_id != category.id:
                continue
            ticket = self.store.ticket(channel.id)
            match = re.fullmatch(r'Esports Business \| Ownership Support \| Owner: (\d+)', channel.topic or '')
            if ticket and ticket['kind'] == 'ownership' and ticket['status'] != 'closed':
                owner_id = ticket['owner_id']
            elif match:
                owner_id = int(match.group(1))
            else:
                continue
            try:
                owner = guild.get_member(owner_id) or await guild.fetch_member(owner_id)
            except discord.NotFound:
                owner = None
            async with self.lock(('ticket', channel.id)):
                current = self.store.ticket(channel.id)
                if current and current['status'] != 'open':
                    continue
                try:
                    await channel.edit(overwrites=ticket_overwrites(guild, owner, roles),
                                       reason='Restrict ownership tickets to the configured ownership team')
                except discord.NotFound:
                    continue  # It was closed while the channel list was being fetched.

    def register_commands(self):
        @self.tree.command(name='setup', description='Publish or update the dashboard, marketplace and ticket panels.')
        @app_commands.default_permissions(administrator=True)
        @app_commands.checks.has_permissions(administrator=True)
        async def setup(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async with self.setup_lock:
                try:
                    channels = await self.preflight()
                    await self.sync_ownership_permissions()
                except (ValueError, discord.HTTPException) as error:
                    await respond(interaction, f'Setup could not finish: {error}')
                    return
                for name in ('dashboard', 'marketplace', 'support'):
                    channel = channels[name]
                    row = self.store.db.execute('SELECT message_id FROM panels WHERE name=?', (name,)).fetchone()
                    message = None
                    if row:
                        try:
                            message = await channel.fetch_message(row['message_id'])
                        except discord.NotFound:
                            pass
                    files = self.assets()
                    try:
                        if message:
                            await message.edit(view=panel(self, name), attachments=files)
                        else:
                            message = await channel.send(view=panel(self, name), files=files)
                            self.store.execute('INSERT OR REPLACE INTO panels VALUES(?,?)', (name, message.id))
                    finally:
                        for file in files:
                            file.close()
                await respond(interaction, 'Dashboard, marketplace and support panels are ready. Careers is disabled. '
                              'Staff access is controlled by staff_role_ids in config.json; empty lists mean administrators only.')

        @self.tree.command(name='help', description='View Esports Business commands and support links.')
        async def help_command(interaction: discord.Interaction):
            await respond(interaction,
                f'**Esports Business**\nDashboard: <#{self.config["channels"]["dashboard"]}>\n'
                f'Support: <#{self.config["channels"]["support"]}>\n\n'
                '**Moderation:** /warn, /warnings, /clearwarn, /timeout, /untimeout, /kick, /ban, /unban, /purge\n'
                '**Tickets:** /claim, /close (also available as buttons)\n'
                '**Administrators:** /setup\nCareers is coming soon.')

        @self.tree.command(name='claim', description='Claim the current support ticket (ticket staff only).')
        async def claim(interaction: discord.Interaction):
            await self.claim_ticket(interaction)

        @self.tree.command(name='close', description='Close this ticket after saving a transcript.')
        async def close_ticket(interaction: discord.Interaction):
            if await self.ticket_access(interaction, allow_owner=True):
                await interaction.response.send_modal(CloseForm(self))

    async def ticket_access(self, interaction, allow_owner=False):
        if not await self.valid_interaction(interaction):
            return None
        ticket = self.store.ticket(interaction.channel_id)
        if ticket is None or ticket['status'] == 'closed':
            await respond(interaction, 'This channel is not an active ticket.')
            return None
        if not (is_staff(interaction.user, ticket['kind'], self.config)
                or (allow_owner and ticket['owner_id'] == interaction.user.id)):
            await respond(interaction, 'Only this ticket’s assigned support roles or server administrators can do that.'
                          if not allow_owner else 'Only the ticket opener or this ticket’s support staff can close it.')
            return None
        return ticket

    async def open_ticket(self, interaction, kind, subject, details):
        if not await self.valid_interaction(interaction) or kind not in self.config['tickets']:
            return
        await interaction.response.defer(ephemeral=True)
        async with self.lock(('open', interaction.user.id, kind)):
            existing = self.store.active(interaction.user.id, kind)
            if existing:
                try:
                    await self.channel(existing['channel_id'])
                except discord.NotFound:
                    self.store.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (existing['channel_id'],))
                else:
                    await respond(interaction, f'You already have a ticket in this category: <#{existing["channel_id"]}>.')
                    return
            settings = self.config['tickets'][kind]
            category = await self.channel(settings['category_id'], discord.CategoryChannel)
            # A failed transcript-channel check prevents users opening tickets we cannot archive.
            archive = await self.channel(self.config['channels']['transcripts'])
            archive_perms = archive.permissions_for(interaction.guild.me)
            if not all(getattr(archive_perms, p) for p in ('view_channel', 'send_messages', 'attach_files')):
                await respond(interaction, 'The transcript channel needs permission fixes before new tickets can be opened.')
                return
            roles = self.staff_roles(interaction.guild, kind)
            overwrites = ticket_overwrites(interaction.guild, interaction.user, roles)
            channel = await interaction.guild.create_text_channel(
                name=f'{kind}-{interaction.user.id}', category=category,
                topic=f'Esports Business | {settings["label"]} | Owner: {interaction.user.id}',
                overwrites=overwrites, reason=f'Ticket opened by {interaction.user.id}',
            )
            # Persist immediately after channel creation, before sending messages.
            self.store.add_ticket(channel.id, interaction.user.id, kind)
            embed = discord.Embed(title=f'{settings["label"]} • {subject}', description=details, colour=RED,
                                  timestamp=datetime.now(timezone.utc))
            embed.add_field(name='Opened by', value=f'<@{interaction.user.id}>', inline=True)
            embed.add_field(name='Claimed by', value='Unclaimed', inline=True)
            embed.set_footer(text='Staff: Claim to take responsibility. Close saves a transcript before deleting this channel.')
            try:
                await channel.send(content=f'<@{interaction.user.id}> — your ticket is open.', embed=embed,
                                   view=TicketControls(self))
            except discord.HTTPException:
                log.exception('Ticket created but welcome message failed: %s', channel.id)
                await respond(interaction, f'Your ticket is <#{channel.id}>. The welcome message failed; staff can use /claim and /close.')
                return
            await respond(interaction, f'Your **{settings["label"]}** ticket is ready: {channel.mention}')

    async def claim_ticket(self, interaction):
        ticket = await self.ticket_access(interaction)
        if ticket is None:
            return
        await interaction.response.defer(ephemeral=True)
        async with self.lock(('ticket', interaction.channel_id)):
            ticket = self.store.ticket(interaction.channel_id)
            if ticket['status'] != 'open':
                await respond(interaction, 'This ticket is closing or already closed.')
                return
            if ticket['claimed_by']:
                await respond(interaction, f'This ticket is already claimed by <@{ticket["claimed_by"]}>.')
                return
            self.store.execute('UPDATE tickets SET claimed_by=? WHERE channel_id=? AND claimed_by IS NULL',
                               (interaction.user.id, interaction.channel_id))
            await interaction.channel.send(f'🙋 Ticket claimed by <@{interaction.user.id}>.')
            # Update the clicked welcome message when possible; database is authoritative.
            message = getattr(interaction, 'message', None)
            if message and message.embeds:
                try:
                    embed = message.embeds[0].copy()
                    embed.set_field_at(1, name='Claimed by', value=f'<@{interaction.user.id}>', inline=True)
                    await message.edit(embed=embed)
                except discord.HTTPException:
                    log.warning('Could not update claim display in %s', interaction.channel_id)
            await respond(interaction, 'You claimed this ticket.')

    async def close_ticket(self, interaction, reason):
        if await self.ticket_access(interaction, allow_owner=True) is None:
            return
        await interaction.response.defer(ephemeral=True)
        async with self.lock(('ticket', interaction.channel_id)):
            ticket = self.store.ticket(interaction.channel_id)
            if ticket['status'] != 'open':
                await respond(interaction, 'This ticket is already closing or closed. If it is stuck, restart the bot to recover it.')
                return
            channel = await self.channel(interaction.channel_id)
            original = serialize_overwrites(channel.overwrites)
            self.store.execute("UPDATE tickets SET status='closing', original_overwrites=? WHERE channel_id=?",
                               (original, channel.id))
            try:
                locked = {target: copy.copy(value) for target, value in channel.overwrites.items()}
                for target, permissions in locked.items():
                    if target.id != self.user.id:
                        permissions.send_messages = False
                        permissions.send_messages_in_threads = False
                        permissions.add_reactions = False
                await channel.edit(overwrites=locked, reason='Freeze ticket while exporting transcript')
                cutoff = discord.Object(id=discord.utils.time_snowflake(datetime.now(timezone.utc), high=True))
                paths, count = await export_transcript(
                    channel, ticket, interaction.user, reason,
                    BASE / 'data' / 'transcripts' / str(channel.id) / str(interaction.id), cutoff,
                )
                archive = await self.channel(self.config['channels']['transcripts'])
                for number, path in enumerate(paths, 1):
                    # Discord previews HTML as raw source. A ZIP keeps the full transcript
                    # downloadable while the embed provides a readable archive summary.
                    download = path.with_suffix('.zip')
                    with zipfile.ZipFile(download, 'w', zipfile.ZIP_DEFLATED) as zipped:
                        zipped.write(path, arcname=path.name)
                    if download.stat().st_size > channel.guild.filesize_limit:
                        raise ValueError('A transcript part exceeds the server upload limit.')
                    embed = discord.Embed(title='Ticket Transcript',
                        description=f'**{discord.utils.escape_markdown(channel.name)}**\nDownload the ZIP below and open the HTML transcript inside.',
                        timestamp=datetime.now(timezone.utc))
                    embed.add_field(name='Ticket Owner', value=f'<@{ticket["owner_id"]}>', inline=True)
                    embed.add_field(name='Category', value=self.config['tickets'][ticket['kind']]['label'], inline=True)
                    embed.add_field(name='Closed By', value=f'<@{interaction.user.id}>', inline=True)
                    embed.add_field(name='Claimed By', value=f'<@{ticket["claimed_by"]}>' if ticket['claimed_by'] else 'Unclaimed', inline=True)
                    embed.add_field(name='Messages', value=str(count), inline=True)
                    embed.add_field(name='Close Reason', value=discord.utils.escape_markdown(reason)[:1024], inline=False)
                    embed.set_footer(text=f'Ticket ID: {channel.id} • Part {number}/{len(paths)}')
                    file = discord.File(download)
                    try:
                        await archive.send(
                            embed=embed,
                            file=file,
                        )
                    finally:
                        file.close()
                # Deletion is the last external operation, after EVERY transcript part uploads.
                await channel.delete(reason=f'Ticket closed by {interaction.user.id}; transcript delivered')
            except Exception:
                log.exception('Ticket closure failed: %s; preserving the channel', channel.id)
                try:
                    await restore_overwrites(channel, original)
                    self.store.execute("UPDATE tickets SET status='open', original_overwrites=NULL WHERE channel_id=?", (channel.id,))
                except discord.NotFound:
                    self.store.execute("UPDATE tickets SET status='closed', original_overwrites=NULL WHERE channel_id=?", (channel.id,))
                except Exception:
                    log.exception('Could not restore ticket permissions. Restart after fixing permissions.')
                await respond(interaction, 'Closure failed. The bot will not delete a ticket before its transcript is delivered. '
                              'Ask an administrator to check permissions and the console. If locked, restart the bot after fixing permissions.')
                return
            self.store.execute("UPDATE tickets SET status='closed', original_overwrites=NULL WHERE channel_id=?", (channel.id,))
            await respond(interaction, f'Ticket closed. Transcript sent to <#{self.config["channels"]["transcripts"]}>.')

    async def recover_closures(self):
        rows = self.store.db.execute("SELECT * FROM tickets WHERE status='closing'").fetchall()
        for ticket in rows:
            try:
                channel = await self.channel(ticket['channel_id'])
                if ticket['original_overwrites']:
                    await restore_overwrites(channel, ticket['original_overwrites'])
            except discord.NotFound:
                self.store.execute("UPDATE tickets SET status='closed', original_overwrites=NULL WHERE channel_id=?", (ticket['channel_id'],))
            else:
                self.store.execute("UPDATE tickets SET status='open', original_overwrites=NULL WHERE channel_id=?", (ticket['channel_id'],))


def main():
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
    log.addHandler(handler)
    load_dotenv(BASE / '.env')
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token or token == 'replace_with_your_new_bot_token':
        raise SystemExit('Add your NEW bot token to a private .env file. See README.md. Never commit a real token.')
    bot = EsportsBot(load_config())
    bot.run(token, log_level=logging.INFO)


if __name__ == '__main__':
    main()
