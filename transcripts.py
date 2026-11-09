"""Escaped, paginated HTML transcripts with no scripts or remote embeds."""
import html
import json
from pathlib import Path
from urllib.parse import urlparse


def escape(value):
    return html.escape(str(value), quote=True)


def link(url, label):
    if urlparse(str(url)).scheme not in ('https', 'http'):
        return escape(label)
    return f'<a href="{escape(url)}" rel="noreferrer noopener">{escape(label)}</a>'


def render_message(message):
    body = f'<pre>{escape(message.content or "")}</pre>'
    for attachment in message.attachments:
        body += '<p>Attachment: ' + link(attachment.url, attachment.filename) + '</p>'
    for embed in message.embeds:
        body += '<pre>Embed: ' + escape(json.dumps(embed.to_dict(), ensure_ascii=False, indent=2)) + '</pre>'
    for component in getattr(message, 'components', []):
        body += '<pre>Component: ' + escape(json.dumps(component.to_dict(), ensure_ascii=False, indent=2)) + '</pre>'
    for sticker in getattr(message, 'stickers', []):
        body += '<p>Sticker: ' + escape(sticker.name) + '</p>'
    reference = getattr(message, 'reference', None)
    if reference and reference.message_id:
        body += f'<p>Reply to message {reference.message_id}</p>'
    edited = f' | edited {escape(message.edited_at.isoformat())}' if message.edited_at else ''
    return (
        f'<article><h3>{escape(message.author)} ({message.author.id})</h3>'
        f'<small>{escape(message.created_at.isoformat())} | Message {message.id}{edited}</small>'
        f'{body}</article>\n'
    )


async def export_transcript(channel, ticket, closer, reason, directory: Path, cutoff, max_bytes=2_000_000):
    """History failures propagate; callers must never delete a channel on failure."""
    directory.mkdir(parents=True, exist_ok=True)
    header = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        '<title>Esports Business — Ticket transcript</title>'
        '<style>body{font:15px system-ui;background:#111827;color:#e5e7eb;max-width:1000px;'
        'margin:32px auto;padding:0 20px}article{border-top:1px solid #374151;padding:14px 0}'
        'h1{color:#ff6154}h3{margin-bottom:5px}small{color:#9ca3af}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}a{color:#93c5fd}</style>'
        f'<h1>Esports Business — #{escape(channel.name)}</h1>'
        f'<p>Channel: {channel.id} | Type: {escape(ticket["kind"])} | Owner: {ticket["owner_id"]}</p>'
        f'<p>Opened: {escape(ticket["created_at"])} | Claimed by: {ticket["claimed_by"] or "Unclaimed"}</p>'
        f'<p>Closed by: {escape(closer)} ({closer.id}) | Reason: {escape(reason)}</p>'
        '<p>Times are UTC. Snapshot of messages available at closure. Deleted messages are unavailable; '
        'attachment links may expire. This file does not embed attachment downloads.</p>'
    )
    footer = '</html>'
    paths, chunks, size, count = [], [header], len(header.encode('utf-8')), 0

    def flush():
        path = directory / f'ticket-{channel.id}-part-{len(paths) + 1}.html'
        path.write_text(''.join(chunks) + footer, encoding='utf-8')
        paths.append(path)

    async for message in channel.history(limit=None, oldest_first=True, before=cutoff):
        entry = render_message(message)
        entry_size = len(entry.encode('utf-8'))
        if size + entry_size > max_bytes and len(chunks) > 1:
            flush()
            chunks, size = [header], len(header.encode('utf-8'))
        chunks.append(entry)
        size += entry_size
        count += 1
    flush()
    return paths, count
