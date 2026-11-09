"""Simple slash-command moderation with runtime permission and hierarchy checks."""
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from panels import respond


def target_error(guild, actor, target):
    if target.id in (actor.id, guild.me.id, guild.owner_id):
        return 'You cannot target yourself, this bot, or the server owner.'
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return 'You cannot moderate someone with an equal or higher role than yours.'
    if target.top_role >= guild.me.top_role:
        return 'Move the bot role above that member’s highest role first.'
    return None


def audit_reason(interaction, reason):
    return f'{interaction.user} ({interaction.user.id}): {reason}'[:512]


async def can_target(interaction, member):
    error = target_error(interaction.guild, interaction.user, member)
    if error:
        await respond(interaction, error)
        return False
    return True


def register_moderation(bot):
    tree = bot.tree

    @tree.command(name='warn', description='Record a warning for a member.')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(interaction: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await can_target(interaction, member):
            return
        now = datetime.now(timezone.utc).isoformat()
        cursor = bot.store.execute('INSERT INTO warnings(user_id,moderator_id,reason,created_at) VALUES(?,?,?,?)',
                                   (member.id, interaction.user.id, reason, now))
        await respond(interaction, f'Warning **#{cursor.lastrowid}** recorded for {member.mention}: {discord.utils.escape_markdown(reason)}')

    @tree.command(name='warnings', description='View a member’s last 10 warnings.')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warnings(interaction: discord.Interaction, member: discord.Member):
        rows = bot.store.db.execute('SELECT * FROM warnings WHERE user_id=? ORDER BY id DESC LIMIT 10', (member.id,)).fetchall()
        count = bot.store.db.execute('SELECT COUNT(*) FROM warnings WHERE user_id=?', (member.id,)).fetchone()[0]
        embed = discord.Embed(title=f'Warnings for {member}', description=f'{count} total • showing up to 10', colour=0xED3326)
        for row in rows:
            embed.add_field(name=f'#{row["id"]} • {row["created_at"][:10]}',
                            value=f'{discord.utils.escape_markdown(row["reason"])}\nModerator: <@{row["moderator_id"]}>', inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name='clearwarn', description='Delete one warning by its ID (administrators only).')
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarn(interaction: discord.Interaction, warning_id: app_commands.Range[int, 1]):
        result = bot.store.execute('DELETE FROM warnings WHERE id=?', (warning_id,))
        await respond(interaction, 'Warning removed.' if result.rowcount else 'No warning has that ID.')

    @tree.command(name='timeout', description='Time out a member for 1 minute to 28 days.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(interaction: discord.Interaction, member: discord.Member,
                      minutes: app_commands.Range[int, 1, 40320], reason: app_commands.Range[str, 1, 500]):
        if not await can_target(interaction, member):
            return
        if member.guild_permissions.administrator or member.bot:
            await respond(interaction, 'Discord does not allow timeouts for administrators or bots.')
            return
        await interaction.response.defer(ephemeral=True)
        await member.timeout(timedelta(minutes=minutes), reason=audit_reason(interaction, reason))
        await respond(interaction, f'{member.mention} timed out for {minutes} minute(s).')

    @tree.command(name='untimeout', description='Remove a member’s timeout.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(interaction: discord.Interaction, member: discord.Member,
                        reason: app_commands.Range[str, 1, 500] = 'Timeout removed'):
        if not await can_target(interaction, member):
            return
        await interaction.response.defer(ephemeral=True)
        await member.timeout(None, reason=audit_reason(interaction, reason))
        await respond(interaction, f'Timeout removed for {member.mention}.')

    @tree.command(name='kick', description='Remove a member from the server.')
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(interaction: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await can_target(interaction, member):
            return
        await interaction.response.defer(ephemeral=True)
        await member.kick(reason=audit_reason(interaction, reason))
        await respond(interaction, f'Kicked {member.mention}.')

    @tree.command(name='ban', description='Ban a member without deleting their message history.')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(interaction: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await can_target(interaction, member):
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.guild.ban(member, reason=audit_reason(interaction, reason), delete_message_seconds=0)
        await respond(interaction, f'Banned {member.mention}.')

    @tree.command(name='unban', description='Unban a user by their Discord user ID.')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(interaction: discord.Interaction, user_id: str, reason: app_commands.Range[str, 1, 500] = 'Ban removed'):
        if not user_id.isascii() or not user_id.isdecimal() or not 15 <= len(user_id) <= 22:
            await respond(interaction, 'Enter a valid numeric Discord user ID.')
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.guild.unban(discord.Object(id=int(user_id)), reason=audit_reason(interaction, reason))
        except discord.NotFound:
            await respond(interaction, 'That user is not banned.')
            return
        await respond(interaction, f'Unbanned user `{user_id}`.')

    @tree.command(name='purge', description='Delete up to 100 recent messages in this channel.')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        if not isinstance(interaction.channel, discord.TextChannel):
            await respond(interaction, 'Use this command in a server text channel.')
            return
        protected = {int(value) for value in bot.config['channels'].values()}
        if interaction.channel_id in protected or bot.store.ticket(interaction.channel_id):
            await respond(interaction, 'Purge is disabled in panel channels, the transcript channel, and tickets.')
            return
        await interaction.response.defer(ephemeral=True)
        cutoff = datetime.now(timezone.utc) - timedelta(days=14) + timedelta(minutes=5)
        deleted = await interaction.channel.purge(limit=amount, check=lambda message: message.created_at > cutoff and not message.pinned,
                                                  reason=audit_reason(interaction, 'Purge recent messages'))
        await respond(interaction, f'Deleted {len(deleted)} messages. Pinned messages and messages near or over 14 days old were skipped.')
