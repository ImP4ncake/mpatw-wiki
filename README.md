# MPATW Wiki

Unofficial fan wiki for the Roblox game **Meet People Across The World**.

**Read the wiki:** https://imp4ncake.github.io/mpatw-wiki/

> This is a fan project. It is not affiliated with, endorsed by or connected to Roblox Corporation or Nogo.

## Contributing

Anyone with a GitHub account can help. The easiest way is to click the edit button on any wiki page. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules.

## How the site works

The wiki is built with [Zensical](https://zensical.org) and hosted for free on GitHub Pages.

| Path | What it is |
|---|---|
| `docs/` | The wiki pages, written in Markdown |
| `docs/assets/images/` | Screenshots and images |
| `zensical.toml` | Site settings and the navigation menu |
| `templates/page-template.md` | Starting point for new pages |
| `requirements.txt` | The pinned Zensical version |
| `.github/workflows/docs.yml` | Builds and publishes the site on every push to `main` |

### Preview on your computer (optional)

You need Python 3 installed.

```bash
pip install -r requirements.txt
zensical serve
```

Then open http://localhost:8000 in your browser. The preview reloads automatically when you save a file.

### Updating Zensical

Zensical is still in early development (0.x versions), so the version is pinned in `requirements.txt`. To upgrade, change the version there, run `zensical build` locally to check that nothing breaks, then push.

## License

- Wiki text: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- Site code and configuration: Apache License 2.0 (see [LICENSE](LICENSE))
