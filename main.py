import time
import aiohttp
import aiofiles
import asyncio
import feedparser
from feedparser import FeedParserDict
import argparse
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from discord_webhook import AsyncDiscordWebhook
from envdefault import EnvDefault
from dotenv import load_dotenv

load_dotenv()

console = Console()

async def fetch_rss(session : aiohttp.ClientSession, url, progress, task_progress):
    # console.log(f"Fetching feed: {url}")
    progress.update(task_progress, description = f"{url} Fetching...")
    try:
        async with session.get(url) as response:
            text = await response.text() or None
            if text == None:
                progress.update(f"{url} Failed to fetch ❌")
            else:
                progress.update(task_progress, advance=1, description = f"{url} Fetched")
            return (url, text)
    except:
        progress.update(f"{url} Failed to fetch ❌")
    return(url, None)

async def main(filename : str, webhook_url : str):
    urls = []
    async with aiofiles.open(filename, mode='r') as f:
        async for line in f:
            urls.append(line)

    if urls.count == 0:
        console.log(f"\"{filename}\" has no entries")
        return

    with Progress(console=console) as progress:
        url_progresses = []
        for url in urls:
            url_progresses.append(progress.add_task(url, total=2))
        async with aiohttp.ClientSession() as session:
            tasks = []
            for index, url in enumerate(urls):
                tasks.append(fetch_rss(session, url, progress, url_progresses[index]))
                            
            results = await asyncio.gather(*tasks)

        table = Table(title="Results")

        table.add_column("Link")
        table.add_column("Description")
        table.add_column("Published")

        webhooks = []
        for index, (url, text) in enumerate(results):
            if text == None:
                continue
            progress.update(url_progresses[index], description=f"{url} Parsing")
            feed = feedparser.parse(text)
            if feed.bozo > 0:
                progress.update(url_progresses[index], description=f"{url} Parsing failed ❌")
                continue
            progress.update(url_progresses[index], advance=1, description=f"{url} Parsed")

            if index != 0:
                table.add_section()

            for index, e in enumerate(feed.entries):
                table.add_row(e.link, e.description, e.published)
                if index == 0:
                    webhooks.append(send_webhook(webhook_url, e))
        
        console.print(table)
        await asyncio.gather(*webhooks)

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
    
    args = parser.parse_args()
    start_time = time.time()
    asyncio.run(main(args.filename, args.webhook))
    console.log(f"Total time taken: {time.time() - start_time} seconds")