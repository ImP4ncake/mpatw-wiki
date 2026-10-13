#!/usr/bin/env python3
"""Keep the wiki up to date.

1. Fetches public data about the 18+ version of Meet People Across The World
   from the official Roblox web APIs (no login needed).
2. Regenerates the snippets that the wiki pages include, in includes/generated/:
   stats, badges, titles, tag effects, gamepasses, limited rewards, update
   history, category cards and recent changes.

    data/game.json             latest snapshot of everything fetched from Roblox
    data/history.json          one data point per day (stats chart, update history)
    data/discord-updates.json  archive of the official update announcements

Official updates come from the game's Discord updates channel. That channel is
followed into a channel of the wiki's own Discord server, where a read-only
bot reads them. Set two GitHub secrets to switch this on:

    DISCORD_BOT_TOKEN   the bot's token
    DISCORD_CHANNEL_ID  the ID of the channel that follows the updates channel

Run it with:

    python scripts/update_data.py            # fetch fresh data, then generate
    python scripts/update_data.py --offline  # only regenerate from saved data

The script never fails the build: if Roblox can't be reached, it keeps the
last saved snapshot and regenerates the pages from that.

To change how a badge or gamepass is described, edit BADGE_INFO or PASS_INFO
below. New badges and gamepasses appear on the wiki automatically. Category
cards and the home page menu are built from the nav in
zensical.toml and from each page's front matter (icon and description).
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import posixpath
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# The 18+ version of the game
UNIVERSE_ID = 6690355795
PLACE_ID = 110570058234582
CREATOR_USER_ID = 149639411  # Nogo's Roblox profile
CREATOR_GROUP_ID = 3394697  # the Nogo group

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA_DIR = ROOT / "data"
GEN_DIR = ROOT / "includes" / "generated"
SNAPSHOT = DATA_DIR / "game.json"
HISTORY = DATA_DIR / "history.json"
DISCORD_ARCHIVE = DATA_DIR / "discord-updates.json"
EVENTS_FILE = DATA_DIR / "events.json"
TITLES_FILE = DATA_DIR / "titles.json"
GALLERY_ROOT = DOCS / "assets" / "events"
IMAGE_FILES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
UPDATE_ASSETS = DOCS / "assets" / "updates"
DISCORD_API = "https://discord.com/api/v10"
DISCORD_UA = "DiscordBot (https://github.com/ImP4ncake/mpatw-wiki, 1.0)"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
REPO_URL = "https://github.com/ImP4ncake/mpatw-wiki"

USER_AGENT = "MPATW-Wiki-Updater/2.0 (+https://github.com/ImP4ncake/mpatw-wiki)"

# --------------------------------------------------------------------------
# Hand-written info. Anything not listed here still shows up automatically,
# using the official description from Roblox.
# --------------------------------------------------------------------------

# Badge groups: (page, heading). Pages are badges/regular.md, badges/limited.md
# and badges/special.md.
GROUPS = {
    "start": ("regular", "Getting started"),
    "rep": ("regular", "Reputation"),
    "arena": ("regular", "Combat arenas"),
    "act": ("regular", "Activities"),
    "special": ("special", "Rare and prestige"),
    "limited": ("limited", "Limited (events)"),
    "new": ("regular", "New badges"),
    "gone": ("special", "No longer available"),
}

# name -> (group, how to get it)
BADGE_INFO = {
    "Welcome to Meet People Across The World!": ("start", "Join the game for the first time"),
    "Invite a Friend!": ("start", "Invite a friend to the game"),
    "Played in VR": ("start", "Join the game in VR"),
    "Pet The Cat": ("start", "Pet the cat"),
    "Pet The Dog": ("start", "Pet the dog"),
    "Pianist": ("start", "Play the piano"),
    "Coder": ("start", "Redeem a code from the community server"),
    "Gifter": ("start", "Gift anyone"),
    "Famous": ("rep", "Reach 10,000 reputation"),
    "Infamous": ("rep", "Reach -10,000 reputation"),
    "Swordmaster": ("arena", "Defeat 50 players in the Sword Arena"),
    "Gunsmith": ("arena", "Defeat 50 players in the Gun Arena"),
    "Boxer": ("arena", "Defeat 50 players in the Boxing Arena"),
    "Sniper": ("arena", "Defeat 50 players in the Sniper Arena"),
    "Arsonist": ("arena", "Defeat 50 players in the Bomb Arena"),
    "Warrior": ("arena", "Defeat 50 players in the Greatsword Arena"),
    "Artist": ("act", "Draw 1,000 times in the Draw Area"),
    "Drink Maker": ("act", "Serve 50 drinks at the Drink Area"),
    "Troller": ("act", "Troll other players 50 times"),
    "Robot": ("act", "Talk to the AI Chatbot 50 times"),
    "Builder": ("act", "Build 10 blocks with the Hammer"),
    "Grandmaster": ("act", "Win 25 chess games"),
    "Wayfarer": ("act", "Reach a 50 streak in Country Trivia"),
    "Win the Lottery": ("act", "Roll 777 on the Lottery"),
    "AFK": ("act", "Earn 1,000 coins in the AFK World"),
    "Rainmaker": ("act", "Make it rain any currency"),
    "Fabled": ("act", "Unlock a cosmetic with Fabled rarity"),
    "Explorer": ("special", "Discover all 250 countries"),
    "Angel": ("special", "Be #1 on a non-timed leaderboard"),
    "Fallen Angel": ("special", "Lose #1 on a non-timed leaderboard while it updates in-game"),
    "Sovereign": ("special", "Finish #1 at the end of a Ranked Season"),
    "Winner": ("special", "Win a community server event"),
    "Honored": ("special", "Become a moderator for the game"),
    "[LIMITED] Claim The Christmas Gift": ("limited", "Give a gift during the Christmas event"),
    "[LIMITED] Loved": ("limited", "Buy or receive the Valentine's Pack"),
    "[LIMITED] Blessed": ("limited", "Roll 7777 on the Saint Patrick's Lottery"),
    "[LIMITED] Win The Lottery?": ("limited", "April Fools' joke badge"),
    "[LIMITED] Easter Collector": ("limited", "Find all 50 Easter Eggs"),
    "[LIMITED] Trick or Treat!": ("limited", "Win a special treat at the Spooky Shed"),
    "[LIMITED] WC2026": ("limited", "Guess a winning team in the 2026 World Cup"),
}

# name -> short description
PASS_INFO = {
    "Tip Jar": "Lets other players donate to you in-game",
    "Coil Pack": "Speed Coil, Gravity Coil and Fusion Coil together",
    "Drink Maker": "Lets you make drinks",
    "Better Customization": "Unlocks extra customization options",
    "[Non-Lethal] Weapons Pack": "Seven cosmetic weapons that cannot defeat players",
    "Size Changer": "Makes your character anywhere from tiny to large",
    "Invisibility": "Makes you invisible",
    "Grab a Friend": "Lets you carry or lasso other players, if they agree",
    "Spectate": "Lets you watch other players",
    "Fly": "Lets you fly",
    "Triple Coins": "Triples the coins you earn from most sources",
    "[LIMITED] Valentine's Pack": "Seasonal emote, balloon, title and effect",
    "Custom Country": "Lets you set any country as your origin",
    "Voice Changers": "Several in-game voice effects",
    "Phone": "A cosmetic phone",
    "Non-Lethal Knife": "A cosmetic knife that cannot defeat players",
    "Non-Lethal Shotgun": "A cosmetic shotgun that cannot defeat players",
    "Speed Coil": "Boosts your movement speed",
    "Gravity Coil": "Boosts your jump height",
    "Fusion Coil": "Boosts your speed and jump height",
    "Gamepass Info [READ DESC]": "Not a real pass: a notice saying gamepasses are linked to the standard version",
}

RARITY_TIERS = [
    (25.0, "Common", "common"),
    (2.0, "Uncommon", "uncommon"),
    (0.2, "Rare", "rare"),
    (0.01, "Epic", "epic"),
    (0.0, "Legendary", "legendary"),
]

# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def get_json(url: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - any failure means "retry"
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last_error}")


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_icons(kind: str, ids: list[int]) -> dict[int, str]:
    """kind is 'badges' or 'game-passes'."""
    icons: dict[int, str] = {}
    for group in chunks(ids, 50):
        joined = ",".join(str(i) for i in group)
        if kind == "badges":
            url = f"https://thumbnails.roblox.com/v1/badges/icons?badgeIds={joined}&size=150x150&format=Png&isCircular=false"
        else:
            url = f"https://thumbnails.roblox.com/v1/game-passes?gamePassIds={joined}&size=150x150&format=Png&isCircular=false"
        for item in get_json(url).get("data", []):
            if item.get("state") == "Completed" and item.get("imageUrl"):
                icons[int(item["targetId"])] = item["imageUrl"]
    return icons


def fetch_game() -> dict:
    data = get_json(f"https://games.roblox.com/v1/games?universeIds={UNIVERSE_ID}")["data"][0]
    return {
        "name": data.get("name"),
        "playing": data.get("playing"),
        "visits": data.get("visits"),
        "favorites": data.get("favoritedCount"),
        "max_players": data.get("maxPlayers"),
        "created": data.get("created"),
        "updated": data.get("updated"),
        "creator": (data.get("creator") or {}).get("name"),
    }


def fetch_votes() -> dict:
    data = get_json(f"https://games.roblox.com/v1/games/votes?universeIds={UNIVERSE_ID}")["data"][0]
    return {"up": data.get("upVotes"), "down": data.get("downVotes")}


def fetch_badges() -> list[dict]:
    badges, cursor = [], ""
    while True:
        url = f"https://badges.roblox.com/v1/universes/{UNIVERSE_ID}/badges?limit=100&sortOrder=Asc"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        page = get_json(url)
        for b in page.get("data", []):
            stats = b.get("statistics") or {}
            badges.append(
                {
                    "id": b["id"],
                    "name": b.get("displayName") or b.get("name"),
                    "description": b.get("displayDescription") or b.get("description") or "",
                    "enabled": bool(b.get("enabled", True)),
                    "created": b.get("created"),
                    "awarded": stats.get("awardedCount"),
                    "awarded_day": stats.get("pastDayAwardedCount"),
                    "icon": None,
                }
            )
        cursor = page.get("nextPageCursor")
        if not cursor:
            break
    try:
        icons = fetch_icons("badges", [b["id"] for b in badges])
        for b in badges:
            b["icon"] = icons.get(int(b["id"]))
    except RuntimeError as exc:
        print(f"warning: badge icons not updated ({exc})")
    return badges


def fetch_passes() -> list[dict]:
    passes, token = [], ""
    while True:
        url = f"https://apis.roblox.com/game-passes/v1/universes/{UNIVERSE_ID}/game-passes?pageSize=100&passView=Full"
        if token:
            url += "&pageToken=" + urllib.parse.quote(token)
        page = get_json(url)
        for p in page.get("gamePasses", []):
            passes.append(
                {
                    "id": p["id"],
                    "name": p.get("displayName") or p.get("name"),
                    "description": p.get("displayDescription") or p.get("description") or "",
                    "price": p.get("price"),
                    "for_sale": bool(p.get("isForSale")),
                    "icon": None,
                }
            )
        token = page.get("nextPageToken")
        if not token:
            break
    try:
        icons = fetch_icons("game-passes", [p["id"] for p in passes])
        for p in passes:
            p["icon"] = icons.get(int(p["id"]))
    except RuntimeError as exc:
        print(f"warning: gamepass icons not updated ({exc})")
    return passes


def list_games(base_url: str) -> list[dict]:
    games, cursor = [], ""
    while True:
        url = base_url + ("&cursor=" + urllib.parse.quote(cursor) if cursor else "")
        page = get_json(url)
        games += page.get("data", [])
        cursor = page.get("nextPageCursor")
        if not cursor:
            return games


def fetch_creator_games() -> list[dict]:
    """Every public game connected to Nogo's profile: the games of the
    account itself and of every group the account owns."""
    owners = [("user", CREATOR_USER_ID, "Nogo's account")]
    roles = get_json(f"https://groups.roblox.com/v1/users/{CREATOR_USER_ID}/groups/roles").get("data", [])
    for r in roles:
        group = r.get("group") or {}
        if (r.get("role") or {}).get("rank") == 255 and group.get("id"):
            owners.append(("group", group["id"], f"{group.get('name') or 'Group'} group"))
    found: dict[int, dict] = {}
    for kind, owner_id, owner_name in owners:
        if kind == "user":
            base = f"https://games.roblox.com/v2/users/{owner_id}/games?accessFilter=Public&limit=50&sortOrder=Asc"
        else:
            base = f"https://games.roblox.com/v2/groups/{owner_id}/gamesV2?accessFilter=Public&limit=50&sortOrder=Asc"
        for g in list_games(base):
            found[g["id"]] = {
                "id": g["id"],
                "name": g.get("name"),
                "created": g.get("created"),
                "visits": g.get("placeVisits"),
                "place_id": (g.get("rootPlace") or {}).get("id"),
                "owner": owner_name,
                "owner_kind": kind,
                "owner_id": owner_id,
                "icon": None,
            }
    try:
        for group in chunks(list(found), 50):
            joined = ",".join(str(i) for i in group)
            url = (f"https://thumbnails.roblox.com/v1/games/icons?universeIds={joined}"
                   "&returnPolicy=PlaceHolder&size=150x150&format=Png&isCircular=false")
            for item in get_json(url).get("data", []):
                if item.get("state") == "Completed" and item.get("imageUrl") and int(item["targetId"]) in found:
                    found[int(item["targetId"])]["icon"] = item["imageUrl"]
    except RuntimeError as exc:
        print(f"warning: game icons not updated ({exc})")
    games = sorted(found.values(), key=lambda g: g.get("created") or "")
    for g in games:  # shown in the workflow log, to check the list
        print(f"  creator game: {g.get('created', '?')[:10]} | {g['name']} | {g.get('visits')} visits | {g['owner']}")
    return games


def update_snapshot(offline: bool) -> tuple[dict, bool]:
    """Returns (snapshot, game_fetched)."""
    snap = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else {}
    if offline:
        return snap, False
    if snap.get("universe_id") not in (None, UNIVERSE_ID):
        snap = {}  # saved data belongs to another version of the game
    snap["universe_id"] = UNIVERSE_ID

    fetched_game = False
    fetchers = (
        ("game", fetch_game),
        ("votes", fetch_votes),
        ("badges", fetch_badges),
        ("passes", fetch_passes),
        ("creator_games", fetch_creator_games),
    )
    for key, fetcher in fetchers:
        try:
            value = fetcher()
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not fetch {key}, keeping the last saved data ({exc})")
            continue
        if key == "creator_games" and not value:
            print("warning: no creator games found, keeping the last saved list")
            continue
        if key in ("badges", "passes", "creator_games"):  # keep known icons if the icon service failed
            old_icons = {x.get("name"): x.get("icon") for x in snap.get(key, [])}
            for item in value:
                item["icon"] = item["icon"] or old_icons.get(item.get("name"))
        snap[key] = value
        print(f"fetched {key}")
        if key == "game":
            fetched_game = True
    if fetched_game:
        snap["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        snap.pop("seed", None)
    return snap, fetched_game


def update_history(snap: dict, game_fetched: bool) -> bool:
    """Adds one point per UTC day. Returns True when a new day was added."""
    history = json.loads(HISTORY.read_text("utf-8")) if HISTORY.exists() else []
    if not game_fetched:
        return False
    today = snap["fetched_at"][:10]
    if any(p["date"] == today for p in history):
        return False
    game, votes = snap.get("game", {}), snap.get("votes", {})
    history.append(
        {
            "date": today,
            "visits": game.get("visits"),
            "favorites": game.get("favorites"),
            "playing": game.get("playing"),
            "up": votes.get("up"),
            "down": votes.get("down"),
            "updated": game.get("updated"),
        }
    )
    history.sort(key=lambda p: p["date"])
    HISTORY.write_text(json.dumps(history, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return True


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def full(n) -> str:
    return f"{n:,}" if isinstance(n, (int, float)) else "?"


def compact(n) -> str:
    if not isinstance(n, (int, float)):
        return "?"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= limit:
            return (f"{n / limit:.1f}".rstrip("0").rstrip(".")) + suffix
    return str(int(n))


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def nice_date(value: str | None, with_time: bool = False) -> str:
    t = parse_time(value)
    if not t:
        return "?"
    t = t.astimezone(dt.timezone.utc)
    text = f"{t.day} {t.strftime('%b %Y')}"
    return text + (t.strftime(", %H:%M UTC") if with_time else "")


def time_tag(value: str | None, with_time: bool = True) -> str:
    if not value:
        return "?"
    return f'<time datetime="{esc(value)}" data-time="{esc(value)}">{esc(nice_date(value, with_time))}</time>'


def rating(votes: dict) -> float | None:
    up, down = votes.get("up"), votes.get("down")
    if isinstance(up, int) and isinstance(down, int) and up + down:
        return up / (up + down) * 100
    return None


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line.rstrip("!.")
    return ""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def lucide(name: str) -> str:
    """Inline SVG of a Lucide icon, taken from the installed Zensical theme."""
    try:
        import zensical  # noqa: PLC0415

        path = Path(zensical.__file__).parent / "templates" / ".icons" / "lucide" / f"{name}.svg"
        return path.read_text("utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def page_url(page: str) -> str:
    """docs-relative .md path -> site URL path ('' for the home page)."""
    p = page[:-3]
    if p == "index":
        return ""
    if p.endswith("/index"):
        return p[: -len("index")]
    return p + "/"


def rel(from_page: str, to_page: str, anchor: str = "") -> str:
    """Relative link from one page to another, for HTML written into a page.

    Zensical treats relative URLs in a page as relative to the page's source
    file and adjusts them for the published site, so links are computed from
    the source file's folder to the target page's published folder."""
    start = posixpath.dirname(from_page) or "."
    target = page_url(to_page) or "."
    r = posixpath.relpath(target, start)
    return ("./" if r == "." else r + "/") + (f"#{anchor}" if anchor else "")


def write(name: str, content: str) -> None:
    path = GEN_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", "utf-8")


def icon_img(url: str | None, alt: str, cls: str = "mp-thumb") -> str:
    if url:
        return f'<img class="{cls}" src="{esc(url)}" alt="{esc(alt)}" width="64" height="64" loading="lazy">'
    return f'<span class="{cls} mp-thumb--empty" aria-hidden="true"></span>'


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------


def badge_reward(description: str, in_game: dict | None = None) -> dict:
    """Reads 'Grants access to the "X" Title + "🍀" Tag effect' style text."""
    reward = {"titles": [], "tag": None, "coins": None}
    for line in description.splitlines():
        # Only the reward lines ("Grants access to ...", "Unlocks ..."), not
        # requirement lines like "Earn 1000 Coins in the AFK World".
        if not re.search(r"grant|unlock|title|effect", line, re.I):
            continue
        tag = re.search(r'"([^"]+)"\s*(?:Tag|Effect)', line, re.I)
        quoted = re.findall(r'"([^"]+)"', line)
        if "title" in line.lower():
            reward["titles"] += [q for q in quoted if not tag or q != tag.group(1)]
        if tag:
            reward["tag"] = tag.group(1)
        coins = re.search(r"(\d[\d,]*)\s*Coins", line, re.I)
        if coins:
            reward["coins"] = coins.group(1)
    reward["titles"] = [(in_game or {}).get(t, t) for t in reward["titles"]]
    return reward


def rarity_of(awarded, base) -> tuple[str, str, str]:
    """(label, css, percent text)"""
    if not isinstance(awarded, int) or not isinstance(base, int) or base <= 0:
        return ("", "", "")
    share = awarded / base * 100
    for limit, label, css in RARITY_TIERS:
        if share >= limit:
            pct = f"{share:.2f}%" if share >= 0.01 else "less than 0.01%"
            return (label, css, pct)
    return ("", "", "")


def rarity_chip(b: dict) -> str:
    label, css, pct = b["rarity"]
    if not label:
        return ""
    return f'<span class="mp-rarity mp-rarity--{css}" title="Owned by {pct} of players who joined">{label}</span>'


def load_titles() -> dict:
    """The game's title list (colors, how many exist, VIP titles), from data/titles.json."""
    if not TITLES_FILE.exists():
        return {"titles": [], "vip": None}
    return json.loads(TITLES_FILE.read_text("utf-8"))


