"""Discord Components V2 panels using the supplied banner and footer."""
import logging
import discord
from discord import ui

log = logging.getLogger(__name__)
RED = 0xED3326


async def respond(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


class SafeView(ui.LayoutView):
    async def on_error(self, interaction, error, item):
        log.error('Panel interaction failed', exc_info=(type(error), error, error.__traceback__))
        await respond(interaction, 'That action failed. Please try again or contact an administrator.')


class SafeButtons(ui.View):
    async def on_error(self, interaction, error, item):
        log.error('Ticket interaction failed', exc_info=(type(error), error, error.__traceback__))
        await respond(interaction, 'That action failed. Please try again or contact an administrator.')


class SafeModal(ui.Modal):
    async def on_error(self, interaction, error):
        log.error('Form submission failed', exc_info=(type(error), error, error.__traceback__))
        await respond(interaction, 'That action failed. Your ticket has not been intentionally deleted. Contact an administrator.')


class TicketForm(SafeModal, title='Esports Business • Open a ticket'):
    subject = ui.TextInput(label='Subject', placeholder='What can we help you with?', max_length=100)
    details = ui.TextInput(label='Details', style=discord.TextStyle.paragraph,
                           placeholder='Describe your request. Do not include passwords or payment card details.',
                           min_length=10, max_length=1500)

    def __init__(self, bot, kind):
        super().__init__(timeout=300)
        self.bot, self.kind = bot, kind

    async def on_submit(self, interaction):
        await self.bot.open_ticket(interaction, self.kind, str(self.subject), str(self.details))


class CloseForm(SafeModal, title='Close this ticket'):
    reason = ui.TextInput(label='Reason for closing', style=discord.TextStyle.paragraph,
                          placeholder='Explain why this ticket is being closed.', max_length=500)

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction):
        await self.bot.close_ticket(interaction, str(self.reason))


class TicketSelect(ui.Select):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(custom_id='esports:ticket:select:v1', placeholder='Choose a support category…', options=[
            discord.SelectOption(label='General Support', value='general', emoji='🌐',
                                 description='Questions, reports, or moderation appeals'),
            discord.SelectOption(label='Ownership Support', value='ownership', emoji='🔑',
                                 description='Private concerns for server leadership'),
            discord.SelectOption(label='Paid Ad/SPGW', value='paid', emoji='💰',
                                 description='Purchase an advertisement or sponsored giveaway'),
        ])

    async def callback(self, interaction):
        if not await self.bot.valid_interaction(interaction):
            return
        await interaction.response.send_modal(TicketForm(self.bot, self.values[0]))


class PurchaseButton(ui.Button):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(label='Open Paid Ad/SPGW Ticket', style=discord.ButtonStyle.primary,
                         custom_id='esports:purchase:v1', emoji='🎟️')

    async def callback(self, interaction):
        if await self.bot.valid_interaction(interaction):
            await interaction.response.send_modal(TicketForm(self.bot, 'paid'))


class RulesButton(ui.Button):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(label='Guidelines', style=discord.ButtonStyle.secondary,
                         custom_id='esports:rules:v1', emoji='📋')

    async def callback(self, interaction):
        if await self.bot.valid_interaction(interaction):
            await interaction.response.send_message(
                view=panel(self.bot, 'rules'), files=self.bot.assets(), ephemeral=True,
            )


def panel(bot, kind):
    cfg = bot.config
    view = SafeView(timeout=None)
    children = [ui.MediaGallery(discord.MediaGalleryItem('attachment://banner.png')), ui.Separator()]
    if kind == 'dashboard':
        children.append(ui.TextDisplay(
            '# Esports Business\nWelcome to the community dashboard.\n\n'
            '**Guidelines** — read our community rules.\n'
            '**Marketplace** — explore advertisement packages.\n'
            '**Ticket Support** — get help from our team.\n'
            '**Careers** — coming soon.'
        ))
        children.append(ui.ActionRow(
            RulesButton(bot),
            ui.Button(label='Marketplace', url=f'https://discord.com/channels/{cfg["guild_id"]}/{cfg["channels"]["marketplace"]}', emoji='🛒'),
            ui.Button(label='Ticket Support', url=f'https://discord.com/channels/{cfg["guild_id"]}/{cfg["channels"]["support"]}', emoji='🎟️'),
            ui.Button(label='Careers', custom_id='esports:careers:v1', disabled=True,
                      style=discord.ButtonStyle.secondary, emoji='💼'),
        ))
    elif kind == 'marketplace':
        children.extend([ui.TextDisplay(cfg['marketplace_text']), ui.Separator(), ui.TextDisplay(
            '## How do I pay?\nWe use **PayPal** for payments. '
            'Open a **Paid Ad/SPGW ticket** to confirm your package and payment details with staff.\n'
            'For purchases requiring leadership review, use **Ownership Support**.'
        )])
        row = ui.ActionRow(PurchaseButton(bot))
        if cfg.get('paypal_url'):
            row.add_item(ui.Button(label='Pay with PayPal', url=cfg['paypal_url']))
        children.append(row)
    elif kind == 'support':
        children.append(ui.TextDisplay(
            '# 🎟️ | Tickets\nNeed help? Choose the category that matches your request.\n\n'
            '### Information\n'
            '- Explain your issue clearly and include evidence for reports or appeals.\n'
            '- Choose the correct category and keep private information out of public channels.\n\n'
            '### Ticket Guidelines\n'
            '- Be patient and do not ping staff repeatedly.\n'
            '- Share clips as MP4 files, unlisted YouTube links, or other trusted links.\n'
            '- Do not abuse the ticket system.\n'
            '- You may have one open ticket per category.\n'
            '- Tickets are closed manually; staff retain a transcript when a ticket is closed.\n\n'
            '### 🌐 | General Support\nQuestions about the server, member reports, or moderation appeals.\n\n'
            '### 🔑 | Ownership Support\nPrivate concerns for leadership, urgent server issues, or purchase reviews.\n\n'
            '### 💰 | Paid Ad/SPGW\nPurchase an advertisement or sponsored giveaway. '
            f'View packages in <#{cfg["channels"]["marketplace"]}>. Payments are handled by staff through PayPal.'
        ))
        children.append(ui.ActionRow(TicketSelect(bot)))
    elif kind == 'rules':
        children.append(ui.TextDisplay(cfg['rules_text']))
    else:
        raise ValueError(f'Unknown panel: {kind}')
    children.extend([ui.Separator(), ui.MediaGallery(discord.MediaGalleryItem('attachment://footer.png'))])
    view.add_item(ui.Container(*children, accent_colour=RED))
    return view


class TicketControls(SafeButtons):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label='Claim', style=discord.ButtonStyle.success, emoji='🙋', custom_id='esports:ticket:claim:v1')
    async def claim(self, interaction, button):
        await self.bot.claim_ticket(interaction)

    @ui.button(label='Close', style=discord.ButtonStyle.danger, emoji='🔒', custom_id='esports:ticket:close:v1')
    async def close(self, interaction, button):
        ticket = await self.bot.ticket_access(interaction, allow_owner=True)
        if ticket:
            await interaction.response.send_modal(CloseForm(self.bot))
