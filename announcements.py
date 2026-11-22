"""Administrator announcements built entirely with Discord Components V2."""
import logging
import discord
from discord import app_commands, ui

log = logging.getLogger('esports')
IMAGE_TYPES = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}


def announcement_view(description, *, image_above=None, image_below=None, logo=None):
    children = []
    if image_above:
        children.append(ui.MediaGallery(discord.MediaGalleryItem(image_above, description='Announcement top image')))
    text = ui.TextDisplay(description)
    children.append(ui.Section(text, accessory=ui.Thumbnail(logo, description='Announcement logo')) if logo else text)
    if image_below:
        children.append(ui.MediaGallery(discord.MediaGalleryItem(image_below, description='Announcement bottom image')))
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children))
    return view


async def feedback(interaction, message):
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.TextDisplay(message))
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    await sender(view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def post_announcement(interaction, description, image_above=None, image_below=None, logo=None, channel=None,
                            *, default_banner=None, use_banner=True):
    description = description.strip()
    if not description or len(description) > 4000:
        await feedback(interaction, 'Description is required and must contain 1–4,000 characters.')
        return
    destination = channel or interaction.channel
    if not isinstance(destination, discord.TextChannel) or destination.guild.id != interaction.guild_id:
        await feedback(interaction, 'Choose a text or announcement channel in this server.')
        return
    images = {name: attachment for name, attachment in (
        ('image_above', image_above), ('image_below', image_below), ('logo', logo)) if attachment is not None}
    permissions = destination.permissions_for(interaction.guild.me)
    required = ['view_channel', 'send_messages']
    if images:
        required.append('attach_files')
    if images or (use_banner and default_banner):
        required.append('embed_links')
    if any(not getattr(permissions, permission) for permission in required):
        await feedback(interaction, 'I need View Channel and Send Messages there, plus Attach Files and Embed Links when images are included.')
        return
    size_limit = min(interaction.filesize_limit, interaction.guild.filesize_limit)
    for name, attachment in images.items():
        if attachment.content_type not in IMAGE_TYPES or not attachment.width or not attachment.height:
            await feedback(interaction, f'{name}: upload a PNG, JPG, GIF, or WebP image.')
            return
        if attachment.size > size_limit:
            await feedback(interaction, f'{name} is too large. Choose an image under {size_limit / 1024 / 1024:g} MB.')
            return
    await interaction.response.defer(ephemeral=True, thinking=True)
    files, media = [], {}
    if use_banner and default_banner and image_above is None:
        media['image_above'] = default_banner
    try:
        for name, attachment in images.items():
            filename = f'announcement-{name}{IMAGE_TYPES[attachment.content_type]}'
            file = await attachment.to_file(filename=filename, description=name.replace('_', ' '))
            files.append(file)
            media[name] = f'attachment://{filename}'
        message = await destination.send(view=announcement_view(description, **media), files=files,
                                         allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, OSError):
        log.exception('Could not send announcement in channel %s.', destination.id)
        await feedback(interaction, 'Discord could not complete the announcement. Check the channel before retrying, and verify the images and bot permissions.')
        return
    finally:
        for file in files:
            file.close()
            file.fp.close()
    await feedback(interaction, f'Announcement posted: {message.jump_url}')


def register_announcements(bot):
    @bot.tree.command(name='announce', description='Post a Components V2 announcement with optional images and a logo.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        description='Required announcement text. Supports Discord formatting (up to 4,000 characters).',
        image_above='Optional image uploaded above the description.',
        image_below='Optional image uploaded below the description.',
        logo='Optional small logo displayed beside the description.',
        channel='Optional destination. Defaults to the channel where you run this command.',
        use_banner='Show the Fishy banner when no custom top image is uploaded. Defaults to true.',
    )
    async def announce(interaction: discord.Interaction, description: app_commands.Range[str, 1, 4000],
                       image_above: discord.Attachment | None = None,
                       image_below: discord.Attachment | None = None,
                       logo: discord.Attachment | None = None,
                       channel: discord.TextChannel | None = None,
                       use_banner: bool = True):
        await post_announcement(interaction, description, image_above, image_below, logo, channel,
                                default_banner=bot.config['branding']['announcement_banner_url'], use_banner=use_banner)
