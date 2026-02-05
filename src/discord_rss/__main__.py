import time
import aiofiles
import asyncio
import feedparser
import argparse
import os
from rich.table import Table
from rich.live import Live
from rich.logging import RichHandler
from discord_webhook import AsyncDiscordWebhook
from dotenv import load_dotenv
from typing import List
from typing import Dict
import datetime
import http.client
from dateutil import parser as dateparser
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

load_dotenv()

logger = logging.getLogger(__name__)

# Source - https://stackoverflow.com/a/10551190
# Posted by Russell Heilling, modified by community. See post 'Timeline' for change history
# Retrieved 2026-02-03, License - CC BY-SA 4.0
class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if envvar:
            if envvar in os.environ:
                default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, 
                                         **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


class RssEntry:
    def __init__(self, feed: RssFeed, url : str, time_posted : datetime.datetime):
        self.feed = feed
        self.url=url
        self.time_posted=time_posted

class RssFeed:
    def __init__(self, url : str):
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

async def check_feeds_task(feeds : List[RssFeed], since : datetime.datetime, queue : asyncio.Queue[RssEntry]):
    while True:
        logger.info("Checking feeds...")
        t = time.time()
        await check_feeds(feeds, since, queue)
        logger.info(f"Took {time.time() - t} seconds")

        await asyncio.sleep(10)

async def check_feeds(feeds : List[RssFeed], since : datetime.datetime, queue : asyncio.Queue[RssEntry]):
    checks = []
    for feed in feeds:
        checks.append(feed.check(since, queue))
    await asyncio.gather(*checks)

# ---- Posting ----

async def webhook_queue_task(webhook_url : str, queue : asyncio.Queue[RssEntry]):
    while True:
        rss_entry = await queue.get()
        await send_webhook(webhook_url, rss_entry)

async def send_webhook(webhook_url : str, entry : RssEntry):
    logger.info(F"We are sending {entry.url} which was posted at {entry.time_posted}")

    webhook = AsyncDiscordWebhook(webhook_url, content = entry.url)
    webhook.username = entry.feed.user_name
    webhook.avatar_url = entry.feed.avatar_url
    webhook.rate_limit_retry = True
    resp = await webhook.execute()
    if resp.status_code == http.client.OK:
        logger.info(f"Sent successfully!")
    else:
        logger.info(f"Sending post failed: {resp.status_code} {http.client.responses[resp.status_code]}")

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

async def render(feeds : List[RssFeed], since : datetime.datetime):
    with Live(render_table(feeds, since), auto_refresh=False) as live:
        while True:
            await asyncio.sleep(0.25)
            live.update(render_table(feeds, since), refresh=True)

# Kudos: https://www.slingacademy.com/article/python-ways-to-check-if-a-string-is-a-valid-url/
def is_valid_url(url : str):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

async def main():
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
    parser.add_argument('-l', '--logs', action=EnvDefault, type=str, envvar='LOG_FILE_PATH', required=False,
                        help='Path to a log file to write to.\n' \
                            'Can also be specified using LOG_FILE_PATH environment variable.')
    parser.add_argument('-s', '--since', type=str,
                        help='Specify a time to use as cutoff point for new posts (yyyy-mm-dd HH:MM). Always in UTC.')
    parser.add_argument('-r', '--render', action='store_true',
                        help="Displays application status in a nicely rendered terminal window.")
    
    args = parser.parse_args()

    FORMAT = "%(message)s"
    handlers = [RichHandler()]
    if args.logs:
        p = Path(args.logs)
        if p.parent is not None and p.parent.is_dir:
            p.parent.mkdir(parents=True, exist_ok=True)
            
        file_log = RotatingFileHandler(
            filename=args.logs,
            mode='a',
            maxBytes=1e+7, # 10 mb
            backupCount=3
        )
        handlers.append(file_log)
    logging.basicConfig(level='NOTSET', format=FORMAT, datefmt="[%X]", handlers=handlers)

    since = datetime.datetime.now(datetime.UTC)
    if args.since is not None:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d %H:%M")
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a valid date: {args.since!r}")

    filename = args.filename
    webhook_url = args.webhook
    should_render = args.render

    feeds = []
    async with aiofiles.open(filename, mode='r') as f:
        line_no = 0
        async for line in f:
            line_no += 1
            if not is_valid_url(line):
                logger.warning(f"{filename}:{line_no}: \"{line}\" is not a valid url. Skipping.")
                continue
                
            feeds.append(RssFeed(line))

    if len(feeds) == 0:
        logger.error(f"\"{filename}\" has no entries")
        return

    tasks = []
    queue = asyncio.Queue[RssEntry]()

    # Spin up poll routine which adds new posts to the queue
    tasks.append(asyncio.create_task(check_feeds_task(feeds, since, queue)))

    # Spin up queue routine which pushes out new webhooks
    tasks.append(asyncio.create_task(webhook_queue_task(webhook_url, queue)))

    # Spin up rendering routine if requested
    if should_render == True:
        tasks.append(asyncio.create_task(render(feeds, since)))

    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception:
        logger.exception("Unhandled exception")