def prepare_badges(snap: dict) -> list[dict]:
    badges = snap.get("badges", [])
    # a badge description can name a title differently from the game ("Fool" is "The Fool")
    in_game = {t["badge_title"]: t["name"] for t in load_titles()["titles"] if t.get("badge_title")}
    base = next((b.get("awarded") for b in badges if b["name"].startswith("Welcome")), None)
    if not isinstance(base, int):
        base = max((b.get("awarded") or 0 for b in badges), default=0)
    out = []
    for b in badges:
        group, how = BADGE_INFO.get(b["name"], (None, None))
        if not b["enabled"]:
            group = "gone"
        elif group is None:
            group = "limited" if b["name"].startswith("[LIMITED]") else "new"
        page, heading = GROUPS[group]
        out.append(
            {
                **b,
                "group": group,
                "page": f"badges/{page}.md",
                "heading": heading,
                "how": how or first_line(b["description"]) or "?",
                "reward": badge_reward(b["description"], in_game),
                "rarity": rarity_of(b.get("awarded"), base),
                "anchor": "badge-" + slug(b["name"]),
                "short": re.sub(r"^\[LIMITED\]\s*", "", b["name"]),
            }
        )
    return out


def reward_chips(r: dict) -> str:
    parts = [f'<span class="mp-chip mp-chip--title">{esc(t)}</span>' for t in r["titles"]]
    if r["tag"]:
        parts.append(f'<span class="mp-chip mp-chip--tag" title="Tag effect">{esc(r["tag"])}</span>')
    if r["coins"]:
        parts.append(f'<span class="mp-chip mp-chip--coins">+{esc(r["coins"])} coins</span>')
    return "".join(parts) or '<span class="mp-chip mp-chip--none">No reward</span>'


def badge_card(b: dict, with_id: bool = True) -> str:
    ident = f' id="{b["anchor"]}"' if with_id else ""
    css = b["rarity"][1] or "common"
    name = esc(b["short"])
    link = f"https://www.roblox.com/badges/{b['id']}" if b.get("id") else None
    title = f'<a class="mp-badge__name" href="{esc(link)}" target="_blank" rel="noopener">{name}</a>' if link else f'<span class="mp-badge__name">{name}</span>'
    limited = '<span class="mp-limited mp-limited--small">LIMITED</span>' if b["name"].startswith("[LIMITED]") else ""
    return (
        f'<div class="mp-badge mp-badge--{css}"{ident}>'
        f"{icon_img(b.get('icon'), b['short'])}"
        f'<div class="mp-badge__body">{limited}{title}'
        f'<span class="mp-badge__how">{esc(b["how"])}</span>'
        f'<span class="mp-badge__reward">{reward_chips(b["reward"])}</span></div>'
        f'<div class="mp-badge__meta">{rarity_chip(b)}'
        f'<span class="mp-badge__owners" title="{full(b.get("awarded"))} players own it">'
        f'{compact(b.get("awarded"))} owners</span></div></div>'
    )


def gen_badges(snap: dict, badges: list[dict]) -> None:
    updated = time_tag(snap.get("fetched_at"))
    for page in ("regular", "limited", "special"):
        items = [b for b in badges if b["page"] == f"badges/{page}.md"]
        out = [f'<p class="mp-lead"><b>{len(items)}</b> badges on this page. Live data, updated {updated}.</p>', ""]
        headings = []
        for b in items:
            if b["heading"] not in headings:
                headings.append(b["heading"])
        for heading in headings:
            group = [b for b in items if b["heading"] == heading]
            if len(headings) > 1:
                out += [f"## {heading}", ""]
            out.append('<div class="mp-badges">' + "".join(badge_card(b) for b in group) + "</div>")
            out.append("")
        write(f"badges-{page}.md", "\n".join(out))

    # One card per badge, for activity and event pages
    for b in badges:
        write(f"badge/{slug(b['name'])}.md", '<div class="mp-badges mp-badges--single">' + badge_card(b, with_id=False) + "</div>")

    # Summary for the category page
    enabled = [b for b in badges if b["enabled"]]
    limited = sum(1 for b in enabled if b["group"] == "limited")
    titles = sum(len(b["reward"]["titles"]) for b in enabled)
    tags = sum(1 for b in enabled if b["reward"]["tag"])
    stats = [
        ("award", "gold", len(enabled), "badges"),
        ("hourglass", "orange", limited, "limited badges"),
        ("tag", "violet", titles, "titles"),
        ("sparkles", "pink", tags, "tag effects"),
    ]
    out = ['<div class="mp-stats mp-stats--grid">']
    for icon, color, value, label in stats:
        out.append(
            f'<div class="mp-stat mp-stat--{color}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
            f'<span class="mp-stat__value" data-count="{value}">{value}</span><span class="mp-stat__label">{label}</span></div>'
        )
    out.append("</div>")
    write("badges-summary.md", "\n".join(out))


def title_name(name: str, info: dict | None, cls: str = "mp-title-card__title") -> str:
    """A title in its color from the game (the rarity color when the game's isn't known)."""
    style, extra = "", ""
    if info and info.get("color"):
        style = f"--tc:{info['color']}"
        if info.get("edge"):
            style += f";--tg:{info['edge']}"
            cls += " is-edge"
        if info.get("gradient"):
            style += f";--tgrad:linear-gradient(90deg,{','.join(info['gradient'])})"
            cls += " is-gradient"
            extra = f' data-text="{esc(name)}"'
        style = f' style="{esc(style)}"'
    return f'<span class="{cls}"{style}{extra}>{esc(name)}</span>'


def title_exist(info: dict | None, checked: str, cls: str = "mp-title-card__exist") -> str:
    if not info or not isinstance(info.get("exist"), int):
        return ""
    when = nice_date(checked + "T00:00:00Z") if checked else ""
    tip = f"The game's title list on {when}" if when else "The game's title list"
    return f'<span class="{cls}" title="{esc(tip)}">{full(info["exist"])} exist</span>'


