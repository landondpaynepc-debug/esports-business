"""Compact welcome panels with ten rotating greetings."""
import random

import discord
from discord import ui


WELCOME_MESSAGES = (
    'We hope you enjoy your stay.',
    'Glad you’re here—make yourself at home!',
    'Your next connection starts here. Say hello!',
    'Welcome aboard! We’re excited to have you with us.',
    'Jump in, meet the community, and enjoy your time here!',
    'A new member, a new opportunity—let’s grow together!',
    'Check out the dashboard and see what’s happening!',
    'The community just got better with you here!',
    'Dive in and get ready to connect with the community!',
    'Thanks for joining us. We can’t wait to see what you bring!',
)


def choose_greeting(previous=None):
    return random.choice([message for message in WELCOME_MESSAGES if message != previous])


def welcome_panel(member, config, greeting, member_count):
    server_name = discord.utils.escape_markdown(discord.utils.escape_mentions(config['name']))
    count = f'{member_count:,}' if member_count is not None else '—'
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(
        ui.TextDisplay(
            f'{config["welcome"]["icon"]} Welcome {member.mention} to **{server_name}**! {greeting}'
        ),
        ui.ActionRow(
            ui.Button(label=f'Members: {count}', style=discord.ButtonStyle.secondary,
                      custom_id='esports:welcome:members:v1', disabled=True),
            ui.Button(label='Dashboard', emoji='📋',
                      url=f'https://discord.com/channels/{config["guild_id"]}/{config["channels"]["dashboard"]}'),
        ),
    ))
    return view
