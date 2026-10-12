---
icon: lucide/pencil
---

# How to contribute

Anyone can help improve this wiki. You need a free [GitHub account](https://github.com/signup), but you don't need to install anything.

## Editing a page

1. Open the page you want to improve and click the :lucide-pencil: **edit** button at the top right.
2. GitHub opens the page's text. If it asks, click **Fork this repository** (this makes your own copy to edit).
3. Make your changes. Pages are written in [Markdown](#formatting-cheat-sheet), a very simple text format.
4. Click **Commit changes**, write a short description of what you changed, then **Propose changes**.
5. Click **Create pull request**.

A wiki maintainer will review your change. Once it is approved, the site updates automatically within a couple of minutes.

## Wiki rules

1. **Only add things you have checked.** Write what you saw in the game, not rumors. If you're not sure, say so or leave it out.
2. **Add dates to things that change.** Codes, prices and "rarest badge" facts go out of date, so write when you checked them (for example "October 2026").
3. **No personal information.** Don't write about specific players, their countries or anything that could identify them. The only exceptions are the game's developer and the [Meet People Legends](sections/legends.md) section, where a player can appear only if they agree to it.
4. **No exploits, hacks or leaks.** Don't post ways to break the game's rules or unreleased content.
5. **Use your own screenshots.** Keep them small (cropped, and saved as `.webp` or `.png`) and put them in `docs/assets/images/`.
6. **Write in English**, in a friendly and neutral tone.
7. **Keep it safe for everyone.** Many players are young, so keep the content appropriate for all ages.

## Formatting cheat sheet

```markdown
## A section title

Some text with **bold** and *italic*.

- A bullet point
- Another one

| Column | Column |
|---|---|
| Cell | Cell |

[A link to another page](../badges.md)

![Description of the image](assets/images/my-screenshot.webp)

!!! question "Needs info"

    Use this box to mark something that is still missing.
```

## Creating a new page

1. Copy the template from [`templates/page-template.md`](https://github.com/ImP4ncake/mpatw-wiki/blob/main/templates/page-template.md) into a new file inside the `docs/` folder.
2. Add the page to the `nav` list in `zensical.toml` so it shows up in the menu.
3. Open a pull request as described above.

## Pages that update automatically

The **Badges**, **Gamepasses** and **Game stats** pages are filled in automatically from the official Roblox data every few hours. Don't edit their tables by hand: your changes would be overwritten.

To change how a badge or gamepass is described, edit the `BADGE_INFO` or `PASS_INFO` lists in [`scripts/update_data.py`](https://github.com/ImP4ncake/mpatw-wiki/blob/main/scripts/update_data.py). New badges and gamepasses appear on the wiki on their own.

## Not comfortable editing?

You can also [open an issue](https://github.com/ImP4ncake/mpatw-wiki/issues/new) on GitHub with the information or correction, and a maintainer will add it for you.
