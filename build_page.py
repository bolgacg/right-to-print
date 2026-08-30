"""Inline model.js and docs/data.json into the template and write docs/index.html."""
import json, pathlib
d = json.load(open("docs/data.json"))
# the page does not need every part's full economics object or the topo histories
slim = dict(d)
slim["model"] = dict(d["model"]); slim["model"].pop("eco", None)
if slim.get("topo"):
    slim["topo"] = dict(d["topo"]); slim["topo"]["designs"] = [dict(x, history=None) for x in d["topo"]["designs"]]
tpl = pathlib.Path("template.html").read_text()
html = tpl.replace("__MODEL__", pathlib.Path("model.js").read_text()).replace("__DATA__", json.dumps(slim, separators=(",", ":")))
pathlib.Path("docs/index.html").write_text(html)
print("wrote docs/index.html", pathlib.Path("docs/index.html").stat().st_size // 1024, "KB")
