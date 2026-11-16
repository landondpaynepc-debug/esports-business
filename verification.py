"""Discord sign-in verification panel and role checks."""
import discord
from discord import ui

from panels import SafeView


def assignable_role(guild, role_id):
    role = guild.get_role(int(role_id))
    if role is None or role == guild.default_role or role.managed:
        raise ValueError('The configured new-member role is missing or cannot be managed.')
    if guild.me is None or not guild.me.guild_permissions.manage_roles:
        raise ValueError('Give the bot Manage Roles permission before assigning roles.')
    if role >= guild.me.top_role:
        raise ValueError('Move the bot’s role above the new-member role in Server Settings → Roles.')
    return role


def unverified_role(guild, config):
    return assignable_role(guild, config['verification']['role_id'])


class VerifyButton(ui.Button):
    def __init__(self, bot):
        super().__init__(label='Verify', style=discord.ButtonStyle.secondary,
                         custom_id='esports:verify:v1')
        self.bot = bot

    async def callback(self, interaction):
        await self.bot.verify_member(interaction)


def verification_panel(bot, *, legacy=False):
    view = SafeView(timeout=None)
    view.add_item(ui.Container(
        ui.MediaGallery(discord.MediaGalleryItem(bot.config['branding']['banner_url'])),
        ui.TextDisplay(
            '**Verification**\n\n'
            'Welcome to **Esports Business**! Click **Verify** to open our website and sign in with Discord. '
            'After successful sign-in, your new-member role will be removed automatically.'
        ),
        ui.Separator(),
        ui.Section(ui.TextDisplay('Verify using the button here:'), accessory=(VerifyButton(bot) if legacy else
            ui.Button(label='Verify', url=bot.config['branding']['verification_url']))),
    ))
    return view