def gen_titles(badges: list[dict]) -> None:
    here = "badges/titles.md"
    data = load_titles()
    checked = data.get("checked", "")
    info = {t["name"]: t for t in data["titles"]}
    rows = []
    for b in badges:
        for t in b["reward"]["titles"]:
            rows.append((t, b))
    out = [f'<p class="mp-lead"><b>{len(rows)}</b> titles you can unlock with badges. Click a title to see its badge.</p>', ""]
    out.append('<div class="mp-titles">')
    for t, b in rows:
        css = b["rarity"][1] or "common"
        out.append(
            f'<a class="mp-title-card mp-title-card--{css}" href="{rel(here, b["page"], b["anchor"])}">'
            f'{title_name(t, info.get(t))}'
            f'<span class="mp-title-card__tag">{esc(b["reward"]["tag"] or "")}</span>'
            f'<span class="mp-title-card__from">{esc(b["short"])}</span>{title_exist(info.get(t), checked)}{rarity_chip(b)}</a>'
        )
    out.append("</div>")
    write("titles.md", "\n".join(out))

    # VIP titles
    vip = data.get("vip") or {}
    vip_titles = vip.get("titles", [])
    out = []
    if vip_titles:
        price = full(vip.get("price")) if vip.get("price") else "?"
        plates = "".join(
            f'<span class="mp-plate">{title_name(t, {"color": vip.get("color")}, "mp-plate__name")}</span>' for t in vip_titles
        )
        out = [
            '<div class="mp-vip">',
            '<div class="mp-vip__head">',
            f'<span class="mp-vip__crown" aria-hidden="true">{lucide("crown")}</span>',
            '<div class="mp-vip__about"><b class="mp-vip__name">VIP subscription</b>'
            f'<span class="mp-vip__price"><span class="mp-price"><span class="mp-robux" aria-hidden="true"></span>{price}</span>'
            f' every {esc(vip.get("every", "month"))}</span></div>',
            f'<span class="mp-vip__count"><b>{len(vip_titles)}</b> titles</span>',
            "</div>",
            f'<div class="mp-plates">{plates}</div>',
            "</div>",
        ]
    write("titles-vip.md", "\n".join(out))

    # Titles the game lists that no badge gives and VIP doesn't either
    known = {t for t, _ in rows} | set(vip_titles)
    others = [t for t in data["titles"] if t["name"] not in known]
    out = []
    if others:
        out += [
            "## Other titles",
            "",
            f'<p>The game also has <b>{len(others)}</b> title{"s" if len(others) != 1 else ""} that no badge gives and that '
            "don't come with VIP. How to get them isn't known yet.</p>",
            "",
            '<div class="mp-plates mp-plates--list">',
        ]
        for t in others:
            out.append(
                f'<span class="mp-plate">{title_name(t["name"], t, "mp-plate__name")}'
                f'{title_exist(t, checked, "mp-plate__exist")}</span>'
            )
        if len(others) <= 4:
            names = [f"**{t['name']}**" for t in others]
            ask = "do you get " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
        else:
            ask = "do you get these titles"
        out += [
            "</div>",
            "",
            '!!! question "Needs info"',
            "",
            f"    How {ask}? If you know, "
            "[:fontawesome-brands-discord: Tell me on Discord](../wiki/suggest.md){ .mp-suggest }",
        ]
    write("titles-other.md", "\n".join(out))

    # Count for the top of the page
    stats = [
        ("award", "gold", len(rows), "badge titles"),
        ("crown", "orange", len(vip_titles), "VIP titles"),
        ("circle-help", "violet", len(others), "other titles"),
    ]
    out = ['<div class="mp-stats mp-stats--grid mp-stats--three">']
    for icon, color, value, label in stats:
        out.append(
            f'<div class="mp-stat mp-stat--{color}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
            f'<span class="mp-stat__value" data-count="{value}">{value}</span><span class="mp-stat__label">{label}</span></div>'
        )
    out.append("</div>")
    write("titles-summary.md", "\n".join(out))

    here = "badges/tag-effects.md"
    tagged = [b for b in badges if b["reward"]["tag"]]
    out = [f'<p class="mp-lead"><b>{len(tagged)}</b> tag effects. Each one is unlocked by a badge.</p>', ""]
    out.append('<div class="mp-tags">')
    for b in tagged:
        css = b["rarity"][1] or "common"
        out.append(
            f'<a class="mp-tag-card mp-tag-card--{css}" href="{rel(here, b["page"], b["anchor"])}">'
            f'<span class="mp-tag-card__emoji">{esc(b["reward"]["tag"])}</span>'
            f'<span class="mp-tag-card__from">{esc(b["short"])}</span></a>'
        )
    out.append("</div>")
    write("tag-effects.md", "\n".join(out))


def gen_badge_hunting(badges: list[dict]) -> None:
    here = "guides/badge-hunting.md"
    items = sorted((b for b in badges if b["enabled"] and isinstance(b.get("awarded"), int)), key=lambda b: -b["awarded"])
    out = ['<ol class="mp-hunt">']
    for b in items:
        out.append(
            f'<li class="mp-hunt__row">{icon_img(b.get("icon"), b["short"], "mp-thumb mp-thumb--small")}'
            f'<span class="mp-hunt__name"><a href="{rel(here, b["page"], b["anchor"])}">{esc(b["short"])}</a>'
            f'<small>{esc(b["how"])}</small></span>{rarity_chip(b)}</li>'
        )
    out.append("</ol>")
    write("badge-hunting.md", "\n".join(out))


def gen_badge_timeline(badges: list[dict]) -> None:
    """Game History: summary tiles, then every month that added badges,
    grouped by year, with each badge as a small chip (icon, rarity color,
    link to its card on the badge pages)."""
    page = "game-info/history.md"
    months: dict[str, list[dict]] = {}
    for b in badges:
        t = parse_time(b.get("created"))
        if t:
            months.setdefault(t.strftime("%Y-%m"), []).append(b)
    if not months:
        write("badge-timeline.md", "The badge timeline appears here once the wiki has downloaded the badge data.")
        return
    keys = sorted(months)
    busiest = max(keys, key=lambda k: (len(months[k]), k))

    def month(key: str, fmt: str = "%b %Y") -> str:
        return dt.datetime.strptime(key, "%Y-%m").strftime(fmt)

    def tile(icon: str, color: str, value: str, label: str) -> str:
        return (
            f'<div class="mp-stat mp-stat--{color}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
            f'<span class="mp-stat__value">{value}</span><span class="mp-stat__label">{label}</span></div>'
        )

    out = [
        '<div class="mp-stats mp-stats--grid">',
        tile("flag", "gold", month(keys[0]), "first badge"),
        tile("sparkles", "blue", month(keys[-1]), "newest badges"),
        tile("flame", "orange", month(busiest), "record month"),
        "</div>",
        "",
        '<div class="mp-timeline mp-timeline--badges">',
    ]
    year = None
    for key in keys:
        if key[:4] != year:
            year = key[:4]
            out.append(f'<div class="mp-timeline__year">{year}</div>')
        chips = []
        for b in months[key]:
            rarity = b["rarity"][1] or "common"
            chips.append(
                f'<a class="mp-bchip mp-bchip--{rarity}" href="{rel(page, b["page"], b["anchor"])}" title="{esc(b["how"])}">'
                f'{icon_img(b.get("icon"), b["short"], "mp-thumb mp-thumb--tiny")}<span>{esc(b["short"])}</span></a>'
            )
        noun = "badge" if len(months[key]) == 1 else "badges"
        out.append(
            f'<div class="mp-timeline__item"><span class="mp-timeline__date">{month(key, "%B %Y")} · {len(months[key])} new {noun}</span>'
            f'<span class="mp-bchips">{"".join(chips)}</span></div>'
        )
    out.append("</div>")
    write("badge-timeline.md", "\n".join(out))


# --------------------------------------------------------------------------
# Gamepasses, stats, update history
# --------------------------------------------------------------------------


def pass_card(p: dict, on_sale: bool) -> str:
    desc = PASS_INFO.get(p["name"]) or first_line(p.get("description") or "") or ""
    price = (
        f'<span class="mp-price"><span class="mp-robux" aria-hidden="true"></span>{full(p["price"])}</span>'
        if on_sale
        else '<span class="mp-price mp-price--off">Off sale</span>'
    )
    inner = (
        f"{icon_img(p.get('icon'), p['name'])}"
        f'<span class="mp-pass__name">{esc(p["name"])}</span>'
        f'<span class="mp-pass__desc">{esc(desc)}</span>{price}'
    )
    if not p.get("id"):
        return f'<div class="mp-pass">{inner}</div>'
    link = f"https://www.roblox.com/game-pass/{p['id']}"
    return f'<a class="mp-pass" href="{esc(link)}" target="_blank" rel="noopener">{inner}</a>'


def gen_passes(snap: dict) -> None:
    passes = snap.get("passes", [])
    if not passes:
        write("gamepasses.md", "Gamepass data is not available yet.")
        write("limited-passes.md", "")
        return
    on_sale = sorted((p for p in passes if p["for_sale"] and isinstance(p.get("price"), int)), key=lambda p: p["price"])
    off_sale = [p for p in passes if p not in on_sale]
    out = [
        f'<p class="mp-lead"><b>{len(on_sale)}</b> gamepasses on sale and <b>{len(off_sale)}</b> off sale. '
        f'Prices updated {time_tag(snap.get("fetched_at"))}.</p>',
        "",
        "## On sale",
        "",
        '<div class="mp-passes">' + "".join(pass_card(p, True) for p in on_sale) + "</div>",
        "",
    ]
    if off_sale:
        out += [
            "## Not for sale",
            "",
            "These gamepasses exist but can't be bought right now. Some were sold in the past, during events or as part of a bundle.",
            "",
            '<div class="mp-passes mp-passes--off">' + "".join(pass_card(p, False) for p in off_sale) + "</div>",
        ]
    write("gamepasses.md", "\n".join(out))
    limited = [p for p in passes if "LIMITED" in p["name"]]
    write("limited-passes.md", '<div class="mp-passes">' + "".join(pass_card(p, p in on_sale) for p in limited) + "</div>" if limited else "")


def nogo_face(kind: str) -> str:
    """Small round picture next to a mention of Nogo: the profile picture
    for Nogo the creator, the devil for the Nogo group."""
    return f'<span class="mp-face mp-face--{kind}" aria-hidden="true"></span>'


def clean_game_name(name: str) -> tuple[str, bool]:
    """Drops event tags like "[🎃]" and the 🔊 sign, which becomes a chip.
    Returns (name, has_voice_chat)."""
    voice = "🔊" in name
    name = re.sub(r"^\s*\[[^\]A-Za-z0-9]*\]\s*", "", name).replace("🔊", "")
    return re.sub(r"\s{2,}", " ", name).strip(), voice


def game_owner(g: dict) -> str:
    kind, owner_id, owner = g.get("owner_kind"), g.get("owner_id"), g.get("owner") or ""
    if kind == "user" or owner == "Nogo's account":
        return nogo_face("nogo") + "Nogo's account"
    if owner_id == CREATOR_GROUP_ID or owner == "Nogo group":
        return nogo_face("group") + "Nogo group"
    return f'<span class="mp-face mp-face--other" aria-hidden="true">{lucide("users")}</span>{esc(owner)}'


def gen_creator_games(snap: dict) -> None:
    """Nogo's games as cards grouped by year, oldest first, with the two
    versions of Meet People Across The World highlighted."""
    games = snap.get("creator_games") or []
    if not games:
        write("nogo-games.md", "<p>The list of Nogo's games appears here after the next update from Roblox.</p>")
        return
    total = sum(g["visits"] for g in games if isinstance(g.get("visits"), int))
    first = parse_time(games[0].get("created"))
    out = [
        '<div class="mp-stats mp-stats--grid">',
        stat_pill("gamepad-2", "violet", len(games), "games", False),
        stat_pill("eye", "blue", total, "visits in total", True),
        '<div class="mp-stat mp-stat--gold"><span class="mp-stat__icon" aria-hidden="true">' + lucide("calendar") + "</span>"
        f'<span class="mp-stat__value">{first.year if first else "?"}</span><span class="mp-stat__label">first game</span></div>',
        "</div>",
        "",
        '<div class="mp-games">',
    ]
    year = None
    for g in games:
        created = parse_time(g.get("created"))
        if created and created.year != year:
            year = created.year
            out.append(f'<div class="mp-games__year">{year}</div>')
        name, voice = clean_game_name(g.get("name") or "?")
        mpatw = "meet people across the world" in name.lower()
        chips = [f'<span class="mp-game__chip">{created.strftime("%b %Y") if created else "?"}</span>']
        if voice:
            chips.append(f'<span class="mp-game__chip mp-game__chip--voice">{lucide("mic")} Voice chat</span>')
        if g.get("id") == UNIVERSE_ID:
            chips.append('<span class="mp-game__chip mp-game__chip--wiki">This wiki</span>')
        visits = f'<span class="mp-game__visits">{compact(g["visits"])} visits</span>' if isinstance(g.get("visits"), int) else ""
        inner = (
            f"{icon_img(g.get('icon'), name)}"
            f'<span class="mp-game__name">{esc(name)}</span>'
            f'<span class="mp-game__chips">{"".join(chips)}</span>'
            f'<span class="mp-game__foot"><span class="mp-game__by">{game_owner(g)}</span>{visits}</span>'
        )
        cls = "mp-game mp-game--hl" if mpatw else "mp-game"
        if g.get("place_id"):
            out.append(f'<a class="{cls}" href="https://www.roblox.com/games/{esc(g["place_id"])}" target="_blank" rel="noopener">{inner}</a>')
        else:
            out.append(f'<div class="{cls}">{inner}</div>')
    out += ["</div>", "", f'<p class="mp-updated">Updated {time_tag(snap.get("fetched_at"))} from Roblox.</p>']
    write("nogo-games.md", "\n".join(out))


def gen_pass_icons(snap: dict) -> None:
    """A style block that shows each gamepass icon in <span class="mp-icon"
    data-pass="name-in-lowercase-with-dashes">, so hand-written pages (like
    Items) can show icons that stay up to date."""
    rules = [
        f'.md-typeset .mp-icon[data-pass="{slug(p["name"])}"]{{background-image:url("{p["icon"].replace(chr(34), "%22")}")}}'
        for p in snap.get("passes", [])
        if p.get("icon")
    ]
    write("pass-icons.md", "<style>" + "".join(rules) + "</style>" if rules else "")


