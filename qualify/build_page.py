"""Inline the stylesheet and docs/qualify/data.json into qualify/template.html -> docs/qualify/index.html."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
css = pathlib.Path(root / "qualify/_css.html").read_text()
d = json.load(open(root / "docs/qualify/data.json"))
tpl = (root / "qualify/template.html").read_text()
html = tpl.replace("__CSS__", css).replace("__DATA__", json.dumps(d, separators=(",", ":")))
(root / "docs/qualify/index.html").write_text(html)
print("wrote docs/qualify/index.html", (root / "docs/qualify/index.html").stat().st_size // 1024, "KB")
