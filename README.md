# MPATW Wiki

Unofficial fan wiki for the **18+ version** of the Roblox game **Meet People Across The World**.

**Read the wiki:** https://imp4ncake.github.io/mpatw-wiki/

> This is a fan project. It is not affiliated with, endorsed by or connected to Roblox Corporation or Nogo.

## Contributing

Anyone with a GitHub account can help. The easiest way is to click the edit button on any wiki page. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules.

## How the site works

The wiki is built with [Zensical](https://zensical.org) and hosted for free on GitHub Pages.

| Path | What it is |
|---|---|
| `docs/` | The wiki pages, in 10 category folders, written in Markdown |
| `docs/assets/stylesheets/game.css` | The game-style look (colors, fonts, buttons, menu tiles) |
| `docs/assets/javascripts/game.js` | Animated counters and countdowns |
| `scripts/update_data.py` | Downloads live stats, badges and gamepasses from the Roblox APIs |
| `data/` | Saved game data and the daily history used for the stats chart |
| `includes/` | Snippets included in pages (`includes/generated/` is written by the script) |
| `docs/assets/images/` | Screenshots and images |
| `zensical.toml` | Site settings and the navigation menu |
| `templates/` | Starting points for new pages (page, badge, item, event) |
| `requirements.txt` | The pinned Zensical version |
| `.github/workflows/docs.yml` | Builds and publishes the site on every push to `main` and every hour |

### Preview on your computer (optional)

You need Python 3 installed.

```bash
pip install -r requirements.txt
zensical serve
```

Then open http://localhost:8000 in your browser. The preview reloads automatically when you save a file.

### Live game data

Every hour GitHub Actions runs `scripts/update_data.py`, which reads the official Roblox APIs for the 18+ version (no login needed) and regenerates stats, badges, titles, tag effects, gamepasses and the update history, then republishes the site. It also builds the category cards, the home page menu, Missing Pages and Recent Changes from the nav in `zensical.toml`. Once a day it also saves a data point in `data/history.json`, which feeds the "Visits per day" chart.

#### Official updates from Discord

The **Update History** page shows the announcements of the game's official Discord updates channel. That channel is *followed* into a channel of the wiki's own Discord server, where a read-only bot reads the announcements. The script saves them in `data/discord-updates.json` and copies their images into `docs/assets/updates/` (Discord image links expire).

It needs two repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DISCORD_BOT_TOKEN` | The bot's token (Discord Developer Portal → Bot → Reset Token). Turn on **Message Content Intent** |
| `DISCORD_CHANNEL_ID` | The ID of the channel in your server that follows the updates channel |

Without them the page simply keeps what is already saved.

To run it yourself: `python scripts/update_data.py` (or `--offline` to only regenerate the pages from the saved data).

### Updating Zensical

Zensical is still in early development (0.x versions), so the version is pinned in `requirements.txt`. To upgrade, change the version there, run `zensical build` locally to check that nothing breaks, then push.

## License

- Wiki text: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- Site code and configuration: Apache License 2.0 (see [LICENSE](LICENSE))
