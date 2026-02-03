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
from copy import deepcopy
from time import mktime

load_dotenv()

class SocialEntry:
    def __init__(self, url : str, time_posted : datetime):
        self.url=url
        self.time_posted=time_posted

class SocialFeed:
    def __init__(self, url : str):
        self.url : str = url
        self.http_etag : str = None
        self.http_modified : str = None
        self.updated : str = None
        self.updated_parsed : datetime = None
        self.last_checked : datetime = None
        self.entries : List[SocialEntry] = []
        self.title : str = url
        self.user_name : str = None
        self.avatar_url : str = None
        self.status : str = "🚩"

    async def check(self):
        self.last_checked = datetime.now()
        self.status = "⏳"

        # Kwargs would be better here
        res = await asyncio.get_event_loop().run_in_executor(None, feedparser.parse, self.url, self.http_etag, self.http_modified)
        if res.status == 304:
            # No changes
            self.status = "✅"
            return
        
        if res.bozo > 1:
            self.status = "⚠️"
        else:
            self.status = "✅"

        self.http_modified = getattr(res, "modified", None)
        self.http_etag = getattr(res, "etag", None)

        feed = getattr(res, 'feed', None)
        image = None
        if feed is not None:
            self.updated = getattr(feed, "updated", None)
            updated_parsed = getattr(feed, "updated_parsed", None)
            if updated_parsed is not None:
                self.updated_parsed = datetime.fromtimestamp(mktime(updated_parsed)) 
            if(hasattr(feed, 'title')):
                self.user_name = feed.title
                self.title = feed.title
            else:
                self.user_name = None
                self.title = self.url
            image = getattr(feed, "image", None)
        if image is not None:
            self.avatar_url = getattr(image, "href", None)
        
        entries = getattr(res, 'entries', None)
        if entries is not None:
            self.entries.clear()
            for entry in entries:
                entry_url = getattr(entry, 'link', None)
                entry_published = getattr(entry, 'published_parsed', None)
                if entry_url is None or entry_published is None:
                    continue
                entry_published = datetime.fromtimestamp(mktime(entry_published))
                self.entries.append(SocialEntry(entry_url, entry_published))

async def check_feeds(feeds : List[SocialFeed]):
    checks = []
    for feed in feeds:
        checks.append(feed.check())
    await asyncio.gather(*checks)

async def post_new(console : Console, webhook_url : str, feeds : List[SocialFeed], since : datetime):
    tasks = []
    for feed in feeds:
        for entry in feed.entries:
            if entry.time_posted < since:
                continue
            tasks.append(send_webhook(console, webhook_url, feed, entry))
    await asyncio.gather(*tasks)

def render_table(feeds : List[SocialFeed]) -> Table:
    table = Table(title="Feeds")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Last Checked")
    table.add_column("Updated")
    table.add_column("E-tag")
    table.add_column("Modified")
    for feed in feeds:
        table.add_row(str(feed.title), str(feed.status), str(feed.last_checked), str(feed.updated), str(feed.http_etag), str(feed.http_modified))
    return table

async def render(console : Console, feeds : List[SocialFeed]):
    with Live(render_table(feeds), auto_refresh=False, console=console) as live:
        while True:
            await asyncio.sleep(0.25)
            live.update(render_table(feeds), refresh=True)

async def main(filename : str, webhook_url : str, since : datetime, should_render : bool):
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
        # Write this before dispatching new posts
        # This would be much better to do with an async queue
        since_cpy = deepcopy(since)
        since = datetime.now()
        await post_new(console, webhook_url, feeds, since_cpy)
        
        await asyncio.sleep(2)

async def send_webhook(console : Console, webhook_url : str, feed : SocialFeed, entry : SocialEntry):
    console.log(F"We are sending {entry.url} which was posted at {entry.time_posted}")
    webhook = AsyncDiscordWebhook(webhook_url, content = entry.url)
    webhook.username = feed.user_name
    webhook.avatar_url = feed.avatar_url
    webhook.rate_limit_retry = True
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
    parser.add_argument('-s', '--since', type=str,
                        help='Specify a time to use as cutoff point for new posts (yyyy-mm-dd HH:MM).')
    parser.add_argument('-r', '--render', action='store_true')
    
    args = parser.parse_args()

    since = datetime.now()
    if args.since is not None:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d %H:%M")
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a valid date: {args.since!r}")

    asyncio.run(main(args.filename, args.webhook, since, args.render))
