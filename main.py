import time
import aiohttp
import asyncio
import feedparser
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

console = Console()

async def fetch_rss(session, url, progress, task_progress):
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

async def main():
    urls = [
        "https://bsky.app/profile/yukiguni.games/rss",
        "https://bsky.app/profile/moonhood.bsky.social/rss",
        "https://bsky.app/profile/riverendgames.bsky.social/rss",
        "https://bsky.app/profile/splendidfailures.bsky.social/rss",
        "https://bsky.app/profile/ycjygames.bsky.social/rss",
        "https://mastodon.gamedev.place/@yukigunigames.rss"
    ]

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

            for e in feed.entries:
                table.add_row(e.link, e.description, e.published)
        
        console.print(table)

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    console.log(f"Total time taken: {time.time() - start_time} seconds")