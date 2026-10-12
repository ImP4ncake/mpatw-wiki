---
icon: lucide/pencil
description: "Step-by-step instructions for new contributors."
---

# How to Contribute

Anyone can help improve this wiki. You need a free [GitHub account](https://github.com/signup), but you don't need to install anything.

## Editing a page

1. Open the page you want to improve and click the :lucide-file-pen: **edit** button at the top right.
2. GitHub opens the page's text. If it asks, click **Fork this repository** (this makes your own copy to edit).
3. Make your changes. Pages are written in [Markdown](#formatting-cheat-sheet), a very simple text format.
4. Click **Commit changes**, write a short description of what you changed, then **Propose changes**.
5. Click **Create pull request**.

A wiki maintainer reviews every change. Once it is approved, the site updates automatically within a couple of minutes.

## Writing a "coming soon" page

Pages that are still empty end with this line:

```markdown
;--8<-- "coming-soon.md"
```

Replace it with your text. As soon as the line is gone, the page counts as written: its card, the [Missing Pages](missing-pages.md) list and the progress bar on the home page update on their own.

## Formatting cheat sheet

```markdown
## A section title

Some text with **bold** and *italic*.

- A bullet point
- Another one

| Column | Column |
|---|---|
| Cell | Cell |

[A link to another page](../mechanics/coins.md)

![Description of the image](../assets/images/my-screenshot.webp)

;--8<-- "generated/badge/pianist.md"

!!! question "Needs info"

    Use this box to mark something that is still missing.
```

The `generated/badge/...` line inserts a live badge card. The names of all badge cards are the badge names in lowercase with dashes, for example `limited-trick-or-treat`.

## Creating a new page

1. Start from a template in the [`templates/`](https://github.com/ImP4ncake/mpatw-wiki/tree/main/templates) folder (page, badge, item or event).
2. Save it inside the right category folder in `docs/`, with an `icon` and a `description` at the top.
3. Add it to the `nav` list in `zensical.toml`, under its category. Its card appears on the category page automatically.

## Pages that update automatically

The badge lists, titles, tag effects, gamepasses, stats, update history, missing pages and recent changes are filled in automatically every hour. Don't edit those parts by hand: they would be overwritten.

To change how a badge or gamepass is described, edit the `BADGE_INFO` or `PASS_INFO` lists in [`scripts/update_data.py`](https://github.com/ImP4ncake/mpatw-wiki/blob/main/scripts/update_data.py).

## Not comfortable editing?

[Open an issue](https://github.com/ImP4ncake/mpatw-wiki/issues/new) on GitHub with the information or correction, and a maintainer will add it for you.
