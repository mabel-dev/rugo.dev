# rugo.dev

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/rugo?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREY&left_text=downloads)](https://pepy.tech/projects/rugo)

This repository hosts the [rugo.dev](https://rugo.dev) documentation site, published via GitHub Pages from the `/docs` folder on the `main` branch.

Rugo is developed as part of [opteryx-core](https://github.com/mabel-dev/opteryx-core). Source code, examples, and issue tracking are all there.

## Guides

The guides hub at [rugo.dev/guides](https://rugo.dev/guides/) is built from Markdown files in `guides/`. To add a guide, copy `guides/_template.md`, fill it in, then:

```bash
pip install markdown pyyaml
python3 tools/build_guides.py     # regenerates docs/guides/: hub, filter tabs, counts, guide page
python3 tools/verify_guides.py    # runs every command in every guide against the rugo on your PATH
```

Commit the regenerated `docs/guides/` with the guide. Nothing in `docs/guides/` is edited by hand.