def stat_pill(icon: str, color: str, value, label: str, compact_value: bool) -> str:
    count = f' data-count="{value}"' if isinstance(value, (int, float)) else ""
    flag = " data-compact" if compact_value else ""
    text = compact(value) if compact_value else full(value)
    return (
        f'<div class="mp-stat mp-stat--{color}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
        f'<span class="mp-stat__value"{count}{flag} title="{full(value)}">{text}</span>'
        f'<span class="mp-stat__label">{label}</span></div>'
    )


def gen_stats(snap: dict, history: list[dict]) -> None:
    game, votes = snap.get("game", {}), snap.get("votes", {})
    r = rating(votes)
    like = (
        '<div class="mp-stat mp-stat--red"><span class="mp-stat__icon" aria-hidden="true">' + lucide("thumbs-up") + "</span>"
        f'<span class="mp-stat__value" data-count="{r:.1f}" data-suffix="%" data-decimals="1">{r:.1f}%</span>'
        '<span class="mp-stat__label">like it</span></div>'
        if r is not None
        else ""
    )
    hero = [
        '<div class="mp-stats">',
        stat_pill("users", "green", game.get("playing"), "online", True),
        stat_pill("eye", "blue", game.get("visits"), "visits", True),
        stat_pill("star", "gold", game.get("favorites"), "favorites", True),
        like,
        "</div>",
        f'<p class="mp-updated">Live data from Roblox for the 18+ version, updated {time_tag(snap.get("fetched_at"))}</p>',
    ]
    write("home-stats.md", "\n".join(hero))

    grid = [
        '<div class="mp-stats mp-stats--grid">',
        stat_pill("users", "green", game.get("playing"), "playing now", False),
        stat_pill("eye", "blue", game.get("visits"), "total visits", True),
        stat_pill("star", "gold", game.get("favorites"), "favorites", True),
        like,
        stat_pill("heart", "pink", votes.get("up"), "likes", True),
        stat_pill("thumbs-down", "slate", votes.get("down"), "dislikes", True),
        "</div>",
        "",
        f'<p class="mp-updated">Updated {time_tag(snap.get("fetched_at"))}. The wiki refreshes these numbers every hour.</p>',
    ]
    write("stats.md", "\n".join(grid))

    on_sale = sum(1 for p in snap.get("passes", []) if p.get("for_sale"))
    # Nogo the creator gets the profile picture, the Nogo group (which
    # publishes the game on Roblox) gets the devil
    creator = game.get("creator") or "Nogo"
    developer, publisher = esc(creator), ""
    if creator.lower() == "nogo":
        developer = (
            f'<a class="mp-who" href="https://www.roblox.com/users/{CREATOR_USER_ID}/profile" '
            f'target="_blank" rel="noopener">{nogo_face("nogo")}Nogo</a>'
        )
        publisher = (
            f'| **Published by** | <a class="mp-who" href="https://www.roblox.com/groups/{CREATOR_GROUP_ID}" '
            f'target="_blank" rel="noopener">{nogo_face("group")}Nogo group</a> |'
        )
    facts = [
        "| Game | 18+ Meet People Across The World |",
        "|---|---|",
        f"| **Developer** | {developer} |",
        *([publisher] if publisher else []),
        f"| **Released** | {nice_date(game.get('created'))} |",
        f"| **Last game update** | {time_tag(game.get('updated'))} |",
        "| **Age requirement** | 18+ |",
        f"| **Players per server** | {full(game.get('max_players'))} |",
        f"| **Badges** | {len(snap.get('badges', []))} |",
        f"| **Gamepasses** | {len(snap.get('passes', []))} ({on_sale} on sale) |",
        f"| **Play** | [Open on Roblox](https://www.roblox.com/games/{PLACE_ID}) |",
    ]
    write("facts.md", "\n".join(facts))

    chart = ["## Visits per day", "", bar_chart(history), ""]
    if history:
        chart += ['??? info "Daily data collected by the wiki"', ""]
        chart += ["    | Date | Visits | Favorites | Likes | Dislikes |", "    |---|---|---|---|---|"]
        for p in reversed(history[-30:]):
            chart.append(
                f"    | {nice_date(p['date'] + 'T00:00:00Z')} | {full(p.get('visits'))} | {full(p.get('favorites'))} "
                f"| {full(p.get('up'))} | {full(p.get('down'))} |"
            )
    write("stats-history.md", "\n".join(chart))


