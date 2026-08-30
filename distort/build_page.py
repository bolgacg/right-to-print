import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
css = (root / "qualify/_css.html").read_text()
d = json.load(open(root / "docs/distort/data.json"))
html = (root / "distort/template.html").read_text().replace("__CSS__", css).replace("__DATA__", json.dumps(d, separators=(",", ":")))
(root / "docs/distort/index.html").write_text(html)
print("wrote docs/distort/index.html", (root / "docs/distort/index.html").stat().st_size // 1024, "KB")
