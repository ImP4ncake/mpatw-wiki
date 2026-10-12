#!/usr/bin/env python3
"""Keep the wiki up to date.

1. Fetches public data about the 18+ version of Meet People Across The World
   from the official Roblox web APIs (no login needed).
2. Regenerates the snippets that the wiki pages include, in includes/generated/:
   stats, badges, titles, tag effects, gamepasses, limited rewards, update
   history, category cards, missing pages and recent changes.

    data/game.json      latest snapshot of everything fetched from Roblox
    data/history.json   one data point per day (stats chart, update history)

Run it with:

    python scripts/update_data.py            # fetch fresh data, then generate
    python scripts/update_data.py --offline  # only regenerate from saved data

The script never fails the build: if Roblox can't be reached, it keeps the
last saved snapshot and regenerates the pages from that.

To change how a badge or gamepass is described, edit BADGE_INFO or PASS_INFO
below. New badges and gamepasses appear on the wiki automatically. Category
cards, "Missing Pages" and the home page menu are built from the nav in
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
import urllib.parse
import urllib.request
from pathlib import Path

# The 18+ version of the game
UNIVERSE_ID = 6690355795
PLACE_ID = 110570058234582

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA_DIR = ROOT / "data"
GEN_DIR = ROOT / "includes" / "generated"
SNAPSHOT = DATA_DIR / "game.json"
HISTORY = DATA_DIR / "history.json"
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
    "Gamepass Info [READ DESC]": "Not a real pass: a notice that gamepasses bought in the standard version carry over",
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


def update_snapshot(offline: bool) -> tuple[dict, bool]:
    """Returns (snapshot, game_fetched)."""
    snap = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else {}
    if offline:
        return snap, False
    if snap.get("universe_id") not in (None, UNIVERSE_ID):
        snap = {}  # saved data belongs to another version of the game
    snap["universe_id"] = UNIVERSE_ID

    fetched_game = False
    for key, fetcher in (("game", fetch_game), ("votes", fetch_votes), ("badges", fetch_badges), ("passes", fetch_passes)):
        try:
            value = fetcher()
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not fetch {key}, keeping the last saved data ({exc})")
            continue
        if key in ("badges", "passes"):  # keep known icons if the icon service failed
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
    """Relative link between two pages, as it works on the published site."""
    a = page_url(from_page) or "./"
    b = page_url(to_page) or "./"
    r = posixpath.relpath(b, a)
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


def badge_reward(description: str) -> dict:
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


def prepare_badges(snap: dict) -> list[dict]:
    badges = snap.get("badges", [])
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
                "reward": badge_reward(b["description"]),
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


def gen_titles(badges: list[dict]) -> None:
    here = "badges/titles.md"
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
            f'<span class="mp-title-card__title">{esc(t)}</span>'
            f'<span class="mp-title-card__tag">{esc(b["reward"]["tag"] or "")}</span>'
            f'<span class="mp-title-card__from">{esc(b["short"])}</span>{rarity_chip(b)}</a>'
        )
    out.append("</div>")
    write("titles.md", "\n".join(out))

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
    months: dict[str, list[dict]] = {}
    for b in badges:
        t = parse_time(b.get("created"))
        if t:
            months.setdefault(t.strftime("%Y-%m"), []).append(b)
    if not months:
        write("badge-timeline.md", "The badge timeline appears here once the wiki has downloaded the badge data.")
        return
    out = ['<div class="mp-timeline">']
    for key in sorted(months):
        t = dt.datetime.strptime(key, "%Y-%m")
        names = ", ".join(f"<b>{esc(b['short'])}</b>" for b in months[key])
        noun = "badge" if len(months[key]) == 1 else "badges"
        out.append(
            f'<div class="mp-timeline__item"><span class="mp-timeline__date">{t.strftime("%B %Y")}</span>'
            f'<span class="mp-timeline__text">{len(months[key])} new {noun}: {names}</span></div>'
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
        f'<p class="mp-updated">Updated {time_tag(snap.get("fetched_at"))}. The wiki refreshes these numbers every 6 hours.</p>',
    ]
    write("stats.md", "\n".join(grid))

    on_sale = sum(1 for p in snap.get("passes", []) if p.get("for_sale"))
    facts = [
        "| Game | 18+ Meet People Across The World |",
        "|---|---|",
        f"| **Developer** | {esc(game.get('creator') or 'Nogo')} |",
        f"| **Released** | {nice_date(game.get('created'))} |",
        f"| **Last game update** | {time_tag(game.get('updated'))} |",
        "| **Age requirement** | 18+ |",
        f"| **Players per server** | {full(game.get('max_players'))} |",
        f"| **Visits** | {full(game.get('visits'))} |",
        f"| **Favorites** | {full(game.get('favorites'))} |",
        f"| **Like ratio** | {f'{r:.1f}%' if r is not None else '?'} |",
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
# Wiki pages: categories, home menu, missing pages, recent changes
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


STATUS_LABEL = {"done": "Ready", "live": "Live data", "partial": "Needs info", "soon": "Coming soon"}


def gen_categories(cats: list[dict]) -> None:
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

    # Missing pages
    here = "wiki/missing-pages.md"
    missing = [(c, p) for c in cats for p in c["pages"] if p["status"] == "soon"]
    out = [f'<p class="mp-lead"><b>{len(missing)}</b> pages are still waiting to be written. Pick one and help!</p>', ""]
    for cat in cats:
        items = [p for c, p in missing if c is cat]
        if not items:
            continue
        out.append(f'<div class="mp-missing mp-cat--{esc(cat.get("category", "blue"))}">')
        out.append(f'<span class="mp-missing__cat">{esc(cat["title"])}</span>')
        out.append(
            "".join(f'<a class="mp-missing__page" href="{rel(here, p["path"])}">{esc(p["title"])}</a>' for p in items)
        )
        out.append("</div>")
    write("missing-pages.md", "\n".join(out))


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

    badges = prepare_badges(snap) if snap else []
    gen_stats(snap, history)
    gen_badges(snap, badges)
    gen_titles(badges)
    gen_badge_hunting(badges)
    gen_badge_timeline(badges)
    gen_passes(snap)
    gen_update_history(snap, history)
    gen_home_news(snap, badges)
    gen_categories(read_structure())
    gen_changes()

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"new_day={'true' if new_day else 'false'}\n")
    print(f"done (new day of history: {new_day})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
