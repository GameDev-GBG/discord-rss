# Discord RSS
Polls RSS feeds and posts updates to Discord via a webhook.

## Description
This is a simple Python application which gathers RSS feeds from a text file, polls them occasionally, and outputs new entries to a Discord channel via a [Discord Webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).

The scope of this project very limited, and was created specifically for use in our Discord server. If you wants something more advanced check out [MonitoRSS](https://github.com/synzen/monitorss) or [discord-rss-bot](https://pypi.org/project/discord-rss-bot/).

## Prerequisites
- Python 3.14.0 (likely works on later versions - untested)

## Usage
1. Create a Discord webhook for a channel in your server:
    - Right-click the channel.
    - Select Edit Channel.
    - Go to Integrations/Webhooks and press the New Webhook button.
    - Copy the webhook URL.
    - You can read more about webhooks in [Discord's documentation](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).
2. Find an RSS feed or two that you are interested in (did you know that [Mastodon and Bluesky support RSS feeds](https://lifehacker.com/tech/bluesky-and-mastodon-rss-feed)?).
3. Create a text document with each RSS feed separated by a new line (see `urls.txt` in this repository as an example).
4. Run the application and pass it your text file and webhook URL:
    - Example when installed via PyPi package: `python -m discord_rss <path/to/your/textfile.txt> --webhook <your webhook URL>`
    - There are additional options available, such as rendering real-time information about what the application is up to with `--render` and a directory for logging. Refer to `--help` for more information.

## Installation (via PyPi package)
This assumes you have a supported Python version installed and accessible at `python` in a terminal at the root of the project.

1. (Recommended) Create a virtual environment:
    - A virtual environment ensures dependencies are not installed system-wide which might cause issues. 
    - Follow the instructions in the [Python docs](https://docs.python.org/3/library/venv.html) for your system/shell.
    - Activate the virtual environment, then proceed with the next steps.
2. Install via `python -m pip install discord-rss`.
3. Verify your installation via `python -m discord_rss --help`. You should see some helpful text.

## Updating PyPi package
This makes the same assumptions about `python` being available in your terminal as in the previous section.

You must have a PyPi account with publishing rights (obviously).

```
python -m pip install --upgrade build
python -m pip install --upgrade twine
python -m build
python -m twine upload dist/*
```