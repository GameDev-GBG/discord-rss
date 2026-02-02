import time
import aiohttp
import asyncio
import xml.etree.ElementTree as ET

def xml_extract_text(element):
    if element is not None:
        return element.text
    return None

async def fetch_rss(session, url):
    print(f"Fetching feed: {url}")
    async with session.get(url) as response:
        data = await response.text()
        print(f"Fetched feed: {url}")
        return data

async def main():
    urls = [
        "https://openrss.org/feed/bsky.app/profile/yukiguni.games",
        "https://mastodon.gamedev.place/@yukigunigames.rss"
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_rss(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

        for rss_feed in results:
            root = ET.fromstring(rss_feed)
            items = root.findall('.//item')
            for item in items:
                title = xml_extract_text(item.find('title'))
                link = xml_extract_text(item.find('link'))
                description = xml_extract_text(item.find('description'))
                print(f"Title: {title}")
                print(f"Description: {description}")
                print(f"Link: {link}")
            

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    print(f"Total time taken: {time.time() - start_time} seconds")