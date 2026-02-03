import time
import aiohttp
import asyncio
import feedparser
from rich.console import Console
from rich.progress import Progress

console = Console()

async def fetch_rss(session, url, progress, task_progress):
    # console.log(f"Fetching feed: {url}")
    progress.update(task_progress, description = F"{url} Fetching...")
    async with session.get(url) as response:
        text = await response.text() or None
        if text == None:
            progress.update("{url} Failed to fetch ❌")
        else:
            progress.update(task_progress, advance=1, description = "{url} Fetched")
        return (url, text)

async def main():
    urls = [
        "https://openrss.org/feed/bsky.app/profile/yukiguni.games",
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

        for index, (url, text) in enumerate(results):
            if text == None:
                continue
            progress.update(url_progresses[index], description=f"{url} Parsing")
            feed = feedparser.parse(text)
            if feed.bozo > 0:
                progress.update(url_progresses[index], description=f"{url} Parsing failed ❌")
                continue
            progress.update(url_progresses[index], advance=1, description=f"{url} Parsed")

                

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    console.log(f"Total time taken: {time.time() - start_time} seconds")