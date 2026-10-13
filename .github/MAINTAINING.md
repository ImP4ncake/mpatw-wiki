# How the site is built

The wiki is built with [Zensical](https://zensical.org) and hosted for free on GitHub Pages.

| Path | What it is |
|---|---|
| `docs/` | The wiki pages, in 10 category folders, written in Markdown |
| `docs/assets/stylesheets/game.css` | The game-style look (colors, fonts, buttons, menu tiles) |
| `docs/assets/javascripts/game.js` | Animated counters and countdowns |
| `scripts/update_data.py` | Downloads live stats, badges and gamepasses from the Roblox APIs |
| `data/` | Saved game data, the daily history used for the stats chart, the rules, the titles and the game updates |
| `includes/` | Snippets included in pages (`includes/generated/` is written by the script) |
| `docs/assets/images/` | Screenshots and images |
| `docs/assets/rules/` | Example pictures for the Rules page |
| `zensical.toml` | Site settings and the navigation menu |
| `overrides/partials/copyright.html` | The footer of every page: the wiki's name and the disclaimer |
| `templates/` | Starting points for new pages (page, badge, item, event) |
| `requirements.txt` | The pinned Zensical version |
| `.github/workflows/docs.yml` | Builds and publishes the site on every push to `main` and every hour |
| `.github/readme/` | The pictures shown in the README |

## Who can change the site

Only people with write access to this repository can change what is published, and the publishing workflow never runs for pull requests. The wiki doesn't take outside pull requests: readers send suggestions to ImP4ncake on Discord (`imp4ncake`), as the Suggest a Change page (`docs/wiki/suggest.md`) explains, and every "Needs info" box links there.

## Changing the look

The look lives in `docs/assets/stylesheets/game.css` and the small animations in `docs/assets/javascripts/game.js`. GitHub Pages lets browsers keep these files for up to 10 minutes, so after editing either one, change the `?v=` number next to it in `zensical.toml` (for example `?v=20261012-2` to `?v=20261013-1`). Browsers then load the new version as soon as the site is published.

## Preview on your computer (optional)

You need Python 3 installed.

```bash
pip install -r requirements.txt
zensical serve
```

Then open http://localhost:8000 in your browser. The preview reloads automatically when you save a file.

## Live game data

Every hour GitHub Actions runs `scripts/update_data.py`, which reads the official Roblox APIs for the 18+ version (no login needed) and regenerates stats, badges, titles, tag effects, gamepasses and the update history, then republishes the site. It also builds the category cards, the home page menu and Recent Changes from the nav in `zensical.toml`. Once a day it also saves a data point in `data/history.json`, which feeds the "Visits per day" chart.

### Official updates from Discord

The **Update History** page shows the announcements of the game's official Discord updates channel. That channel is *followed* into a channel of the wiki's own Discord server, where a read-only bot reads the announcements. Only messages that arrived through the follow are published, so anything else posted in that channel never reaches the wiki. The script saves them in `data/discord-updates.json` and copies their images into `docs/assets/updates/` (Discord image links expire).

It needs two repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DISCORD_BOT_TOKEN` | The bot's token (Discord Developer Portal → Bot → Reset Token). Turn on **Message Content Intent** |
| `DISCORD_CHANNEL_ID` | The ID of the channel in your server that follows the updates channel |

Without them the page simply keeps what is already saved.

Until the bot is set up, updates can be added by hand: put a new entry at the top of `data/discord-updates.json` (the title on the first line as `## October 11 (57.12)`, then one `- ` line per change). The three newest also appear in **Latest Updates** on the home page, with their first change.

To run it yourself: `python scripts/update_data.py` (or `--offline` to only regenerate the pages from the saved data).

## The Titles page

Badge titles come from the badges' descriptions automatically. What the game's title list (in the **CUSTOMIZE** menu) shows is saved by hand in `data/titles.json`: each title's color, the "Nx Exist" number and the day it was checked (`checked`). A dark title with a colored outline has an `edge` color, and a title in more than one color has a `gradient`. The VIP titles and their price are under `vip`. A title that no badge gives and that isn't VIP shows up under **Other titles**, in the group named by its `group` (with `how`, how to get it), or under **Not known yet** with a Needs info box. **All titles** lists every title once, in the game's order, and the title count on Badges & Titles counts them all.

To update the numbers, change `exist` (and `checked`) and push.

## The Rules page

The Rules page is built from `data/rules.json` (copied from the official *Detailed Ban Info* posts on the community Discord). Every rule can have `explain` paragraphs and `bannable`, `ok` and `never` example lists. Each example has a title (`t`), an optional note (`d`) and optional pictures (`img`):

```json
{"t": "Wearing a bikini without suggestive intent", "d": "Wearing a Bikini on its own is not bannable.",
 "img": [{"src": "a4-ok-bikini.webp", "alt": "A player wearing a bikini in a normal way"}]}
```

Words in quotes after *say*, *tell*, *ask*, *call*, *post*, *type* or *write* (in the same sentence) are shown as in-game chat bubbles, so write what a player says between "double quotes". A ban code in bold, like `**b8**`, becomes a link that opens that rule, and `section **d**` opens that chapter. Game words listed in `RULE_LINKS` in `scripts/update_data.py` (Draw Area, Lottery, Admin Panel…) link to their wiki page the first time they appear in a rule.

On other pages, link a ban code to its rule with `[c6](../community/rules.md#c6){ .mp-rule }`: it shows as a small chip that opens the rule.

Pictures go in `docs/assets/rules/`. Add `"spoiler": true` to show a picture blurred until it is clicked (used for every bannable example). Hide player names in screenshots before adding them. After editing, run `python scripts/update_data.py --offline` or just push: the hourly run rebuilds the page.

Discord image links stop working about a day after they are copied, and they can't be downloaded from everywhere. The **Fetch images** workflow (Actions → Fetch images → Run workflow) downloads them on GitHub and keeps them for 3 days as a download on the run page. Run it with `clean` as the links to remove the temporary `fetched-images` branch it can create.

## Updating Zensical

Zensical is still in early development (0.x versions), so the version is pinned in `requirements.txt`. To upgrade, change the version there, run `zensical build` locally to check that nothing breaks, then push.