def bar_chart(history: list[dict]) -> str:
    """Visits gained per day, as an accessible SVG bar chart."""
    points = []
    for prev, cur in zip(history, history[1:]):
        if isinstance(prev.get("visits"), int) and isinstance(cur.get("visits"), int):
            points.append((cur["date"], max(cur["visits"] - prev["visits"], 0)))
    points = points[-60:]
    if not points:
        return (
            '<p class="mp-chart-empty">The chart of daily visits appears here after the wiki has collected '
            "data for two days in a row.</p>"
        )
    width, height, left, bottom, top = 720, 260, 56, 28, 16
    plot_w, plot_h = width - left - 8, height - bottom - top
    vmax = max(v for _, v in points) or 1
    magnitude = 10 ** (len(str(int(vmax))) - 1)
    axis_max = ((int(vmax) // magnitude) + 1) * magnitude
    slot = plot_w / len(points)
    bar_w = max(min(slot - 2, 18), 2)
    parts = [
        f'<svg class="mp-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Visits gained per day, last {len(points)} days">'
    ]
    for i in range(5):
        value = axis_max * i / 4
        y = top + plot_h - plot_h * i / 4
        parts.append(f'<line class="mp-chart__grid" x1="{left}" x2="{width - 8}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="mp-chart__axis" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{compact(int(value))}</text>')
    for i, (date, value) in enumerate(points):
        h = plot_h * value / axis_max
        x = left + i * slot + (slot - bar_w) / 2
        y = top + plot_h - h
        r = min(4, bar_w / 2, h)
        path = (
            f"M{x:.1f},{top + plot_h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + bar_w - r:.1f} Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + r:.1f} V{top + plot_h:.1f} Z"
        )
        parts.append(
            f'<g class="mp-chart__bar"><rect x="{x - 1:.1f}" y="{top}" width="{bar_w + 2:.1f}" height="{plot_h}" class="mp-chart__hit"/>'
            f'<path d="{path}"/><title>{esc(nice_date(date + "T00:00:00Z"))}: {full(value)} visits</title></g>'
        )
    step = max(1, len(points) // 6)
    for i in range(0, len(points), step):
        date = points[i][0]
        x = left + i * slot + slot / 2
        parts.append(f'<text class="mp-chart__axis" x="{x:.1f}" y="{height - 8}" text-anchor="middle">{esc(nice_date(date + "T00:00:00Z")[:-5])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def gen_update_history(snap: dict, history: list[dict]) -> None:
    seen: dict[str, str] = {}
    stamps = [p.get("updated") for p in history] + [snap.get("game", {}).get("updated")]
    for value in stamps:
        t = parse_time(value)
        if t:
            seen[t.strftime("%Y-%m-%d")] = value
    if not seen:
        write("update-history.md", "No updates recorded yet.")
        return
    first = history[0]["date"] if history else None
    out = []
    if first:
        out.append(f'<p class="mp-lead">The wiki has been recording game updates since {esc(nice_date(first + "T00:00:00Z"))}.</p>')
        out.append("")
    out.append('<div class="mp-timeline">')
    for day in sorted(seen, reverse=True):
        out.append(
            f'<div class="mp-timeline__item"><span class="mp-timeline__date">{esc(nice_date(seen[day]))}</span>'
            f'<span class="mp-timeline__text">The game was updated ({time_tag(seen[day])}).</span></div>'
        )
    out.append("</div>")
    write("update-history.md", "\n".join(out))


# --------------------------------------------------------------------------
# Official updates from Discord
# --------------------------------------------------------------------------


def discord_get(path: str, token: str) -> list | dict:
    url = DISCORD_API + path
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"Authorization": f"Bot {token}", "User-Agent": DISCORD_UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                try:
                    wait = float(json.loads(exc.read().decode("utf-8")).get("retry_after", 2))
                except Exception:  # noqa: BLE001
                    wait = 2.0
                time.sleep(min(wait, 30) + 0.5)
                continue
            raise RuntimeError(f"Discord answered {exc.code} for {path}") from None
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise RuntimeError(f"could not reach Discord ({exc.__class__.__name__})") from None
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("Discord rate limit")


def fetch_discord_messages(token: str, channel: str, pages: int) -> tuple[list[dict], bool]:
    """Newest first. Returns (messages, complete) where complete means the
    whole channel history was read."""
    messages: list[dict] = []
    before = ""
    for _ in range(pages):
        query = "?limit=100" + (f"&before={before}" if before else "")
        page = discord_get(f"/channels/{channel}/messages{query}", token)
        if not isinstance(page, list):
            break
        messages += page
        if len(page) < 100:
            return messages, True
        before = page[-1]["id"]
    return messages, False


def download(url: str, target: Path) -> bool:
    if target.exists():
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"warning: image not downloaded ({exc.__class__.__name__})")
        return False


IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


def image_ext(url: str, content_type: str | None) -> str | None:
    if content_type in IMAGE_EXT:
        return IMAGE_EXT[content_type]
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return None


def simplify_message(m: dict) -> dict | None:
    """Keeps only announcements that arrived through the channel follow."""
    if not (m.get("flags", 0) & 2) or m.get("type", 0) not in (0, 19):
        return None
    ref = m.get("message_reference") or {}
    author = m.get("author") or {}
    avatar = None
    if author.get("avatar") and author.get("id"):
        avatar = f"https://cdn.discordapp.com/avatars/{author['id']}/{author['avatar']}.png?size=64"
    source = None
    if ref.get("guild_id") and ref.get("channel_id") and ref.get("message_id"):
        source = f"https://discord.com/channels/{ref['guild_id']}/{ref['channel_id']}/{ref['message_id']}"
    images = []
    for att in m.get("attachments", []):
        ext = image_ext(att.get("url", ""), att.get("content_type"))
        if ext and (att.get("size") or 0) <= MAX_IMAGE_BYTES:
            images.append({"name": f"{m['id']}-{att['id']}{ext}", "url": att["url"], "alt": att.get("filename", "")})
    embeds = []
    for i, e in enumerate(m.get("embeds", [])):
        item = {"title": e.get("title"), "description": e.get("description"), "url": e.get("url"), "image": None}
        pic = (e.get("image") or {}).get("url") or ((e.get("thumbnail") or {}).get("url") if e.get("type") == "image" else None)
        ext = image_ext(pic or "", None) if pic else None
        if pic and ext:
            item["image"] = {"name": f"{m['id']}-e{i}{ext}", "url": pic, "alt": e.get("title") or "image"}
        if item["title"] or item["description"] or item["image"]:
            embeds.append(item)
    return {
        "id": m["id"],
        "timestamp": m.get("timestamp"),
        "edited": m.get("edited_timestamp"),
        "author": author.get("global_name") or author.get("username") or "Updates",
        "avatar": avatar,
        "content": m.get("content") or "",
        "mentions": {u["id"]: (u.get("global_name") or u.get("username") or "someone") for u in m.get("mentions", [])},
        "source": source,
        "images": images,
        "embeds": embeds,
    }


def save_images(item: dict) -> None:
    """Discord image links expire, so the wiki keeps its own copy."""
    for img in item["images"] + [e["image"] for e in item["embeds"] if e.get("image")]:
        if download(img["url"], UPDATE_ASSETS / img["name"]):
            img["file"] = f"assets/updates/{img['name']}"
        img.pop("url", None)


def update_discord() -> bool:
    """Merges new announcements into the archive. Returns True if it changed."""
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    archive = json.loads(DISCORD_ARCHIVE.read_text("utf-8")) if DISCORD_ARCHIVE.exists() else []
    if not token or not channel:
        print("Discord updates: not configured (DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID)")
        return False
    try:
        raw, complete = fetch_discord_messages(token, channel, pages=1 if archive else 5)
    except RuntimeError as exc:
        print(f"warning: Discord updates not refreshed, keeping the archive ({exc})")
        return False

    fetched = {}
    for m in raw:
        item = simplify_message(m)
        if item:
            fetched[item["id"]] = item
    before = json.dumps(archive, sort_keys=True)
    by_id = {a["id"]: a for a in archive}
    for msg_id, item in fetched.items():
        old = by_id.get(msg_id)
        if old and old.get("edited") == item["edited"] and old.get("content") == item["content"]:
            continue
        save_images(item)
        by_id[msg_id] = item
    # Announcements deleted on Discord disappear from the wiki too.
    if raw:
        oldest_seen = min(int(m["id"]) for m in raw)
        for msg_id in list(by_id):
            if msg_id not in fetched and (complete or int(msg_id) >= oldest_seen):
                del by_id[msg_id]
    archive = sorted(by_id.values(), key=lambda a: int(a["id"]), reverse=True)
    after = json.dumps(archive, sort_keys=True)
    if after != before:
        DISCORD_ARCHIVE.write_text(json.dumps(archive, indent=1, ensure_ascii=False) + "\n", "utf-8")
        print(f"Discord updates: {len(archive)} in the archive (changed)")
        return True
    print(f"Discord updates: {len(archive)} in the archive (no change)")
    return False


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"\|\|(.+?)\|\|", r'<span class="mp-spoiler" tabindex="0">\1</span>', text)
    return text


def discord_html(text: str, mentions: dict) -> str:
    """Discord markdown -> safe HTML (everything is escaped first)."""
    kept: list[str] = []

    def keep(fragment: str) -> str:
        kept.append(fragment)
        return f"\x00{len(kept) - 1}\x00"

    text = re.sub(r"```(?:[\w+-]*\n)?(.*?)```", lambda m: keep(f"<pre><code>{esc(m.group(1).strip(chr(10)))}</code></pre>"), text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{esc(m.group(1))}</code>"), text)
    text = re.sub(
        r"<(a?):(\w+):(\d+)>",
        lambda m: keep(
            f'<img class="mp-emoji" src="https://cdn.discordapp.com/emojis/{m.group(3)}.{"gif" if m.group(1) else "webp"}?size=48" '
            f'alt=":{esc(m.group(2))}:" title=":{esc(m.group(2))}:">'
        ),
        text,
    )
    text = re.sub(
        r"<t:(-?\d+)(?::[tTdDfFR])?>",
        lambda m: keep(esc(nice_date(dt.datetime.fromtimestamp(int(m.group(1)), dt.timezone.utc).isoformat(), True))),
        text,
    )
    text = re.sub(r"<@!?(\d+)>", lambda m: keep(f'<span class="mp-mention">@{esc(mentions.get(m.group(1), "someone"))}</span>'), text)
    text = re.sub(r"<@&\d+>", "", text)
    text = re.sub(r"<#\d+>", lambda m: keep('<span class="mp-mention">#channel</span>'), text)
    text = re.sub(r"@(everyone|here)\b", "", text)
    text = re.sub(
        r"\[([^\]\n]+)\]\(<?(https?://[^\s)>]+)>?\)",
        lambda m: keep(f'<a href="{esc(m.group(2))}" target="_blank" rel="noopener nofollow">{_inline(esc(m.group(1)))}</a>'),
        text,
    )
    text = re.sub(
        r"<?(https?://[^\s<>]+[^\s<>.,!?)])>?",
        lambda m: keep(
            f'<a href="{esc(m.group(1))}" target="_blank" rel="noopener nofollow">'
            f"{esc(re.sub(r'^https?://(www[.])?', '', m.group(1))[:60])}</a>"
        ),
        text,
    )
    text = esc(text)

    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    quote: list[str] = []

    def flush() -> None:
        if para:
            out.append("<p>" + "<br>".join(_inline(x) for x in para) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            items.clear()
        if quote:
            out.append("<blockquote>" + "<br>".join(_inline(x) for x in quote) + "</blockquote>")
            quote.clear()

    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("&gt;&gt;&gt; "):
            flush()
            quote.extend([stripped[13:]] + lines[i + 1 :])
            break
        heading = re.match(r"^(#{1,3}) (.+)$", stripped)
        if heading:
            flush()
            out.append(f'<p class="mp-patch__h mp-patch__h--{len(heading.group(1))}">{_inline(heading.group(2))}</p>')
        elif stripped.startswith("-# "):
            flush()
            out.append(f'<p class="mp-patch__sub">{_inline(stripped[3:])}</p>')
        elif re.match(r"^[-*•] ", stripped):
            if para or quote:
                flush()
            items.append(stripped[2:])
        elif stripped.startswith("&gt; "):
            if para or items:
                flush()
            quote.append(stripped[5:])
        elif not stripped:
            flush()
        else:
            if items or quote:
                flush()
            para.append(stripped)
    flush()
    html_out = "\n".join(out)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], html_out)


def split_title(content: str) -> tuple[str | None, str]:
    """Uses a first line that is a heading or fully bold as the title."""
    lines = content.strip().split("\n")
    if not lines or not lines[0].strip():
        return None, content
    first = lines[0].strip()
    m = re.match(r"^#{1,3} (.+)$", first) or re.match(r"^\*\*([^*]+)\*\*$", first) or re.match(r"^__\*\*([^*]+)\*\*__$", first)
    if m:
        return m.group(1).strip(), "\n".join(lines[1:]).strip()
    return None, content


def plain_title(update: dict) -> str:
    title, body = split_title(update.get("content", ""))
    if not title and update.get("embeds"):
        title = update["embeds"][0].get("title")
    if not title:
        first = next((x.strip() for x in body.splitlines() if x.strip()), "")
        title = first or "Game update"
    title = re.sub(r"<a?:\w+:\d+>|<@[!&]?\d+>|<#\d+>|<t:-?\d+(?::\w)?>", "", title)
    title = re.sub(r"[*_~|`#>]", "", title).strip()
    return title[:90] + ("…" if len(title) > 90 else "")


def gen_discord(page: str = "events/update-history.md") -> None:
    archive = json.loads(DISCORD_ARCHIVE.read_text("utf-8")) if DISCORD_ARCHIVE.exists() else []
    if not archive:
        write(
            "discord-updates.md",
            '<div class="mp-patch mp-patch--empty"><p>The official update announcements from the game\'s Discord '
            "will appear here automatically as soon as the next one is posted.</p></div>",
        )
        write("home-discord.md", "")
        write("discord-count.md", "")
        return
    asset_base = posixpath.relpath("assets", posixpath.dirname(page) or ".")
    out = []
    for u in archive:
        title, body = split_title(u.get("content", ""))
        when = u.get("timestamp")
        t = parse_time(when)
        new_until = (t + dt.timedelta(days=7)).isoformat() if t else ""
        head = (
            f'<header class="mp-patch__head">'
            + (f'<img class="mp-patch__avatar" src="{esc(u["avatar"])}" alt="" width="40" height="40" loading="lazy">' if u.get("avatar") else '<span class="mp-patch__avatar"></span>')
            + f'<span class="mp-patch__who"><b class="mp-patch__title">{_inline(esc(title)) if title else "Game update"}</b>'
            f'<span class="mp-patch__meta">{esc(u.get("author") or "Updates")} · {time_tag(when)}</span></span>'
            + (f'<span class="mp-patch__new" data-hide-after="{esc(new_until)}">NEW</span>' if new_until else "")
            + "</header>"
        )
        parts = [f'<article class="mp-patch" id="update-{esc(u["id"])}">', head, '<div class="mp-patch__body">']
        if body.strip():
            parts.append(discord_html(body, u.get("mentions", {})))
        for e in u.get("embeds", []):
            parts.append('<div class="mp-patch__embed">')
            if e.get("title"):
                t_html = _inline(esc(e["title"]))
                if e.get("url"):
                    t_html = f'<a href="{esc(e["url"])}" target="_blank" rel="noopener nofollow">{t_html}</a>'
                parts.append(f'<p class="mp-patch__h mp-patch__h--3">{t_html}</p>')
            if e.get("description"):
                parts.append(discord_html(e["description"], u.get("mentions", {})))
            if e.get("image") and e["image"].get("file"):
                parts.append(f'<img class="mp-patch__img" src="{esc(asset_base + "/" + e["image"]["file"][len("assets/"):])}" alt="{esc(e["image"]["alt"])}" loading="lazy">')
            parts.append("</div>")
        pics = [img for img in u.get("images", []) if img.get("file")]
        if pics:
            parts.append('<div class="mp-patch__gallery">')
            for img in pics:
                src = asset_base + "/" + img["file"][len("assets/"):]
                parts.append(f'<a href="{esc(src)}" target="_blank" rel="noopener"><img class="mp-patch__img" src="{esc(src)}" alt="{esc(img["alt"])}" loading="lazy"></a>')
            parts.append("</div>")
        parts.append("</div>")
        if u.get("source"):
            parts.append(f'<a class="mp-patch__src" href="{esc(u["source"])}" target="_blank" rel="noopener">View on Discord</a>')
        parts.append("</article>")
        out.append("".join(parts))
    write("discord-updates.md", '<div class="mp-patches">\n' + "\n".join(out) + "\n</div>")
    write("discord-count.md", f'<p class="mp-lead"><b>{len(archive)}</b> official announcements collected so far.</p>')

    lines = []
    for u in archive[:3]:
        d = parse_time(u.get("timestamp"))
        label = f"Update · {d.day} {d.strftime('%b')}" if d else "Update"
        # the first change of the update, so the home page says what's new
        _, body = split_title(u.get("content", ""))
        first = next((re.sub(r"^[-*•] ", "", x.strip()) for x in body.splitlines() if x.strip()), "")
        first = re.sub(r"<a?:\w+:\d+>|<@[!&]?\d+>|<#\d+>|[*_~|`#>]", "", first).strip()
        # the bug report credit stays on the Update History page
        first = re.sub(r"\s*\(Thanks [^)]*\)\s*$", "", first)
        if len(first) > 90:
            first = first[:90].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        more = f' <span class="mp-news__more">{esc(first)}</span>' if first else ""
        lines.append(
            f'<li><span class="mp-news__date">{esc(label)}</span>'
            f'<a href="{rel("index.md", page, "update-" + u["id"])}">{esc(plain_title(u))}</a>{more}</li>'
        )
    write("home-discord.md", "\n".join(lines))


# --------------------------------------------------------------------------
# Seasonal events: current event, rotation, galleries
# --------------------------------------------------------------------------


def easter(year: int) -> dt.date:
    """Gregorian Easter Sunday."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def holiday(event: dict, year: int) -> dt.date:
    if event["date"] == "easter":
        return easter(year)
    month, day = (int(x) for x in event["date"].split("-"))
    return dt.date(year, month, day)


def next_holiday(event: dict, today: dt.date) -> dt.date:
    d = holiday(event, today.year)
    return d if d >= today else holiday(event, today.year + 1)


def load_events() -> dict:
    if not EVENTS_FILE.exists():
        return {"rotation": [], "special": []}
    return json.loads(EVENTS_FILE.read_text("utf-8"))


def event_state(now: dt.datetime | None = None) -> dict:
    """Which event is running now, and the order of the next ones."""
    cfg = load_events()
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date()
    by_id = {e["id"]: e for e in cfg.get("rotation", [])}
    current = cfg.get("current") or {}
    ends = parse_time(current.get("ends"))
    active = bool(current.get("event") in by_id and ends and now < ends)
    cur_event = by_id.get(current.get("event")) if active else None
    upcoming = sorted(
        (e for e in cfg.get("rotation", []) if e is not cur_event),
        key=lambda e: next_holiday(e, today),
    )
    return {"cfg": cfg, "now": now, "today": today, "active": active, "current": current, "event": cur_event,
            "ends": ends, "upcoming": upcoming, "special": cfg.get("special", [])}


def event_link(from_page: str, e: dict) -> str:
    return rel(from_page, e["page"], e.get("anchor", ""))


def gen_events() -> None:
    st = event_state()
    today = st["today"]
    out_status = GEN_DIR / "event-status"
    out_status.mkdir(parents=True, exist_ok=True)

    # Home page strip and news line
    if st["active"]:
        e, cur = st["event"], st["current"]
        note = f' <small>({esc(cur["ends_note"])})</small>' if cur.get("ends_note") else ""
        strip = (
            f'<a class="mp-event" href="{event_link("index.md", e)}" data-hide-after="{esc(cur["ends"])}">'
            f'<span class="mp-limited">LIMITED</span>'
            f'<span class="mp-event__emoji">{esc(e["emoji"])}</span>'
            f'<span><b>{esc(cur.get("edition") or e["name"])} is here!</b> {cur.get("highlight", "")}. '
            f'Ends in <span class="mp-countdown" data-countdown="{esc(cur["ends"])}">{esc(nice_date(cur["ends"]))}</span>{note}</span>'
            f'<span class="mp-event__go">See the event</span></a>'
        )
        news = (
            f'<li data-hide-after="{esc(cur["ends"])}"><span class="mp-news__date">Event</span>{esc(e["emoji"])} '
            f'<a href="{event_link("index.md", e)}">{esc(cur.get("edition") or e["name"])}</a> is live: {cur.get("highlight", "")}</li>'
        )
    elif st["upcoming"]:
        e = st["upcoming"][0]
        d = next_holiday(e, today)
        strip = (
            f'<a class="mp-event mp-event--next" href="{event_link("index.md", e)}">'
            f'<span class="mp-limited mp-limited--next">NEXT EVENT</span>'
            f'<span class="mp-event__emoji">{esc(e["emoji"])}</span>'
            f'<span><b>{esc(e["name"])}</b> usually arrives in {esc(e["season"])} (around {d.day} {d.strftime("%B")}).</span>'
            f'<span class="mp-event__go">See past editions</span></a>'
        )
        news = ""
    else:
        strip, news = "", ""
    write("home-event.md", strip)
    write("home-event-news.md", news)

    # Event calendar for the Events & Updates page
    here = "events/index.md"
    lines = []
    if st["active"]:
        e, cur = st["event"], st["current"]
        lines += [
            "## Happening now",
            "",
            f'<a class="mp-now" href="{event_link(here, e)}">'
            f'<span class="mp-now__emoji">{esc(e["emoji"])}</span>'
            f'<span class="mp-now__text"><span class="mp-now__label">NOW</span>'
            f'<b class="mp-now__title">{esc(cur.get("edition") or e["name"])}</b>'
            f'<span class="mp-now__desc">{cur.get("highlight", "")}.</span>'
            f'<span class="mp-now__ends">Ends in <span class="mp-countdown" data-countdown="{esc(cur["ends"])}">'
            f'{esc(nice_date(cur["ends"]))}</span></span></span></a>',
            "",
        ]
    lines += [
        "## Event rotation",
        "",
        "The seasonal events come back every year around the same holiday. When one ends, the next one in the calendar takes its place.",
        "",
        '<div class="mp-rotation">',
    ]
    ordered = ([st["event"]] if st["active"] else []) + st["upcoming"]
    for i, e in enumerate(ordered):
        if st["active"] and i == 0:
            tag, when = '<span class="mp-rot__tag mp-rot__tag--now">NOW</span>', "Running now"
        else:
            d = next_holiday(e, today)
            tag = '<span class="mp-rot__tag mp-rot__tag--next">NEXT</span>' if i == (1 if st["active"] else 0) else ""
            when = f"Around {d.day} {d.strftime('%b %Y')}"
        lines.append(
            f'<a class="mp-rot" href="{event_link(here, e)}" style="--i:{i}">{tag}'
            f'<span class="mp-rot__emoji">{esc(e["emoji"])}</span>'
            f'<span class="mp-rot__name">{esc(e["name"])}</span>'
            f'<span class="mp-rot__when">{esc(when)}</span>'
            f'<span class="mp-rot__season">{esc(e["season"])}</span></a>'
        )
    lines.append("</div>")
    if st["special"]:
        lines += ["", "## Special events", "", "One-off events that are not part of the yearly rotation.", "", '<div class="mp-rotation">']
        for i, e in enumerate(st["special"]):
            lines.append(
                f'<a class="mp-rot mp-rot--special" href="{event_link(here, e)}" style="--i:{i}">'
                f'<span class="mp-rot__emoji">{esc(e["emoji"])}</span><span class="mp-rot__name">{esc(e["name"])}</span>'
                f'<span class="mp-rot__when">{esc(e.get("when", ""))}</span></a>'
            )
        lines.append("</div>")
    write("event-calendar.md", "\n".join(lines))

    # Banner at the top of each event page
    for e in st["cfg"].get("rotation", []) + st["special"]:
        if st["active"] and e is st["event"]:
            cur = st["current"]
            html_out = (
                f'<div class="mp-evstatus mp-evstatus--now"><span class="mp-evstatus__emoji">{esc(e["emoji"])}</span>'
                f'<span><b>Happening now: {esc(cur.get("edition") or e["name"])}</b> · ends in '
                f'<span class="mp-countdown" data-countdown="{esc(cur["ends"])}">{esc(nice_date(cur["ends"]))}</span></span></div>'
            )
        elif "date" in e:
            d = next_holiday(e, today)
            html_out = (
                f'<div class="mp-evstatus"><span class="mp-evstatus__emoji">{esc(e["emoji"])}</span>'
                f'<span><b>Rotating event</b> · comes back every year in {esc(e["season"])}. '
                f'Next: around {d.day} {d.strftime("%B %Y")}.</span></div>'
            )
        else:
            html_out = (
                f'<div class="mp-evstatus"><span class="mp-evstatus__emoji">{esc(e["emoji"])}</span>'
                f'<span><b>Special event</b> · {esc(e.get("when", ""))}.</span></div>'
            )
        write(f"event-status/{e['id']}.md", html_out)


def caption_from_name(name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", name)
    stem = re.sub(r"^\d+[-_ ]*", "", stem)
    text = re.sub(r"[-_]+", " ", stem).strip()
    return text[:1].upper() + text[1:] if text else ""


def gen_galleries() -> None:
    """Every '--8<-- "generated/gallery/NAME.md"' in a page shows the images
    found in docs/assets/events/NAME/ (sorted by file name; the file name,
    without leading numbers, becomes the caption)."""
    refs: dict[str, str] = {}
    for md in sorted(DOCS.rglob("*.md")):
        for name in re.findall(r'^--8<-- "generated/gallery/([\w-]+)\.md"', md.read_text("utf-8"), re.M):
            refs.setdefault(name, md.relative_to(DOCS).as_posix())
    for name, page in refs.items():
        folder = GALLERY_ROOT / name
        files = sorted(f for f in folder.iterdir() if f.suffix.lower() in IMAGE_FILES) if folder.is_dir() else []
        if not files:
            write(
                f"gallery/{name}.md",
                '<div class="mp-gallery mp-gallery--empty"><span>📸</span> Screenshots of this edition are coming soon.</div>',
            )
            continue
        start = posixpath.dirname(page) or "."
        items = []
        for f in files:
            src = posixpath.relpath(f"assets/events/{name}/{f.name}", start)
            cap = caption_from_name(f.name)
            items.append(
                f'<figure class="mp-shot"><a href="{esc(src)}" target="_blank" rel="noopener">'
                f'<img src="{esc(src)}" alt="{esc(cap or name)}" loading="lazy"></a>'
                + (f"<figcaption>{esc(cap)}</figcaption>" if cap else "")
                + "</figure>"
            )
        write(f"gallery/{name}.md", '<div class="mp-gallery">' + "".join(items) + "</div>")


# --------------------------------------------------------------------------
# Rules: the official rulebook, built from data/rules.json
# --------------------------------------------------------------------------

RULES_FILE = DATA_DIR / "rules.json"
RULES_PAGE = "community/rules.md"
RULE_IMAGES = DOCS / "assets" / "rules"

# Colours and icons of the chapters that are not ban code groups
RB_EXTRA = {
    "start": ("Start here", "Start", "book-open-text", "How bans work"),
    "not": ("Not bannable", "Not bannable", "circle-check", "Things that are allowed"),
    "unbans": ("Unbans", "Unbans", "unlock", "How to get unbanned"),
    "faq": ("Questions", "FAQ", "circle-help", "Frequently asked questions"),
    "discord": ("Discord bans", "Discord", "message-circle", "Bans on the community server"),
}
STRIKE = "3 days → 7 days → 30 days → permanent"


def md_inline(text: str) -> str:
    return _inline(esc(text))


# A quote after one of these words, in the same sentence, is something a player says or writes
SPEECH_VERB = re.compile(
    r"\b(say|says|said|saying|tell|tells|told|telling|ask|asks|asked|asking|call|calls|called|calling|"
    r"post|posts|posted|type|types|typed|write|writes|wrote|reply|replies|replied|shout|shouts|yell|yells)\b",
    re.IGNORECASE,
)


RULES_DISCORD = "https://discord.com/invite/ASRasdGjzA"

# Game words in the rules that link to their wiki page (each one once per rule)
RULE_LINKS = [
    (r"\bDraw(?:ing)? Area\b", "activities/draw-area.md", ""),
    (r"\bDrink Area\b", "activities/drink-area.md", ""),
    (r"\bArenas\b", "activities/combat-arenas.md", ""),
    (r"\bLottery\b", "activities/lottery.md", ""),
    (r"\bAvatar (?:Item )?Laser\b|\bLasers\b", "items/troll-items.md", "lasers"),
    (r"\bFly gamepass\b", "items/gamepasses.md", ""),
    (r"\bSize Changer gamepass\b", "items/gamepasses.md", ""),
    (r"\bAdmin Panel\b", "servers/admin-panel.md", ""),
    (r"\breputation\b", "mechanics/reputation.md", ""),
    (r"\bcoins\b", "mechanics/coins.md", ""),
    (r"\bvoice chat\b", "servers/voice-chat.md", ""),
    (r"\bplayer reports\b", "community/reporting.md", ""),
    (r"\bbio\b", "mechanics/profiles.md", ""),
    (r"(?:(?<=\ba )|(?<=\bthe ))Country\b(?! [XY])", "mechanics/countries.md", ""),
    (r"\b(?:official|community) Discord\b", None, RULES_DISCORD),
]
_rule_linked: set[int] = set()  # RULE_LINKS already used in the rule being written
_rule_codes: set[str] = set()  # codes that have a card, so "**b8**" can link to it
_rule_current: list[str] = [""]  # the rule being written, which never links to itself


def rule_text(text: str) -> str:
    """md_inline, with the quoted words players say shown as in-game chat bubbles,
    other rules' codes linked to their card and game words linked to their wiki page."""
    out, pos, armed = [], 0, False
    for m in re.finditer(r'"([^"]+)"', text):
        before = text[pos:m.start()]
        cut = max(before.rfind(". "), before.rfind("! "), before.rfind("? "))
        if cut != -1:
            armed = False
            before_tail = before[cut + 2:]
        else:
            before_tail = before
        armed = armed or bool(SPEECH_VERB.search(before_tail))
        out.append(before)
        out.append(f"\x01{m.group(1)}\x02" if armed else m.group(0))
        pos = m.end()
    out.append(text[pos:])

    urls: list[str] = []

    def link_words(part: str) -> str:
        for i, (pattern, page, target) in enumerate(RULE_LINKS):
            if i in _rule_linked:
                continue
            m = re.search(pattern, part)
            if not m:
                continue
            _rule_linked.add(i)
            urls.append(target if page is None else rel(RULES_PAGE, page, target))
            part = f"{part[:m.start()]}\x03{len(urls) - 1}\x04{m.group(0)}\x05{part[m.end():]}"
        return part

    # never link inside a chat bubble
    joined = "".join(p if p.startswith("\x01") else link_words(p) for p in re.split(r"(\x01[^\x02]*\x02)", "".join(out)))
    html_text = md_inline(joined).replace("\x01", '<span class="rb-say">').replace("\x02", "</span>")

    def page_link(m: re.Match) -> str:
        url = urls[int(m.group(1))]
        new_tab = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return f'<a class="rb-ref rb-ref--page" href="{esc(url)}"{new_tab}>{m.group(2)}</a>'

    html_text = re.sub(r"\x03(\d+)\x04(.*?)\x05", page_link, html_text)
    html_text = re.sub(
        r"<b>([a-e][1-9])</b>",
        lambda m: f'<a class="rb-ref rb-ref--code" href="#{m.group(1)}">{m.group(1)}</a>'
        if m.group(1) in _rule_codes and m.group(1) != _rule_current[0] else m.group(0),
        html_text,
    )
    return re.sub(r"section <b>([a-e])</b>", r'section <a class="rb-ref rb-ref--code" href="#rb-\1">\1</a>', html_text)



def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def rule_note(text: str) -> str:
    """rule_text for text outside the rule cards (each block links its words again)."""
    _rule_linked.clear()
    _rule_current[0] = ""
    return rule_text(text)


def rule_pic(pic: dict, rule_code: str, side: str) -> str:
    """One example picture: a thumbnail that opens full size. Bannable ones start hidden, like Discord spoilers."""
    path = RULE_IMAGES / pic["src"]
    size = ""
    try:
        from PIL import Image  # noqa: PLC0415

        with Image.open(path) as im:
            size = f' width="{im.width}" height="{im.height}"'
    except Exception:  # noqa: BLE001
        pass
    src = posixpath.relpath(f"assets/rules/{pic['src']}", posixpath.dirname(RULES_PAGE))
    mark = pic.get("mark") or side
    spoiler = pic.get("spoiler")
    veil = ""
    if spoiler:
        label = "Bannable example" if mark == "ban" else pic.get("spoiler_label") or "Sensitive"
        veil = (
            f'<span class="rb-pic__veil">{lucide("eye-off")}<b>Tap to show</b><small>{esc(label)}</small></span>'
        )
    sign = lucide("x") if mark == "ban" else lucide("check")
    return (
        f'<button type="button" class="rb-pic rb-pic--{mark}{" is-spoiler" if spoiler else ""}" '
        f'data-src="{esc(src)}" data-cap="{esc(pic["alt"])}" data-mark="{mark}" data-rule="{rule_code}">'
        f'<img src="{esc(src)}" alt="{esc(pic["alt"])}" loading="lazy"{size}>'
        f'<span class="rb-pic__mark" aria-hidden="true">{sign}</span>{veil}</button>'
    )


def rule_examples(rule: dict, side: str) -> str:
    items = rule.get("bannable" if side == "ban" else "ok", [])
    if not items:
        return ""
    head = (lucide("circle-x") + "<span>Bannable</span>") if side == "ban" else (lucide("circle-check") + "<span>Not bannable</span>")
    out = [f'<div class="rb-side rb-side--{side}"><p class="rb-side__head">{head}<span class="rb-side__n">{len(items)}</span></p><ul class="rb-exs">']
    for x in items:
        x = {"t": x} if isinstance(x, str) else x
        d = f'<span class="rb-ex__d">{rule_text(x["d"])}</span>' if x.get("d") else ""
        sub = ""
        if x.get("ex"):
            items_html = []
            for e in x["ex"]:
                first, sep, rest = e.partition(". ")
                if sep and rest:
                    items_html.append(f'<li><span class="rb-sub__t">{rule_text(first)}.</span> <span class="rb-sub__why">{rule_text(rest)}</span></li>')
                else:
                    items_html.append(f'<li><span class="rb-sub__t">{rule_text(e)}</span></li>')
            label = "For example" if len(x["ex"]) == 1 else f'{len(x["ex"])} examples'
            sub = f'<span class="rb-sub"><span class="rb-sub__head">{label}</span><ul>{"".join(items_html)}</ul></span>'
        pics = ""
        if x.get("img"):
            pics = '<span class="rb-pics">' + "".join(rule_pic({**p, "spoiler_label": x.get("spoiler_label")}, rule["code"], side) for p in x["img"]) + "</span>"
        out.append(f'<li class="rb-ex"><span class="rb-ex__t">{rule_text(x["t"])}</span>{d}{sub}{pics}</li>')
    out.append("</ul></div>")
    return "".join(out)


def rule_punishment(rule: dict, group: dict) -> tuple[list[tuple[str, str, str]], str]:
    """(chips for the closed card, sentence for the open card)."""
    chips: list[tuple[str, str, str]] = []
    if rule.get("removed"):
        return [("off", "ban", "Removed")], "This rule is not used right now."
    if group["kind"] == "permanent":
        if rule.get("tag") == "1 year":
            chips.append(("year", "calendar-x", "1 year ban"))
            text = "A <b>1 year ban</b> instead of a permanent one."
        else:
            chips.append(("perm", "octagon-x", "Permanent"))
            text = "A <b>permanent ban</b> straight away."
    else:
        chips.append(("strike", "timer", "Strike ban"))
        text = f"Strike ban: <b>{STRIKE}</b>. Breaking this same rule twice is permanent."
    if rule.get("tag") == "Data wipe":
        chips.append(("wipe", "database-zap", "Data wipe"))
    if rule.get("scope"):
        chips.append(("scope", "earth", "In and out of game"))
    return chips, text


def rule_card(rule: dict, group: dict, words: dict, faq: dict) -> str:
    code = rule["code"]
    _rule_linked.clear()
    _rule_current[0] = code
    chips, punish = rule_punishment(rule, group)
    n_ex = len(rule.get("bannable", [])) + len(rule.get("ok", [])) + len(rule.get("never", []))
    n_pic = sum(len(x.get("img", [])) for x in rule.get("bannable", []) + rule.get("ok", []) if isinstance(x, dict))
    if n_ex:
        chips.append(("ex", "list-checks", f"{n_ex} example{'s' if n_ex != 1 else ''}"))
    if n_pic:
        chips.append(("pics", "camera", f"{n_pic} picture{'s' if n_pic != 1 else ''}"))
    if not n_ex and not rule.get("removed"):
        chips.append(("soon", "hourglass", "Examples soon"))

    chip_html = "".join(f'<span class="rb-chip rb-chip--{k}">{lucide(i)}<span>{esc(t)}</span></span>' for k, i, t in chips)
    body: list[str] = []
    note = rule.get("note")
    if rule.get("scope"):
        body.append(f'<p class="rb-callout rb-callout--scope">{lucide("earth")}<span>{md_inline(rule["scope"])}.</span></p>')
    if note and not rule.get("removed"):
        body.append(f'<p class="rb-callout rb-callout--note">{lucide("info")}<span>{rule_text(note.rstrip("."))}.</span></p>')
    if rule.get("explain"):
        body.append(
            f'<div class="rb-explain"><p class="rb-explain__head">{lucide("lightbulb")}<span>How it works</span></p>'
            + "".join(f"<p>{rule_text(p)}</p>" for p in rule["explain"])
            + "</div>"
        )
    sides = rule_examples(rule, "ban") + rule_examples(rule, "ok")
    if sides:
        body.append(f'<div class="rb-compare">{sides}</div>')
    if rule.get("never"):
        body.append(
            f'<div class="rb-side rb-side--never"><p class="rb-side__head">{lucide("shield-x")}<span>Never unbanned for</span>'
            f'<span class="rb-side__n">{len(rule["never"])}</span></p><ul class="rb-exs">'
            + "".join(f'<li class="rb-ex"><span class="rb-ex__t">{rule_text(x)}</span></li>' for x in rule["never"])
            + "</ul></div>"
        )
    if not n_ex and not rule.get("removed"):
        body.append(
            f'<p class="rb-soon">{lucide("hourglass")}<span>The examples for this rule are being added to the wiki. '
            "Until then, the title above is the official rule.</span></p>"
        )
    if rule.get("counts"):
        rows = "".join(
            f'<span class="rb-count"><b>{lucide(words[w]["icon"])}{esc(w)}</b> means {md_inline(words[w]["means"])}</span>'
            for w in rule["counts"]
            if w in words
        )
        body.append(f'<div class="rb-counts"><p class="rb-counts__head">Counts everywhere</p>{rows}</div>')
    for q in rule.get("faq", []):
        if q in faq:
            body.append(
                f'<div class="rb-related"><p class="rb-related__q">{lucide("circle-help")}<span>{md_inline(q)}</span></p>'
                f"<p>{rule_text(faq[q])}</p></div>"
            )
    body.append(
        f'<div class="rb-rule__foot"><span class="rb-punish">{lucide("gavel")}<span>{punish}</span></span>'
        f'<button type="button" class="rb-copy" data-code="{code}">{lucide("link")}<span>Copy link</span></button></div>'
    )
    search = " ".join(
        [code, rule.get("title", ""), rule.get("note", ""), " ".join(rule.get("explain", []))]
        + [(x["t"] + " " + x.get("d", "") + " " + " ".join(x.get("ex", []))) if isinstance(x, dict) else x
           for x in rule.get("bannable", []) + rule.get("ok", [])]
        + rule.get("never", [])
    ).lower()
    return (
        f'<details class="rb-rule rb-rule--{group["id"]}{" is-removed" if rule.get("removed") else ""}" id="{code}" data-search="{esc(search)}">'
        f'<summary><span class="rb-code">{code}</span><span class="rb-rule__main">'
        f'<span class="rb-rule__title">{md_inline(rule["title"])}</span><span class="rb-chips">{chip_html}</span></span>'
        f'<span class="rb-rule__toggle" aria-hidden="true"><span class="rb-rule__open">Open</span>'
        f'<span class="rb-rule__close">Close</span>{lucide("chevron-down")}</span></summary>'
        f'<div class="rb-rule__body"><div class="rb-rule__inner">{"".join(body)}</div></div></details>'
    )


def gen_rules() -> None:
    if not RULES_FILE.exists():
        write("rules-book.md", "")
        return
    R = json.loads(RULES_FILE.read_text("utf-8"))
    src = R["source"]
    words = {w["word"]: w for w in R["reading"]["words"]}
    faq = {x["q"]: x["a"] for x in R["faq"]}
    groups = R["groups"]
    active = [r for g in groups for r in g["rules"] if not r.get("empty") and not r.get("removed")]
    _rule_codes.clear()
    _rule_codes.update(r["code"] for g in groups for r in g["rules"] if not r.get("empty"))

    # (id, title, short name, icon or letter, subtitle, html, css class)
    chapters: list[dict] = []

    def chapter(cid: str, title: str, short: str, mark: str, sub: str, about: str, html_body: str, cls: str, letter: bool = False) -> None:
        chapters.append({"id": f"rb-{cid}", "title": title, "short": short, "mark": mark, "letter": letter,
                         "sub": sub, "about": about, "body": html_body, "cls": cls})

    # ---------------------------------------------------------------- Start here
    steps = R["lengths"]["steps"]
    ladder = "".join(
        f'<div class="rb-step rb-step--{i}"><span class="rb-step__n">{esc(s["n"])}</span>'
        f'<span class="rb-step__len">{esc(s["len"])}</span></div>'
        + (f'<span class="rb-step__arrow" aria-hidden="true">{lucide("chevron-right")}</span>' if i < len(steps) - 1 else "")
        for i, s in enumerate(steps)
    )
    fact_heads = [("layers", "Many at once = one ban"), ("repeat", "Same rule twice = permanent"),
                  ("octagon-x", "d and e = permanent now"), ("users", "Counts on all your accounts")]
    facts = "".join(
        f'<div class="rb-fact"><span class="rb-fact__icon">{lucide(fact_heads[i][0])}</span>'
        f'<b>{esc(fact_heads[i][1])}</b><span>{rule_note(n.rstrip("."))}.</span></div>'
        for i, n in enumerate(R["lengths"]["notes"][:4])
    )
    tiles = "".join(
        f'<a class="rb-gtile rb-gtile--{g["id"]}" href="#rb-{g["id"]}"><span class="rb-letter">{g["id"]}</span>'
        f'<span class="rb-gtile__t"><b>{esc(g["title"])}</b><small>{esc(g["about"])}</small></span>'
        f'<span class="rb-gtile__k rb-gtile__k--{"perm" if g["kind"] == "permanent" else "strike"}">'
        f'{"Permanent" if g["kind"] == "permanent" else "Strike"}</span></a>'
        for g in groups
    )
    word_tiles = "".join(
        f'<div class="rb-word"><span class="rb-word__icon">{lucide(w["icon"])}</span><b>"{esc(w["word"])}"</b>'
        f'<span class="rb-word__list">'
        + "".join(f"<span>{esc(x.strip())}</span>" for x in w["means"].replace(", etc", "").split(","))
        + "<span>and more</span></span></div>"
        for w in R["reading"]["words"]
    )
    start = (
        '<h3 class="rb-h">How long is a ban?</h3>'
        '<p class="rb-p">For the rules in <b>a</b>, <b>b</b> and <b>c</b>, every new ban is longer than the last one:</p>'
        f'<div class="rb-ladder">{ladder}</div>'
        f'<div class="rb-facts">{facts}</div>'
        '<h3 class="rb-h">The five groups of rules</h3>'
        '<p class="rb-p">Every rule has a <b>ban code</b>: its group letter and a number, like <b>c1</b>. '
        "The code is written in your ban message.</p>"
        f'<div class="rb-gtiles">{tiles}</div>'
        '<h3 class="rb-h">Words used in the rules</h3>'
        '<p class="rb-p">When a rule uses one of these words, it counts in all of these places. The rules apply in every language.</p>'
        f'<div class="rb-words">{word_tiles}</div>'
        f'<p class="rb-source">{lucide("scroll-text")}<span>Copied from the official <b>{esc(src["name"])}</b> posts on '
        f'<a href="{esc(src["invite"])}" target="_blank" rel="noopener">{esc(src["where"])}</a> on '
        f'{esc(src["checked"])}. If anything here is different, the Discord version is the one that counts.</span></p>'
    )
    t, short, icon, sub = RB_EXTRA["start"]
    chapter("start", t, short, icon, sub, f"{len(active)} rules in 5 groups, explained simply.", start, "start")

    # ---------------------------------------------------------------- Groups
    for g in groups:
        live = [r for r in g["rules"] if not r.get("empty")]
        empty = [r["code"] for r in g["rules"] if r.get("empty")]
        cards = "".join(rule_card(r, g, words, faq) for r in live)
        if g["kind"] == "permanent":
            punish = (
                f'<div class="rb-banner rb-banner--perm">{lucide("octagon-x")}<span><b>Permanent right away.</b> '
                + ("Except <b>e5</b>, which is always a 1 year ban." if g["id"] == "e" else "Some of these count even outside the game.")
                + "</span></div>"
            )
        else:
            punish = (
                f'<div class="rb-banner rb-banner--strike">{lucide("timer")}<span><b>Strike bans:</b> {STRIKE}. '
                '<a href="#rb-start">How bans work</a></span></div>'
            )
        unused = ""
        if empty:
            unused = (
                f'<p class="rb-unused">{lucide("info")}<span>Codes not used right now: <b>{", ".join(empty)}</b>. '
                "Rules change over time and some were merged or removed.</span></p>"
            )
        n = len([r for r in live if not r.get("removed")])
        chapter(
            g["id"], g["title"], g["short"], g["id"], f"{n} rules · {'permanent' if g['kind'] == 'permanent' else 'strike bans'}",
            g["about"], punish + f'<div class="rb-rules">{cards}</div>' + unused, f"group rb-ch--{g['id']}", letter=True,
        )

    # ---------------------------------------------------------------- Not bannable
    nb = R["not_bannable"]
    ok_cards = "".join(
        f'<div class="rb-okcard"><span class="rb-okcard__icon">{lucide("circle-check")}</span>'
        f'<span class="rb-okcard__t">{md_inline(x["t"].rstrip("."))}</span><span class="rb-okcard__d">{md_inline(x["d"])}</span></div>'
        for x in nb["items"]
    )
    hide = (
        f'<div class="rb-howto"><p class="rb-howto__head">{lucide("eye-off")}<span>Someone is annoying you? Hide them</span></p>'
        '<ol class="rb-howto__steps"><li>Click on the player, or find them in the <b>Server List</b></li>'
        "<li>Their <b>Profile Card</b> opens</li><li>Click <b>Hide Player</b></li></ol></div>"
    )
    t, short, icon, sub = RB_EXTRA["not"]
    chapter("not", t, short, icon, sub, "These things are not against the rules, so nobody gets banned for them.",
            f'<div class="rb-okcards">{ok_cards}</div>' + hide, "not")

    # ---------------------------------------------------------------- Unbans
    unban_icons = ["file-search", "clock-3", "hand-heart", "scale"]
    unbans = "".join(
        f'<div class="rb-ustep"><span class="rb-ustep__icon">{lucide(unban_icons[i % len(unban_icons)])}</span>'
        f"<span>{rule_note(x)}</span></div>"
        for i, x in enumerate(R["unbans"])
    )
    never = "".join(
        f'<a class="rb-never" href="#{code}"><span class="rb-code rb-code--sm">{code}</span>'
        f'<span>{esc(next((r["title"] for g in groups for r in g["rules"] if r["code"] == code), code))}</span></a>'
        for code in R["never"]
    )
    t, short, icon, sub = RB_EXTRA["unbans"]
    chapter(
        "unbans", t, short, icon, sub, "You can ask for the proof of your ban, and many bans can end early.",
        f'<div class="rb-usteps">{unbans}</div>'
        f'<div class="rb-banner rb-banner--info">{lucide("scale")}<span><b>A ban only counts</b> if what you did matches '
        "one of the bannable examples of its ban code.</span></div>"
        f'<div class="rb-nevers"><p class="rb-nevers__head">{lucide("shield-x")}<span>Never unbanned</span></p>'
        f"<p>{md_inline(R['never_intro'])}</p><div class=\"rb-never-list\">{never}</div>"
        '<p class="rb-nevers__tip">Open each rule to see exactly which cases are never unbanned.</p></div>',
        "unbans",
    )

    # ---------------------------------------------------------------- FAQ
    faq_html = "".join(
        f'<details class="rb-faq" id="faq-{slug(x["q"])}" data-search="{esc((x["q"] + " " + x["a"]).lower())}">'
        f'<summary><span class="rb-faq__q">?</span><span class="rb-faq__t">{md_inline(x["q"])}</span>'
        f'<span class="rb-rule__toggle" aria-hidden="true">{lucide("chevron-down")}</span></summary>'
        f'<div class="rb-rule__body"><div class="rb-rule__inner"><p class="rb-faq__a">{rule_note(x["a"])}</p></div></div></details>'
        for x in R["faq"]
    )
    t, short, icon, sub = RB_EXTRA["faq"]
    chapter("faq", t, short, icon, sub, "Answers from the moderators to the questions they get the most.",
            f'<div class="rb-faqs">{faq_html}</div>', "faq")

    # ---------------------------------------------------------------- Discord
    disc = "".join(f'<li>{rule_note(x)}</li>' for x in R["discord"])
    t, short, icon, sub = RB_EXTRA["discord"]
    chapter("discord", t, short, icon, sub, "How bans work on the community Discord server.",
            f'<ul class="rb-list">{disc}</ul>', "discord")

    # ---------------------------------------------------------------- Index (left page)
    def ix(c: dict, i: int) -> str:
        mark = (
            f'<span class="rb-letter">{c["mark"]}</span>' if c["letter"]
            else f'<span class="rb-ix__icon">{lucide(c["mark"])}</span>'
        )
        return (
            f'<a class="rb-ix rb-ix--{c["cls"].split()[-1].replace("rb-ch--", "")}" href="#{c["id"]}" data-ch="{c["id"]}">'
            f'{mark}<span class="rb-ix__text"><b class="rb-ix__long">{esc(c["title"])}</b><b class="rb-ix__short">{esc(c["short"])}</b>'
            f'<small>{esc(c["sub"])}</small></span><span class="rb-ix__p">{i + 1}</span></a>'
        )

    index = (
        f'<p class="rb-index__head">{lucide("book-open")}<span>Contents</span></p>'
        + ix(chapters[0], 0)
        + '<p class="rb-index__sub">Ban codes</p>'
        + "".join(ix(c, i) for i, c in enumerate(chapters) if c["letter"])
        + '<p class="rb-index__sub">Good to know</p>'
        + "".join(ix(c, i) for i, c in enumerate(chapters) if i and not c["letter"])
    )

    # ---------------------------------------------------------------- Pages
    pages = []
    for i, c in enumerate(chapters):
        prev_c = chapters[i - 1] if i else None
        next_c = chapters[i + 1] if i + 1 < len(chapters) else None
        turn = '<nav class="rb-turn" aria-label="Turn the page">'
        turn += (
            f'<a class="rb-turn__btn rb-turn__btn--prev" href="#{prev_c["id"]}">{lucide("arrow-left")}'
            f'<span><small>Previous</small><b>{esc(prev_c["title"])}</b></span></a>' if prev_c else "<span></span>"
        )
        turn += (
            f'<a class="rb-turn__btn rb-turn__btn--next" href="#{next_c["id"]}"><span><small>Next</small>'
            f'<b>{esc(next_c["title"])}</b></span>{lucide("arrow-right")}</a>' if next_c else "<span></span>"
        )
        turn += "</nav>"
        badge = (
            f'<span class="rb-ch__badge rb-letter">{c["mark"]}</span>' if c["letter"]
            else f'<span class="rb-ch__badge rb-ch__badge--icon">{lucide(c["mark"])}</span>'
        )
        kicker = f"Chapter {i + 1} · ban codes" if c["letter"] else f"Chapter {i + 1}"
        pages.append(
            f'<section class="rb-ch rb-ch--{c["cls"].split()[0]} {c["cls"].split()[-1] if c["letter"] else ""}" id="{c["id"]}" data-title="{esc(c["title"])}">'
            f'<header class="rb-ch__head">{badge}<div><span class="rb-ch__kicker">{esc(kicker)}</span>'
            f'<h2 class="rb-ch__title">{esc(c["title"])}</h2><p class="rb-ch__about">{esc(c["about"])}</p></div></header>'
            f'{c["body"]}{turn}<span class="rb-folio">{i + 1}</span></section>'
        )

    out = [
        '<div class="rb" id="rulebook">',
        f'<div class="rb-uptodate"><span class="rb-uptodate__icon">{lucide("calendar-check")}</span>'
        f'<span class="rb-uptodate__text"><b>Rules as of {esc(src["checked"])}</b>This page has the rules available up to that day. '
        "Rules can change: for the always up-to-date rules, check the official community Discord server.</span>"
        f'<a class="rb-uptodate__btn" href="{esc(src["invite"])}" target="_blank" rel="noopener">{lucide("message-circle")}'
        "<span>Open the Discord</span></a></div>",
        '<div class="rb-finder">'
        f'<div class="rb-finder__copy"><span class="rb-finder__icon">{lucide("gavel")}</span>'
        '<span><b class="rb-finder__title">Got banned?</b>'
        "<span>Type the code from your ban message, like <b>c1</b>, or search any word.</span></span></div>"
        f'<label class="rb-search">{lucide("search")}<input type="search" placeholder="Ban code or word…" '
        'aria-label="Find a rule" autocomplete="off" spellcheck="false"><kbd>/</kbd></label></div>',
        '<div class="rb-book">',
        f'<aside class="rb-index" aria-label="Chapters"><nav class="rb-index__inner">{index}</nav></aside>',
        '<div class="rb-pages">',
        *pages,
        '<section class="rb-ch rb-ch--results" id="rb-results" hidden><header class="rb-ch__head">'
        f'<span class="rb-ch__badge rb-ch__badge--icon">{lucide("search")}</span><div><span class="rb-ch__kicker">Search</span>'
        '<h2 class="rb-ch__title">Results</h2><p class="rb-ch__about rb-results__count"></p></div></header>'
        '<div class="rb-results"></div></section>',
        "</div></div></div>",
    ]
    write("rules-book.md", "\n".join(out))


# --------------------------------------------------------------------------
# Wiki pages: categories, home menu, recent changes
# --------------------------------------------------------------------------


def front_matter(path: Path) -> dict:
    text = path.read_text("utf-8")
    meta: dict = {}
    if text.startswith("---"):
        block = text.split("---", 2)[1]
        for line in block.splitlines():
            if ":" in line and not line.startswith(" "):
                key, value = line.split(":", 1)
                value = value.strip()
                if value.startswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        value = value.strip('"')
                meta[key.strip()] = value
    if re.search(r'^--8<-- "coming-soon\.md"', text, re.M):
        meta["status"] = "soon"
    elif re.search(r'^!!! question "Needs info"', text, re.M):
        meta["status"] = "partial"
    elif re.search(r'^--8<-- "generated/', text, re.M):
        meta["status"] = "live"
    else:
        meta["status"] = "done"
    title = re.search(r"^# (.+)$", text, re.M)
    meta["h1"] = title.group(1).strip() if title else path.stem
    return meta


def read_structure() -> list[dict]:
    config = tomllib.loads((ROOT / "zensical.toml").read_text("utf-8"))
    cats = []
    for entry in config["project"]["nav"]:
        (title, value), = entry.items()
        if not isinstance(value, list):
            continue
        index = next(v for v in value if isinstance(v, str))
        meta = front_matter(DOCS / index)
        pages = []
        for item in value:
            if isinstance(item, dict):
                (ptitle, ppath), = item.items()
                pmeta = front_matter(DOCS / ppath)
                pages.append({"title": ptitle, "path": ppath, **pmeta})
        cats.append({"title": title, "index": index, "slug": index.split("/")[0], **meta, "pages": pages})
    return cats


STATUS_LABEL = {"done": "Ready", "live": "Live data", "partial": "Needs info", "soon": "Coming soon", "now": "Happening now"}


def gen_categories(cats: list[dict]) -> None:
    st = event_state()
    if st["active"]:
        for cat in cats:
            for p in cat["pages"]:
                if p["path"] == st["event"]["page"]:
                    p["status"] = "now"
    for cat in cats:
        out = [f'<div class="mp-cards mp-cat--{esc(cat.get("category", "blue"))}">']
        for i, p in enumerate(cat["pages"]):
            out.append(
                f'<a class="mp-card" href="{rel(cat["index"], p["path"])}" style="--i:{i}">'
                f'<span class="mp-card__icon" aria-hidden="true">{lucide(p.get("icon", "file").replace("lucide/", ""))}</span>'
                f'<span class="mp-card__title">{esc(p["title"])}</span>'
                f'<span class="mp-card__desc">{esc(p.get("description", ""))}</span>'
                f'<span class="mp-status mp-status--{p["status"]}">{STATUS_LABEL[p["status"]]}</span></a>'
            )
        out.append("</div>")
        write(f"cards-{cat['slug']}.md", "\n".join(out))

    # Home page: one colorful card per category, with progress
    total = sum(len(c["pages"]) for c in cats)
    ready = sum(1 for c in cats for p in c["pages"] if p["status"] != "soon")
    out = ['<div class="mp-cats">']
    for i, cat in enumerate(cats):
        n = len(cat["pages"])
        done = sum(1 for p in cat["pages"] if p["status"] != "soon")
        pct = round(done / n * 100) if n else 0
        out.append(
            f'<a class="mp-cat mp-cat--{esc(cat.get("category", "blue"))}" href="{rel("index.md", cat["index"])}" style="--i:{i}">'
            f'<span class="mp-cat__icon" aria-hidden="true">{lucide(cat.get("icon", "folder").replace("lucide/", ""))}</span>'
            f'<span class="mp-cat__title">{esc(cat["title"])}</span>'
            f'<span class="mp-cat__desc">{esc(cat.get("description", ""))}</span>'
            f'<span class="mp-cat__meta"><span>{n} pages</span><span>{done} ready</span></span>'
            f'<span class="mp-progress" aria-label="{pct}% ready"><span style="width:{pct}%"></span></span></a>'
        )
    out.append("</div>")
    write("home-categories.md", "\n".join(out))
    pct = round(ready / total * 100) if total else 0
    write(
        "progress.md",
        f'<div class="mp-bigprogress"><span class="mp-bigprogress__label"><b>{ready}</b> of <b>{total}</b> pages ready</span>'
        f'<span class="mp-progress mp-progress--big" aria-label="{pct}% ready"><span style="width:{pct}%"></span></span></div>',
    )


def git_changes(limit: int) -> list[tuple[str, str, str]]:
    try:
        out = subprocess.run(
            ["git", "log", f"-n{limit * 3}", "--date=short", "--pretty=format:%h|%ad|%s", "--", "docs", "includes/coming-soon.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for line in out.splitlines():
        sha, date, subject = line.split("|", 2)
        if subject.startswith("Update game data"):
            continue
        rows.append((sha, date, subject))
    return rows[:limit]


def gen_changes() -> None:
    rows = git_changes(25)
    if not rows:
        write("recent-changes.md", "Recent changes appear here once the wiki is built from its repository.")
        write("latest-changes.md", "")
        return
    out = ['<div class="mp-timeline">']
    for sha, date, subject in rows:
        out.append(
            f'<div class="mp-timeline__item"><span class="mp-timeline__date">{esc(nice_date(date + "T00:00:00Z"))}</span>'
            f'<span class="mp-timeline__text"><a href="{REPO_URL}/commit/{sha}" target="_blank" rel="noopener">{esc(subject)}</a></span></div>'
        )
    out.append("</div>")
    write("recent-changes.md", "\n".join(out))
    latest = "\n".join(
        f'<li><span class="mp-news__date">Wiki · {esc(nice_date(d + "T00:00:00Z"))}</span>{esc(s)}</li>' for _, d, s in rows[:3]
    )
    write("latest-changes.md", latest)


def gen_home_news(snap: dict, badges: list[dict]) -> None:
    game = snap.get("game", {})
    newest = max((b for b in badges if parse_time(b.get("created"))), key=lambda b: parse_time(b["created"]), default=None)
    items = [
        f'<li><span class="mp-news__date">Game</span>Last updated {time_tag(game.get("updated"))}</li>',
    ]
    if newest:
        items.append(
            f'<li><span class="mp-news__date">New badge</span><a href="{rel("index.md", newest["page"], newest["anchor"])}">'
            f'{esc(newest["short"])}</a>, added {esc(nice_date(newest["created"]))}</li>'
        )
    write("home-news.md", "\n".join(items))


def main() -> int:
    offline = "--offline" in sys.argv
    DATA_DIR.mkdir(exist_ok=True)
    snap, game_fetched = update_snapshot(offline)
    if not offline and snap:
        SNAPSHOT.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n", "utf-8")
    new_day = update_history(snap, game_fetched) if snap else False
    history = json.loads(HISTORY.read_text("utf-8")) if HISTORY.exists() else []
    discord_changed = False if offline else update_discord()

    badges = prepare_badges(snap) if snap else []
    gen_stats(snap, history)
    gen_badges(snap, badges)
    gen_titles(badges)
    gen_badge_hunting(badges)
    gen_badge_timeline(badges)
    gen_passes(snap)
    gen_pass_icons(snap)
    gen_creator_games(snap)
    gen_update_history(snap, history)
    gen_discord()
    gen_events()
    gen_galleries()
    gen_rules()
    gen_home_news(snap, badges)
    gen_categories(read_structure())
    gen_changes()

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"new_day={'true' if new_day else 'false'}\n")
            fh.write(f"discord_changed={'true' if discord_changed else 'false'}\n")
    print(f"done (new day of history: {new_day})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
