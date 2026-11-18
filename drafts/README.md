# Blog drafts

Posts here are **drafts**: nothing in `drafts/` is served (the site is built from `docs/`).
See [BACKLOG.md](BACKLOG.md) for the ten ideas, their status and which ones can become guides.

| Folder | Post | Status |
|--------|------|--------|
| `s3-lambda-parquet-validation/` | `validate-parquet-in-s3-with-lambda.html` | ready for review |
| `jsonl-ci-validation/` | `fail-the-build-on-bad-jsonl.html` | draft |
| `schema-drift-rugo-diff/` | `catch-schema-drift-with-rugo-diff.html` | draft |

Each folder holds the post (named for its final URL slug) and the code the post links to.

## Check the commands

Every runnable command in a post is replayed against the rugo on your PATH:

```bash
python3 -m venv /tmp/v && /tmp/v/bin/pip install -U rugo actionlint-py boto3 'moto[s3]' pytest
PATH=/tmp/v/bin:$PATH /tmp/v/bin/python drafts/verify_drafts.py
```

Code blocks marked `language-bash` are run (an adjacent `language-output` block is the expected
output), `data-save` / `data-append` blocks are written to disk as a reader would save them, and
saved workflow files are linted with `actionlint`. AWS CLI steps are not replayed (they need an
account); they were checked against `aws ... help` only. Last run: rugo 0.5.12, all three posts pass.

## To publish a draft

1. Move `<slug>.html` to `docs/blog/`, and the folder's code to `docs/blog/code/<folder>/`
   (the posts link to `code/<folder>/...`). Leave `.github/` and `data/` out of `docs/`; the workflows
   are shown in the post, and the data is created by the post's own commands.
2. Set the date in the post header (all three say 18 November 2026) and add a card to `docs/blog/index.html`.
3. Re-run `verify_drafts.py` against the newest rugo and update "tested with rugo X" in the post notice.
4. The posts cross-link by slug (`validate-parquet-in-s3-with-lambda.html`, `fail-the-build-on-bad-jsonl.html`,
   `catch-schema-drift-with-rugo-diff.html`); publish all three or remove the links to the unpublished ones.
