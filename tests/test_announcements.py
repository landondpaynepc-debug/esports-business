import io
import itertools
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands, ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from announcements import announcement_view, post_announcement, register_announcements

BANNER = 'https://example.com/fishy-banner.png'


class AnnouncementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.files = []
        self.guild = NS(id=1, me=discord.Object(99), filesize_limit=10_000_000)
        self.channel = Mock(spec=discord.TextChannel, id=2, guild=self.guild)
        self.channel.permissions_for.return_value = discord.Permissions.all()
        self.channel.send = AsyncMock(return_value=NS(jump_url='https://discord.com/channels/1/2/3'))
        self.interaction = NS(guild=self.guild, guild_id=1, channel=self.channel, filesize_limit=10_000_000,
            response=NS(defer=AsyncMock(), is_done=lambda: True, send_message=AsyncMock()),
            followup=NS(send=AsyncMock()))

    def attachment(self, **overrides):
        async def to_file(**kwargs):
            file = discord.File(io.BytesIO(b'image-test-data'), **kwargs)
            self.files.append(file)
            return file
        fields = dict(filename='same.png', content_type='image/png', width=640, height=320,
                      size=100, to_file=AsyncMock(side_effect=to_file))
        fields.update(overrides)
        return NS(**fields)

    def feedback_text(self):
        return json.dumps(self.interaction.followup.send.await_args.kwargs['view'].to_components())

    async def test_all_optional_image_combinations_keep_requested_order(self):
        for top, bottom, logo in itertools.product((False, True), repeat=3):
            with self.subTest(top=top, bottom=bottom, logo=logo):
                view = announcement_view('Required text', image_above=BANNER if top else None,
                    image_below='attachment://bottom.png' if bottom else None,
                    logo='attachment://logo.png' if logo else None)
                self.assertIsInstance(view, ui.LayoutView)
                container = view.to_components()[0]
                self.assertEqual(container['type'], 17)
                self.assertIsNone(view.children[0].accent_colour)
                expected = ([12] if top else []) + ([9] if logo else [10]) + ([12] if bottom else [])
                self.assertEqual([child['type'] for child in container['components']], expected)
                if logo:
                    self.assertEqual(container['components'][int(top)]['accessory']['type'], 11)
                self.assertEqual(view.content_length(), len('Required text'))

    async def test_default_banner_and_optional_bottom_and_logo_are_v2(self):
        await post_announcement(self.interaction, 'Hello **everyone**', image_below=self.attachment(),
                                logo=self.attachment(), default_banner=BANNER)
        sent = self.channel.send.await_args.kwargs
        self.assertNotIn('content', sent)
        self.assertNotIn('embed', sent)
        self.assertIsInstance(sent['view'], ui.LayoutView)
        container = sent['view'].to_components()[0]['components']
        self.assertEqual([child['type'] for child in container], [12, 9, 12])
        self.assertEqual(container[0]['items'][0]['media']['url'], BANNER)
        self.assertEqual(container[1]['accessory']['media']['url'], 'attachment://announcement-logo.png')
        self.assertEqual(container[2]['items'][0]['media']['url'], 'attachment://announcement-image_below.png')
        self.assertEqual(len({file.filename for file in sent['files']}), 2)
        self.assertTrue(all(file.fp.closed for file in self.files))
        self.assertEqual(sent['allowed_mentions'].to_dict()['parse'], [])
        self.assertIsInstance(self.interaction.followup.send.await_args.kwargs['view'], ui.LayoutView)
        self.assertIn('Announcement posted', self.feedback_text())

    async def test_banner_can_be_disabled_for_description_only(self):
        await post_announcement(self.interaction, 'Text only', default_banner=BANNER, use_banner=False)
        sent = self.channel.send.await_args.kwargs
        self.assertEqual([child['type'] for child in sent['view'].to_components()[0]['components']], [10])
        self.assertEqual(sent['files'], [])

    async def test_uploaded_top_overrides_banner_and_selected_channel_is_used(self):
        destination = Mock(spec=discord.TextChannel, id=4, guild=self.guild)
        destination.permissions_for.return_value = discord.Permissions.all()
        destination.send = AsyncMock(return_value=NS(jump_url='https://discord.com/channels/1/4/5'))
        await post_announcement(self.interaction, 'Custom', image_above=self.attachment(),
                                default_banner=BANNER, channel=destination)
        self.channel.send.assert_not_awaited()
        sent = destination.send.await_args.kwargs
        payload = json.dumps(sent['view'].to_components())
        self.assertNotIn(BANNER, payload)
        self.assertIn('attachment://announcement-image_above.png', payload)

    async def test_blank_or_overlong_descriptions_never_post(self):
        for text in ('', '   \n ', 'x' * 4001):
            await post_announcement(self.interaction, text, default_banner=BANNER)
        self.channel.send.assert_not_awaited()
        self.interaction.response.defer.assert_not_awaited()
        self.assertIn('Description is required', self.feedback_text())

    async def test_invalid_images_and_oversize_uploads_never_post(self):
        for upload in (self.attachment(content_type='application/pdf'), self.attachment(width=None),
                       self.attachment(size=10_000_001)):
            await post_announcement(self.interaction, 'Hello', image_above=upload)
            upload.to_file.assert_not_awaited()
        self.channel.send.assert_not_awaited()

    async def test_missing_permissions_and_other_guild_do_not_post(self):
        self.channel.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True)
        await post_announcement(self.interaction, 'Hello', default_banner=BANNER)
        self.assertIn('Embed Links', self.feedback_text())
        self.channel.guild = NS(id=123)
        await post_announcement(self.interaction, 'Hello')
        self.assertIn('in this server', self.feedback_text())
        self.channel.send.assert_not_awaited()

    async def test_send_failure_closes_files_and_does_not_claim_success(self):
        self.channel.send.side_effect = discord.Forbidden(NS(status=403, reason='Forbidden'), 'Denied')
        with self.assertLogs('esports', level='ERROR'):
            await post_announcement(self.interaction, 'Hello', image_above=self.attachment())
        self.assertTrue(all(file.fp.closed for file in self.files))
        self.assertNotIn('Announcement posted', self.feedback_text())
        self.channel.send.assert_awaited_once()

    async def test_failed_download_closes_prior_file_without_posting(self):
        broken = self.attachment(to_file=AsyncMock(side_effect=OSError('Download failed')))
        with self.assertLogs('esports', level='ERROR'):
            await post_announcement(self.interaction, 'Hello', image_above=self.attachment(), logo=broken)
        self.assertTrue(all(file.fp.closed for file in self.files))
        self.channel.send.assert_not_awaited()

    async def test_command_requires_only_description_and_checks_admin_permissions(self):
        client = discord.Client(intents=discord.Intents.none())
        tree = app_commands.CommandTree(client)
        register_announcements(NS(tree=tree, config={'branding': {'announcement_banner_url': BANNER}}))
        command = tree.get_command('announce')
        payload = command.to_dict(tree)
        self.assertEqual([option['name'] for option in payload['options'] if option.get('required')], ['description'])
        self.assertEqual(payload['options'][0]['max_length'], 4000)
        self.assertTrue(command.default_permissions.administrator)
        with self.assertRaises(app_commands.MissingPermissions):
            command.checks[0](NS(permissions=discord.Permissions.none()))
        self.assertTrue(command.checks[0](NS(permissions=discord.Permissions(administrator=True))))
        await client.close()
