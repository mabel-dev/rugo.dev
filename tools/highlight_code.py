"""Syntax-highlight code blocks in blog posts, at build time (no JavaScript).

    python3 tools/highlight_code.py docs/blog/some-post.html [more.html ...]

Finds `<pre><code ...>` blocks whose language is known and rewrites their contents with
the token spans blog.css already styles (`pre .c` comment, `.k` keyword, `.s` string,
`.f` function / command, `.n` number or constant). The language comes from
`class="language-bash|python|yaml|json"` or, for `data-save="path"` blocks, the file
extension. `language-output` blocks and blocks with no language are left alone, and a block
that already contains spans is skipped, so running it twice changes nothing.

Needs `pip install pygments`. Pygments only tokenises; the colours stay in docs/blog.css.
"""
import html
import re
import sys
from pathlib import Path

from pygments import lex
from pygments.lexers import BashLexer, JsonLexer, PythonLexer, YamlLexer
from pygments.token import Comment, Keyword, Name, Number, String, Token

LEXERS = {"bash": BashLexer, "python": PythonLexer, "yaml": YamlLexer, "json": JsonLexer}
EXT = {".py": "python", ".sh": "bash", ".yml": "yaml", ".yaml": "yaml", ".json": "json"}
BLOCK = re.compile(r"<pre><code([^>]*)>(.*?)</code></pre>", re.S)
SEPARATORS = {"|", "||", "&&", ";", "&", "(", "$(", "{"}


def css_class(ttype):
    if ttype in Keyword.Constant or ttype in Number or ttype in Name.Variable:
        return "n"
    if ttype in Keyword:
        return "k"
    if ttype in String:
        return "s"
    if ttype in Comment:
        return "c"
    if ttype in Name.Builtin or ttype in Name.Function or ttype in Name.Class or ttype in Name.Decorator:
        return "f"
    if ttype in Name.Tag:  # YAML keys
        return "f"
    return None


def spans(code, lang):
    tokens = [(t, v) for t, v in lex(code, LEXERS[lang](ensurenl=False, stripnl=False))]
    out, command_next = [], True
    for i, (ttype, value) in enumerate(tokens):
        cls = css_class(ttype)
        if lang == "python" and cls is None and ttype in Name and i + 1 < len(tokens) and tokens[i + 1][1] == "(":
            cls = "f"  # a call, like the hand-highlighted posts do
        if lang == "bash":
            if value.strip() == "":
                command_next = command_next or "\n" in value
            elif value.strip() in SEPARATORS:
                command_next = True
            elif command_next:
                command_next = False
                if ttype in (Token.Text, Name.Builtin, Name):
                    cls = "f"  # the command being run
        text = html.escape(value, quote=False)
        out.append(f'<span class="{cls}">{text}</span>' if cls and value.strip() else text)
    return "".join(out)


def language(attrs):
    m = re.search(r'class="language-(\w+)"', attrs)
    if m:
        return m.group(1) if m.group(1) in LEXERS else None
    m = re.search(r'data-(?:save|append)="([^"]+)"', attrs)
    return EXT.get(Path(m.group(1)).suffix) if m else None


def rewrite(match):
    attrs, body = match.groups()
    lang = language(attrs)
    if not lang or "<span" in body:
        return match.group(0)
    return f"<pre><code{attrs}>{spans(html.unescape(body), lang)}</code></pre>"


def main(paths):
    for path in map(Path, paths):
        before = path.read_text(encoding="utf-8")
        after = BLOCK.sub(rewrite, before)
        if after != before:
            path.write_text(after, encoding="utf-8")
        print(("highlighted " if after != before else "unchanged   ") + str(path))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
