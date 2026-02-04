import time
import aiofiles
import asyncio
import feedparser
import argparse
from rich.console import Console
from rich.table import Table
from rich.live import Live
from discord_webhook import AsyncDiscordWebhook
from envdefault import EnvDefault
from dotenv import load_dotenv
from typing import List
from typing import Dict
import datetime
import http.client
from dateutil import parser as dateparser

load_dotenv()

class RssEntry:
    def __init__(self, feed: RssFeed, url : str, time_posted : datetime.datetime):
        self.feed = feed
        self.url=url
        self.time_posted=time_posted

class RssFeed:
    def __init__(self, url : str, console: Console):
        self.url : str = url
        self.http_etag : str = None
        self.http_modified : str = None
        self.updated_str : str = None
        self.updated_parsed : datetime.datetime = None
        self.last_checked : datetime.datetime = None
        self.entries : Dict[str, RssEntry] = {}
        self.title : str = url
        self.user_name : str = None
        self.avatar_url : str = None
        self.status : str = ":rocket:"
        self.console = console

    async def check(self, since : datetime.datetime, queue : asyncio.Queue[RssEntry]):
        self.last_checked = datetime.datetime.now()
        self.status = ":fast_down_button:"

        # Kwargs would be better here
        res = await asyncio.get_event_loop().run_in_executor(None, feedparser.parse, self.url, self.http_etag, self.http_modified)

        if res.bozo:
            self.status = f":x: {str(res.bozo_exception)}"
            return

        if res.status == http.client.NOT_MODIFIED:
            # No changes
            self.status = ":white_heavy_check_mark:"
            return
        
        # 302 Found is returned by Bluesky if you use the actual 
        # https://bsky.app/profile/<username>/rss url, it redirects you to
        # where they want you to go
        if res.status != http.client.OK and res.status != http.client.FOUND:
            self.status = f":warning: {http.client.responses[res.status]}"
            return
        
        self.status = ":white_heavy_check_mark:"

        self.http_modified = getattr(res, "modified", None)
        self.http_etag = getattr(res, "etag", None)

        feed = getattr(res, 'feed', None)
        image = None
        if feed is not None:
            self.updated_str = getattr(feed, "updated", None)
            if self.updated_str is not None:
                self.updated_parsed = dateparser.parse(self.updated_str)
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
        if entries is None:
            return # Not good that we don't have any entries

        for entry in entries:
            id = getattr(entry, 'id', None)
            if id is None:
                # Can't use this at all
                continue

            if id in self.entries:
                # It might have been updated, but let's not care about that right now
                continue
            
            entry_url = getattr(entry, 'link', None)
            entry_published : str = getattr(entry, 'published', None)
            if entry_url is None or entry_published is None:
                continue

            published = dateparser.parse(entry_published)
            rss_entry = RssEntry(self, entry_url, published)
            self.entries[id] = rss_entry
            if published >= since:
                await queue.put(rss_entry)

def date_time_from_struct(t : time.struct_time):
    # datetime(year, month, day[, hour[, minute[, second[, microsecond[,tzinfo]]]]])
    return datetime.datetime(t.tm_year, t.tm_mon, t.day)

# ---- Checking Feeds ----

async def check_feeds(feeds : List[RssFeed], since : datetime.datetime, queue : asyncio.Queue[RssEntry]):
    checks = []
    for feed in feeds:
        checks.append(feed.check(since, queue))
    await asyncio.gather(*checks)

# ---- Posting ----

async def run_webhook_queue(console : Console, webhook_url : str, queue : asyncio.Queue[RssEntry]):
    while True:
        rss_entry = await queue.get()
        await send_webhook(console, webhook_url, rss_entry)

async def send_webhook(console : Console, webhook_url : str, entry : RssEntry):
    console.log(F"We are sending {entry.url} which was posted at {entry.time_posted}")

    webhook = AsyncDiscordWebhook(webhook_url, content = entry.url)
    webhook.username = entry.feed.user_name
    webhook.avatar_url = entry.feed.avatar_url
    webhook.rate_limit_retry = True
    resp = await webhook.execute()
    if resp.status_code == http.client.OK:
        console.log(f"Sent successfully!")
    else:
        console.log(f"Sending post failed: {resp.status_code} {http.client.responses[resp.status_code]}")

# ---- Render ----
def render_table(feeds : List[RssFeed], since : datetime.datetime) -> Table:
    table = Table(title=f"Feeds (Checking since {str(since)})")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Last Checked")
    table.add_column("Updated")
    table.add_column("E-tag")
    table.add_column("Modified")
    for feed in feeds:
        table.add_row(str(feed.title), str(feed.status), str(feed.last_checked), str(feed.updated_str), str(feed.http_etag), str(feed.http_modified))
    return table

async def render(console : Console, feeds : List[RssFeed], since : datetime.datetime):
    with Live(render_table(feeds, since), auto_refresh=False, console=console) as live:
        while True:
            await asyncio.sleep(0.25)
            live.update(render_table(feeds, since), refresh=True)

async def main(filename : str, webhook_url : str, since : datetime.datetime, should_render : bool):
    console = Console()
    feeds = []
    async with aiofiles.open(filename, mode='r') as f:
        async for line in f:
            feeds.append(RssFeed(line, console))

    if feeds.count == 0:
        console.log(f"\"{filename}\" has no entries")
        return

    queue = asyncio.Queue[RssEntry]()

    # Spin up queue routine which pushes out new webhooks
    asyncio.create_task(run_webhook_queue(console, webhook_url, queue))

    # Spin up rendering routine if requested
    if should_render == True:
        asyncio.create_task(render(console, feeds, since))

    # Just endlessly check feeds and push to the queue
    while True:
        console.log("Checking feeds...")
        t = time.time()
        await check_feeds(feeds, since, queue)
        console.log(f"Took {time.time() - t} seconds")

        await asyncio.sleep(10)

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
                        help='Specify a time to use as cutoff point for new posts (yyyy-mm-dd HH:MM). Always in UTC.')
    parser.add_argument('-r', '--render', action='store_true')
    
    args = parser.parse_args()

    since = datetime.datetime.now(datetime.UTC)
    if args.since is not None:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d %H:%M")
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a valid date: {args.since!r}")

    asyncio.run(main(args.filename, args.webhook, since, args.render))
