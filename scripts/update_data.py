#!/usr/bin/env python3
"""Keep the wiki's game data up to date.

Fetches public data about Meet People Across The World from the official
Roblox web APIs (no login needed) and regenerates the snippets that the wiki
pages include:

    data/game.json            latest snapshot of everything we fetched
    data/history.json         one data point per day, used for the stats chart
    includes/generated/*.md   tables and stat blocks included by the pages

Run it with:

    python scripts/update_data.py            # fetch fresh data, then generate
    python scripts/update_data.py --offline  # only regenerate from data/game.json

The script never fails the build: if Roblox can't be reached, it keeps the
last saved snapshot and regenerates the pages from that.

To change how a badge or gamepass is described, edit BADGE_INFO or PASS_INFO
below. New badges and gamepasses appear on the wiki automatically.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UNIVERSE_ID = 6500938341
PLACE_ID = 78699621133325

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GEN_DIR = ROOT / "includes" / "generated"
SNAPSHOT = DATA_DIR / "game.json"
HISTORY = DATA_DIR / "history.json"

USER_AGENT = "MPATW-Wiki-Updater/1.0 (+https://github.com/ImP4ncake/mpatw-wiki)"

# --------------------------------------------------------------------------
# Hand-written info. Anything not listed here still shows up automatically,
# using the official description from Roblox.
# --------------------------------------------------------------------------

BADGE_CATEGORIES = [
    "Getting started",
    "Reputation",
    "Arenas",
    "Activities",
    "Rare and prestige",
    "Limited (events)",
    "New badges",
    "No longer available",
]

# name -> (category, how to get it)
BADGE_INFO = {
    "Welcome to Meet People Across The World!": ("Getting started", "Join the game for the first time"),
    "Invite a Friend!": ("Getting started", "Invite a friend to the game"),
    "Played in VR": ("Getting started", "Join the game in VR"),
    "Pet The Cat": ("Getting started", "Pet the cat"),
    "Pet The Dog": ("Getting started", "Pet the dog"),
    "Pianist": ("Getting started", "Play the piano"),
    "Coder": ("Getting started", "Redeem a code from the community server"),
    "Gifter": ("Getting started", "Gift anyone"),
    "Famous": ("Reputation", "Reach 10,000 reputation"),
    "Infamous": ("Reputation", "Reach -10,000 reputation"),
    "Swordmaster": ("Arenas", "Defeat 50 players in the Sword Arena"),
    "Gunsmith": ("Arenas", "Defeat 50 players in the Gun Arena"),
    "Boxer": ("Arenas", "Defeat 50 players in the Boxing Arena"),
    "Sniper": ("Arenas", "Defeat 50 players in the Sniper Arena"),
    "Arsonist": ("Arenas", "Defeat 50 players in the Bomb Arena"),
    "Warrior": ("Arenas", "Defeat 50 players in the Greatsword Arena"),
    "Artist": ("Activities", "Draw 1,000 times in the Draw Area"),
    "Drink Maker": ("Activities", "Serve 50 drinks at the Drink Area"),
    "Troller": ("Activities", "Troll other players 50 times"),
    "Robot": ("Activities", "Talk to the AI Chatbot 50 times"),
    "Builder": ("Activities", "Build 10 blocks with the Hammer"),
    "Grandmaster": ("Activities", "Win 25 chess games"),
    "Wayfarer": ("Activities", "Reach a 50 streak in Country Trivia"),
    "Win the Lottery": ("Activities", "Roll 777 on the Lottery"),
    "AFK": ("Activities", "Earn 1,000 coins in the AFK World"),
    "Rainmaker": ("Activities", "Make it rain any currency"),
    "Fabled": ("Activities", "Unlock a cosmetic with Fabled rarity"),
    "Explorer": ("Rare and prestige", "Discover all 250 countries"),
    "Angel": ("Rare and prestige", "Be #1 on a non-timed leaderboard"),
    "Fallen Angel": ("Rare and prestige", "Lose #1 on a non-timed leaderboard while it updates in-game"),
    "Sovereign": ("Rare and prestige", "Finish #1 at the end of a Ranked Season"),
    "Winner": ("Rare and prestige", "Win a community server event"),
    "Honored": ("Rare and prestige", "Become a moderator for the game"),
    "[LIMITED] Claim The Christmas Gift": ("Limited (events)", "Give a gift during the Christmas event"),
    "[LIMITED] Loved": ("Limited (events)", "Buy or receive the Valentine's Pack"),
    "[LIMITED] Blessed": ("Limited (events)", "Roll 7777 on the Saint Patrick's Lottery"),
    "[LIMITED] Win The Lottery?": ("Limited (events)", "April Fools' joke badge"),
    "[LIMITED] Easter Collector": ("Limited (events)", "Find all 50 Easter Eggs"),
    "[LIMITED] Trick or Treat!": ("Limited (events)", "Win a special treat at the Spooky Shed"),
    "[LIMITED] WC2026": ("Limited (events)", "Guess a winning team in the 2026 World Cup"),
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
}

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

    fetched_game = False
    for key, fetcher in (("game", fetch_game), ("votes", fetch_votes), ("badges", fetch_badges), ("passes", fetch_passes)):
        try:
            value = fetcher()
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not fetch {key}, keeping the last saved data ({exc})")
            continue
        # Keep known icons if the icon service failed this time.
        if key in ("badges", "passes"):
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
        }
    )
    history.sort(key=lambda p: p["date"])
    HISTORY.write_text(json.dumps(history, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return True


# --------------------------------------------------------------------------
# Formatting helpers
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
            value = n / limit
            return (f"{value:.1f}".rstrip("0").rstrip(".")) + suffix
    return str(n)


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


def badge_reward(description: str) -> str:
    """Reads 'Grants access to the "X" Title + "🍀" Tag effect' style text."""
    parts = []
    for line in description.splitlines():
        # Only the reward lines ("Grants access to ...", "Unlocks ..."), not
        # requirement lines like "Earn 1000 Coins in the AFK World".
        if not re.search(r"grant|unlock|title|effect", line, re.I):
            continue
        tag = re.search(r'"([^"]+)"\s*(?:Tag|Effect)', line, re.I)
        quoted = re.findall(r'"([^"]+)"', line)
        titles = [q for q in quoted if not tag or q != tag.group(1)]
        if titles and "title" in line.lower():
            parts.append(" + ".join(f"<b>{esc(t)}</b>" for t in titles) + (" titles" if len(titles) > 1 else " title"))
        if tag:
            parts.append(f'<span class="mp-tag">{esc(tag.group(1))}</span> tag')
        coins = re.search(r"(\d[\d,]*)\s*Coins", line, re.I)
        if coins:
            parts.append(f"{esc(coins.group(1))} coins")
    return ", ".join(parts) if parts else "None"


RARITY_TIERS = [
    (25.0, "Common", "common"),
    (2.0, "Uncommon", "uncommon"),
    (0.2, "Rare", "rare"),
    (0.01, "Epic", "epic"),
    (0.0, "Legendary", "legendary"),
]


def rarity(awarded, base) -> str:
    if not isinstance(awarded, int) or not isinstance(base, int) or base <= 0:
        return ""
    share = awarded / base * 100
    for limit, label, css in RARITY_TIERS:
        if share >= limit:
            pct = f"{share:.2f}%" if share >= 0.01 else "&lt;0.01%"
            return f'<span class="mp-rarity mp-rarity--{css}" title="{pct} of players who joined have it">{label}</span>'
    return ""


def lucide(name: str) -> str:
    """Inline SVG of a Lucide icon, taken from the installed Zensical theme."""
    try:
        import zensical  # noqa: PLC0415 - only needed here

        path = Path(zensical.__file__).parent / "templates" / ".icons" / "lucide" / f"{name}.svg"
        return path.read_text("utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def icon_img(url: str | None, alt: str) -> str:
    if url:
        return f'<img class="mp-thumb" src="{esc(url)}" alt="{esc(alt)}" width="56" height="56" loading="lazy">'
    return '<span class="mp-thumb mp-thumb--empty" aria-hidden="true"></span>'


def write(name: str, content: str) -> None:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    (GEN_DIR / name).write_text(content.rstrip() + "\n", "utf-8")


# --------------------------------------------------------------------------
# Page snippets
# --------------------------------------------------------------------------


def gen_home_stats(snap: dict) -> None:
    game, votes = snap.get("game", {}), snap.get("votes", {})
    r = rating(votes)
    stats = [
        ("users", "mp-stat--green", game.get("playing"), "playing now"),
        ("eye", "mp-stat--blue", game.get("visits"), "visits"),
        ("star", "mp-stat--gold", game.get("favorites"), "favorites"),
    ]
    out = ['<div class="mp-stats">']
    for icon, cls, value, label in stats:
        out.append(
            f'<div class="mp-stat {cls}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
            f'<span class="mp-stat__value" data-count="{value if isinstance(value, int) else ""}" data-compact>{compact(value)}</span>'
            f'<span class="mp-stat__label">{label}</span></div>'
        )
    if r is not None:
        out.append(
            '<div class="mp-stat mp-stat--red"><span class="mp-stat__icon" aria-hidden="true">' + lucide("thumbs-up") + "</span>"
            f'<span class="mp-stat__value" data-count="{r:.1f}" data-suffix="%" data-decimals="1">{r:.1f}%</span>'
            '<span class="mp-stat__label">like it</span></div>'
        )
    out.append("</div>")
    out.append(f'<p class="mp-updated">Live data from Roblox, updated {time_tag(snap.get("fetched_at"))}</p>')
    write("home-stats.md", "\n".join(out))


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
    # round the axis max up to a nice number
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
        # rounded top, square bottom anchored to the baseline
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


def gen_stats(snap: dict, history: list[dict]) -> None:
    game, votes = snap.get("game", {}), snap.get("votes", {})
    r = rating(votes)
    cards = [
        ("users", "green", full(game.get("playing")), "Playing now", game.get("playing")),
        ("eye", "blue", full(game.get("visits")), "Total visits", game.get("visits")),
        ("star", "gold", full(game.get("favorites")), "Favorites", game.get("favorites")),
        ("thumbs-up", "red", f"{r:.1f}%" if r is not None else "?", "Like ratio", None),
        ("heart", "pink", full(votes.get("up")), "Likes", votes.get("up")),
        ("thumbs-down", "slate", full(votes.get("down")), "Dislikes", votes.get("down")),
    ]
    out = ['<div class="mp-stats mp-stats--grid">']
    for icon, color, text, label, count in cards:
        count_attr = f' data-count="{count}"' if isinstance(count, int) else ""
        out.append(
            f'<div class="mp-stat mp-stat--{color}"><span class="mp-stat__icon" aria-hidden="true">{lucide(icon)}</span>'
            f'<span class="mp-stat__value"{count_attr}>{text}</span><span class="mp-stat__label">{label}</span></div>'
        )
    out.append("</div>\n")
    out.append(f'<p class="mp-updated">Updated {time_tag(snap.get("fetched_at"))}. The wiki refreshes these numbers automatically every few hours.</p>\n')
    out.append("| Game info | |")
    out.append("|---|---|")
    out.append(f"| **Developer** | {esc(game.get('creator') or 'Nogo')} |")
    out.append(f"| **Released** | {nice_date(game.get('created'))} |")
    out.append(f"| **Last game update** | {time_tag(game.get('updated'))} |")
    out.append(f"| **Players per server** | {full(game.get('max_players'))} |")
    out.append(f"| **Badges** | {len(snap.get('badges', []))} |")
    on_sale = sum(1 for p in snap.get("passes", []) if p.get("for_sale"))
    out.append(f"| **Gamepasses** | {len(snap.get('passes', []))} ({on_sale} on sale) |")
    write("stats.md", "\n".join(out))

    chart = ["## Visits per day", "", bar_chart(history), ""]
    if len(history) >= 1:
        chart += ["??? info \"Daily data collected by the wiki\"", ""]
        chart += ["    | Date | Visits | Favorites | Likes | Dislikes |", "    |---|---|---|---|---|"]
        for p in reversed(history[-30:]):
            chart.append(
                f"    | {nice_date(p['date'] + 'T00:00:00Z')} | {full(p.get('visits'))} | {full(p.get('favorites'))} "
                f"| {full(p.get('up'))} | {full(p.get('down'))} |"
            )
    write("stats-history.md", "\n".join(chart))


def gen_badges(snap: dict) -> None:
    badges = snap.get("badges", [])
    if not badges:
        write("badges.md", "Badge data is not available yet.")
        return
    base = next((b.get("awarded") for b in badges if b["name"].startswith("Welcome")), None)
    if not isinstance(base, int):
        base = max((b.get("awarded") or 0 for b in badges), default=0)
    groups: dict[str, list[dict]] = {c: [] for c in BADGE_CATEGORIES}
    for b in badges:
        category, how = BADGE_INFO.get(b["name"], (None, None))
        if not b["enabled"]:
            category = "No longer available"
        elif category is None:
            category = "Limited (events)" if b["name"].startswith("[LIMITED]") else "New badges"
        groups[category].append({**b, "how": how or first_line(b["description"]) or "?"})

    enabled = sum(1 for b in badges if b["enabled"])
    out = [
        f'<p class="mp-lead">The game has <b>{enabled} badges</b> you can earn right now. '
        f'Data updated {time_tag(snap.get("fetched_at"))}.</p>',
        "",
    ]
    for category in BADGE_CATEGORIES:
        items = groups[category]
        if not items:
            continue
        out += [f"## {category}", ""]
        if category == "Limited (events)":
            out += ["These can only be earned while their [event](features/events.md) is running.", ""]
        if category == "New badges":
            out += ["Recently added badges. The wiki lists them automatically: help us describe them!", ""]
        out += ["| | Badge | How to get it | Reward | Owned by | Rarity |", "|---|---|---|---|---|---|"]
        for b in items:
            name = f"[{esc(b['name'])}](https://www.roblox.com/badges/{b['id']})" if b.get("id") else esc(b["name"])
            out.append(
                f"| {icon_img(b.get('icon'), b['name'])} | {name} | {esc(b['how'])} | "
                f"{badge_reward(b['description'])} | {full(b.get('awarded'))} | {rarity(b.get('awarded'), base)} |"
            )
        out.append("")
    write("badges.md", "\n".join(out))


def gen_passes(snap: dict) -> None:
    passes = snap.get("passes", [])
    if not passes:
        write("gamepasses.md", "Gamepass data is not available yet.")
        return
    on_sale = sorted((p for p in passes if p["for_sale"] and isinstance(p.get("price"), int)), key=lambda p: p["price"])
    off_sale = [p for p in passes if p not in on_sale]

    def card(p: dict) -> str:
        desc = PASS_INFO.get(p["name"]) or first_line(p.get("description") or "") or ""
        price = (
            f'<span class="mp-price"><span class="mp-robux" aria-hidden="true"></span>{full(p["price"])}</span>'
            if p in on_sale
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

    out = [
        f'<p class="mp-lead"><b>{len(on_sale)}</b> gamepasses on sale and <b>{len(off_sale)}</b> off sale. '
        f'Prices updated {time_tag(snap.get("fetched_at"))}.</p>',
        "",
        "## On sale",
        "",
        '<div class="mp-passes">' + "".join(card(p) for p in on_sale) + "</div>",
        "",
    ]
    if off_sale:
        out += [
            "## Not for sale",
            "",
            "These gamepasses exist but can't be bought right now. Some were sold in the past, during events or as part of a bundle.",
            "",
            '<div class="mp-passes mp-passes--off">' + "".join(card(p) for p in off_sale) + "</div>",
        ]
    write("gamepasses.md", "\n".join(out))


def main() -> int:
    offline = "--offline" in sys.argv
    DATA_DIR.mkdir(exist_ok=True)
    snap, game_fetched = update_snapshot(offline)
    if not snap:
        print("No data available yet; nothing to generate.")
        return 0
    if not offline:
        SNAPSHOT.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n", "utf-8")
    new_day = update_history(snap, game_fetched)
    history = json.loads(HISTORY.read_text("utf-8")) if HISTORY.exists() else []

    gen_home_stats(snap)
    gen_stats(snap, history)
    gen_badges(snap)
    gen_passes(snap)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"new_day={'true' if new_day else 'false'}\n")
    print(f"done (new day of history: {new_day})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
