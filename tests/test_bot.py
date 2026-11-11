import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import discord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import EsportsBot, is_staff, load_config, ticket_overwrites
from moderation import target_error
from panels import panel, TicketControls
from storage import Store
from transcripts import export_transcript, render_message


class StoreTests(unittest.TestCase):
    def test_duplicate_tickets_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            store = Store(path)
            store.add_ticket(101, 1, 'general')
            with self.assertRaises(sqlite3.IntegrityError):
                store.add_ticket(102, 1, 'general')
            store.add_ticket(103, 1, 'paid')
            store.execute('UPDATE tickets SET claimed_by=5 WHERE channel_id=101')
            store.close()
            store = Store(path)
            self.assertEqual(store.ticket(101)['claimed_by'], 5)
            store.execute("UPDATE tickets SET status='closed' WHERE channel_id=101")
            store.add_ticket(104, 1, 'general')
            self.assertEqual(store.active(1, 'general')['channel_id'], 104)
            store.close()

    def test_moderator_hierarchy(self):
        guild = NS(owner_id=1, me=NS(id=9, top_role=80))
        actor = NS(id=2, top_role=50)
        self.assertIsNone(target_error(guild, actor, NS(id=3, top_role=20)))
        for target in (NS(id=1, top_role=100), NS(id=2, top_role=50), NS(id=3, top_role=50), NS(id=9, top_role=80)):
            self.assertIsNotNone(target_error(guild, actor, target))
        self.assertIsNotNone(target_error(guild, NS(id=1, top_role=100), NS(id=3, top_role=90)))

    def test_staff_is_scoped_by_ticket_kind(self):
        cfg = load_config()
        cfg['tickets']['ownership']['staff_role_ids'] = ['7']
        member = NS(guild_permissions=NS(administrator=False), roles=[NS(id=1564325589827977330)])
        self.assertTrue(is_staff(member, 'general', cfg))
        self.assertFalse(is_staff(member, 'ownership', cfg))
        member.guild_permissions.administrator = True
        self.assertTrue(is_staff(member, 'ownership', cfg))

    def test_ownership_role_excludes_general_staff(self):
        cfg = load_config()
        staff = NS(guild_permissions=NS(administrator=False), roles=[NS(id=1564325589827977330)])
        owner_staff = NS(guild_permissions=NS(administrator=False), roles=[NS(id=1569278707833503776)])
        self.assertFalse(is_staff(staff, 'ownership', cfg))
        self.assertTrue(is_staff(owner_staff, 'ownership', cfg))
        self.assertTrue(is_staff(staff, 'general', cfg))
        self.assertTrue(is_staff(staff, 'paid', cfg))

    def test_ticket_overwrites_are_private(self):
        guild = NS(default_role=discord.Object(1), me=discord.Object(2))
        owner, staff = discord.Object(3), discord.Object(4)
        permissions = ticket_overwrites(guild, owner, [staff])
        self.assertFalse(permissions[guild.default_role].view_channel)
        self.assertTrue(permissions[owner].view_channel)
        self.assertTrue(permissions[staff].send_messages)
        self.assertFalse(permissions[owner].create_public_threads)
        self.assertEqual(len(permissions), 4)
        with self.assertRaises(ValueError):
            ticket_overwrites(guild, owner, [guild.default_role])

    def test_transcript_escapes_untrusted_content(self):
        msg = NS(content='<script>alert(1)</script>', author=NS(id=1), id=5,
                 created_at=datetime.now(timezone.utc), edited_at=None, embeds=[],
                 attachments=[NS(url='javascript:alert(1)', filename='<evil>')])
        rendered = render_message(msg)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('&lt;evil&gt;', rendered)


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = EsportsBot(load_config(), Path(self.tmp.name) / 'state.db')
        self.bot._connection.user = NS(id=99)
        self.bot.ready_for_tickets = True

    async def asyncTearDown(self):
        await self.bot.close()
        self.tmp.cleanup()

    def interaction(self):
        return NS(channel_id=100, id=987654, user=NS(id=5), message=None,
                  response=NS(defer=AsyncMock(), is_done=lambda: True),
                  followup=NS(send=AsyncMock()))

    async def test_status_refreshes_server_count_in_watching_activity(self):
        self.bot.is_ready = Mock(return_value=True)
        self.bot.fetch_guild = AsyncMock(side_effect=[NS(approximate_member_count=1234), NS(approximate_member_count=1235)])
        self.bot.change_presence = AsyncMock()
        await self.bot.member_count_status()
        await self.bot.member_count_status()
        activities = [call.kwargs['activity'] for call in self.bot.change_presence.await_args_list]
        self.assertEqual([activity.name for activity in activities], ['1,234 members!', '1,235 members!'])
        self.assertTrue(all(activity.type == discord.ActivityType.watching for activity in activities))
        self.bot.fetch_guild.assert_awaited_with(int(self.bot.config['guild_id']), with_counts=True)
        self.assertEqual(self.bot.member_count_status.minutes, 1)

    async def test_status_recovers_after_temporary_failure(self):
        self.bot.is_ready = Mock(return_value=True)
        self.bot.fetch_guild = AsyncMock(side_effect=[OSError('Temporary network failure'), NS(approximate_member_count=42)])
        self.bot.change_presence = AsyncMock()
        with self.assertLogs('esports', level='WARNING'):
            await self.bot.member_count_status()
        self.bot.change_presence.assert_not_awaited()
        await self.bot.member_count_status()
        self.assertEqual(self.bot.change_presence.await_args.kwargs['activity'].name, '42 members!')

    async def test_all_panels_serialize_and_buttons_persist(self):
        ids = []
        for kind in ('dashboard', 'marketplace', 'support', 'rules'):
            view = panel(self.bot, kind)
            payload = json.dumps(view.to_components())
            self.assertIn('attachment://banner.png', payload)
            self.assertIn('attachment://footer.png', payload)
            self.assertLessEqual(view.content_length(), 4000)
            self.assertLessEqual(view.total_children_count, 40)
            self.assertTrue(view.is_persistent())
            for item in view.walk_children():
                if getattr(item, 'custom_id', None):
                    ids.append(item.custom_id)
                if getattr(item, 'label', None) == 'Careers':
                    self.assertTrue(item.disabled)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(TicketControls(self.bot).is_persistent())
        self.assertEqual(len(self.bot.tree.get_commands()), 13)

    async def test_ticket_menu_matches_reference(self):
        view = panel(self.bot, 'support')
        select = next(item for item in view.walk_children() if isinstance(item, discord.ui.Select))
        self.assertEqual([o.label for o in select.options], ['General Support', 'Ownership Support', 'Paid Ad/SPGW'])

    async def test_simultaneous_claims_have_one_winner(self):
        self.bot.store.add_ticket(100, 1, 'general')
        self.bot.ticket_access = AsyncMock(return_value=self.bot.store.ticket(100))
        first, second = self.interaction(), self.interaction()
        first.channel = second.channel = NS(send=AsyncMock())
        second.user.id = 6
        await asyncio.gather(self.bot.claim_ticket(first), self.bot.claim_ticket(second))
        self.assertIn(self.bot.store.ticket(100)['claimed_by'], (5, 6))
        self.assertEqual(first.channel.send.await_count, 1)

    async def closure_fixture(self):
        self.bot.store.add_ticket(100, 1, 'general')
        self.bot.ticket_access = AsyncMock(return_value=self.bot.store.ticket(100))
        channel = NS(id=100, name='general-1', overwrites={}, edit=AsyncMock(), delete=AsyncMock(),
                     guild=NS(filesize_limit=10_000_000))
        archive = NS(send=AsyncMock())
        self.bot.channel = AsyncMock(side_effect=[channel, archive])
        path = Path(self.tmp.name) / 'transcript.html'
        path.write_text('<html>Test transcript</html>')
        return channel, archive, path

    async def test_failed_upload_never_deletes_channel(self):
        channel, archive, path = await self.closure_fixture()
        archive.send.side_effect = RuntimeError('Simulated failed upload')
        with patch('bot.export_transcript', AsyncMock(return_value=([path], 1))), \
             patch('bot.restore_overwrites', AsyncMock()) as restore, self.assertLogs('esports', level='ERROR'):
            await self.bot.close_ticket(self.interaction(), 'Resolved')
        channel.delete.assert_not_awaited()
        restore.assert_awaited_once()
        self.assertEqual(self.bot.store.ticket(100)['status'], 'open')

    async def test_history_failure_never_deletes_channel(self):
        channel, archive, path = await self.closure_fixture()
        with patch('bot.export_transcript', AsyncMock(side_effect=RuntimeError('History unavailable'))), \
             patch('bot.restore_overwrites', AsyncMock()), self.assertLogs('esports', level='ERROR'):
            await self.bot.close_ticket(self.interaction(), 'Resolved')
        channel.delete.assert_not_awaited()
        archive.send.assert_not_awaited()

    async def test_delete_runs_only_after_every_part_uploaded(self):
        channel, archive, path = await self.closure_fixture()
        events = []
        async def uploaded(**kwargs):
            self.assertNotIn('content', kwargs)
            self.assertEqual(kwargs['embed'].title, 'Ticket Transcript')
            self.assertNotIn('color', kwargs['embed'].to_dict())
            self.assertTrue(kwargs['file'].filename.endswith('.zip'))
            with zipfile.ZipFile(kwargs['file'].fp) as archive_file:
                self.assertEqual(archive_file.read('transcript.html'), b'<html>Test transcript</html>')
            events.append('uploaded')
        async def deleted(**kwargs):
            events.append('deleted')
        archive.send.side_effect = uploaded
        channel.delete.side_effect = deleted
        with patch('bot.export_transcript', AsyncMock(return_value=([path, path], 2))):
            await self.bot.close_ticket(self.interaction(), 'Resolved')
        self.assertEqual(events, ['uploaded', 'uploaded', 'deleted'])
        self.assertEqual(self.bot.store.ticket(100)['status'], 'closed')

    async def test_existing_ownership_ticket_permissions_are_replaced(self):
        owner, staff = discord.Object(12), discord.Object(1569278707833503776)
        guild = NS(default_role=discord.Object(1), me=discord.Object(99), get_member=lambda _: owner)
        category = NS(id=500, guild=guild)
        ticket_channel = Mock(spec=discord.TextChannel)
        ticket_channel.id = 100
        ticket_channel.category_id = 500
        ticket_channel.topic = 'Esports Business | Ownership Support | Owner: 12'
        ticket_channel.edit = AsyncMock()
        unrelated = Mock(spec=discord.TextChannel)
        unrelated.id = 101
        unrelated.category_id = 500
        unrelated.topic = 'Unrelated channel'
        unrelated.edit = AsyncMock()
        guild.text_channels = [ticket_channel, unrelated]
        guild.fetch_channels = AsyncMock(side_effect=discord.InvalidData(
            'Unknown channel type 20 for channel ID 1569462259506225216.'))
        self.bot.channel = AsyncMock(return_value=category)
        with patch.object(self.bot, 'staff_roles', return_value=[staff]):
            await self.bot.sync_ownership_permissions()
        overwrites = ticket_channel.edit.await_args.kwargs['overwrites']
        self.assertEqual({target.id for target in overwrites}, {1, 99, 12, 1569278707833503776})
        self.assertFalse(overwrites[guild.default_role].view_channel)
        unrelated.edit.assert_not_awaited()
        guild.fetch_channels.assert_not_awaited()

    async def test_unknown_server_channel_does_not_block_ticket_startup(self):
        guild = NS(text_channels=[], fetch_channels=AsyncMock(side_effect=discord.InvalidData(
            'Unknown channel type 20 for channel ID 1569462259506225216.')))
        self.bot.channel = AsyncMock(return_value=NS(id=500, guild=guild))
        self.bot.recover_closures = AsyncMock()
        self.bot.ready_for_tickets = False
        with patch.object(self.bot, 'staff_roles', return_value=[]):
            await self.bot.on_ready()
        self.assertTrue(self.bot.ready_for_tickets)
        self.assertTrue(self.bot.started)
        guild.fetch_channels.assert_not_awaited()

    async def test_real_ownership_permission_failure_still_blocks_startup(self):
        self.bot.recover_closures = AsyncMock()
        self.bot.sync_ownership_permissions = AsyncMock(side_effect=discord.Forbidden(
            NS(status=403, reason='Forbidden'), 'Missing Permissions'))
        self.bot.ready_for_tickets = False
        with self.assertLogs('esports', level='ERROR'):
            await self.bot.on_ready()
        self.assertFalse(self.bot.ready_for_tickets)
        self.assertFalse(self.bot.started)

    async def test_restart_restores_interrupted_closure(self):
        self.bot.store.add_ticket(100, 1, 'general')
        self.bot.store.execute("UPDATE tickets SET status='closing', original_overwrites='[]' WHERE channel_id=100")
        self.bot.channel = AsyncMock(return_value=NS(id=100))
        with patch('bot.restore_overwrites', AsyncMock()) as restore:
            await self.bot.recover_closures()
        restore.assert_awaited_once()
        self.assertEqual(self.bot.store.ticket(100)['status'], 'open')

    async def test_transcript_paginates_and_keeps_messages(self):
        async def history(**kwargs):
            self.assertIsNone(kwargs['limit'])
            self.assertTrue(kwargs['oldest_first'])
            for index in range(4):
                yield NS(content=f'Message {index} ' + 'x' * 1000, author=NS(id=1), id=index,
                         created_at=datetime.now(timezone.utc), edited_at=None, attachments=[], embeds=[])
        channel = NS(id=100, name='general-1', history=history)
        self.bot.store.add_ticket(100, 1, 'general')
        paths, count = await export_transcript(channel, self.bot.store.ticket(100), NS(id=5),
                                               '<unsafe reason>', Path(self.tmp.name) / 'export', None, max_bytes=3000)
        self.assertEqual(count, 4)
        self.assertGreater(len(paths), 1)
        joined = ''.join(path.read_text(encoding='utf-8') for path in paths)
        for index in range(4):
            self.assertEqual(joined.count(f'Message {index} '), 1)
        self.assertNotIn('<unsafe reason>', joined)


if __name__ == '__main__':
    unittest.main()
