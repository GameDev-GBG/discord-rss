import time
import aiofiles
import asyncio
import feedparser
from feedparser import FeedParserDict
import argparse
from rich.console import Console
from rich.table import Table
from rich.live import Live
from discord_webhook import AsyncDiscordWebhook
from envdefault import EnvDefault
from dotenv import load_dotenv
from typing import List
from datetime import datetime

load_dotenv()

class SocialEntry:
    def __init__(self, url : str, posted : datetime):
        self.url=url
        self.posted=posted

class SocialFeed:
    def __init__(self, url : str):
        self.url = url
        self.etag = None
        self.modified = None
        self.modified_parsed = None
        self.last_checked = None
        self.entries = List[SocialEntry]
        self.title = url
        self.avatar_url = None
        self.status = "🚩"

    async def check(self):
        self.last_checked = datetime.now()
        self.status = "⏳"

        res = await asyncio.get_event_loop().run_in_executor(None, feedparser.parse, self.url, self.modified, self.etag)
        if res.status == 304:
            # No changes
            self.status = "✅"
            return
        
        if res.bozo > 1:
            self.status = "⚠️"
        else:
            self.status = "✅"

        self.etag = getattr(res, "etag", None)
        self.modified = getattr(res, "modified", None)
        self.modified_parsed = getattr(res, "modified_parsed", None)

        feed = getattr(res, 'feed', None)
        image = None
        if feed is not None:
            self.title = getattr(feed, "title", self.url)
            image = getattr(feed, "image", None)
        if image is not None:
            self.avatar_url = getattr(image, "href", None)

async def check_feeds(feeds : List[SocialFeed]):
    checks = []
    for feed in feeds:
        checks.append(feed.check())
    await asyncio.gather(*checks)

def render_table(feeds : List[SocialFeed]) -> Table:
    table = Table(title="Feeds")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Last Checked")
    table.add_column("Last Modified")
    for feed in feeds:
        table.add_row(str(feed.title), str(feed.status), str(feed.last_checked), str(feed.modified_parsed))
    return table

async def render(console : Console, feeds : List[SocialFeed]):
    with Live(render_table(feeds), auto_refresh=False, console=console) as live:
        while True:
            await asyncio.sleep(0.25)
            live.update(render_table(feeds), refresh=True)

async def main(filename : str, webhook_url : str, should_render : bool):
    console = Console()
    feeds = []
    async with aiofiles.open(filename, mode='r') as f:
        async for line in f:
            feeds.append(SocialFeed(line))

    if feeds.count == 0:
        console.log(f"\"{filename}\" has no entries")
        return

    if should_render == True:
        asyncio.create_task(render(console, feeds))

    while True:
        console.log("Checking feeds...")
        t = time.time()
        await check_feeds(feeds)
        console.log(f"Took {time.time() - t} seconds")
        await asyncio.sleep(2)

async def send_webhook(webhook_url : str, entry : FeedParserDict):
    webhook = AsyncDiscordWebhook(webhook_url, content = entry.link)
    await webhook.execute()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog = 'Discord RSS Socials',
        description= 'Polls RSS feeds and posts updates to Discord via a webhook.',
        epilog= 'Good bye!'
    )
    parser.add_argument('filename', type=str,
                        help="Path to a file containing URL:s to RSS feeds, separated by new lines.")
    parser.add_argument('-wh', '--webhook', action=EnvDefault, type=str, envvar='DISCORD_WEBHOOK',
                        help='A Discord webhook URL. You can generate this for a channel under Edit Channel/Integrations/Webhooks.\n' \
                            'Can also be specified using DISCORD_WEBHOOK environment variable.')
    parser.add_argument('-r', '--render', action='store_true')
    
    args = parser.parse_args()
    asyncio.run(main(args.filename, args.webhook, args.render))
