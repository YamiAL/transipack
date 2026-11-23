from pathlib import Path

root = Path("inventario/templates")
old_style = """    th, td, tr, .table thead th{
      border: 1px solid #838a91;
      height: 0px;
    }

    th{
      background-color: aliceblue;
    }
"""
replacements = [
    (
        'class="table table-hover cell-border mt-4"',
        'class="table table-hover table-sm table-striped mt-4"',
    ),
    (
        'class="table table-hover cell-border" >',
        'class="table table-hover table-sm table-striped">',
    ),
    (
        'class="table table-hover cell-border"',
        'class="table table-hover table-sm table-striped"',
    ),
    (
        'class="table table-hover text-nowrap"',
        'class="table table-hover table-sm table-striped text-nowrap"',
    ),
    (
        'class="table table-hover"',
        'class="table table-hover table-sm table-striped"',
    ),
]
changed = []
paths = list((root / "reportes").glob("*.html")) + [root / "inventario" / "inventario_reportes.html"]
for path in paths:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    orig = text
    if old_style in text:
        text = text.replace(old_style, "")
    for a, b in replacements:
        text = text.replace(a, b)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        changed.append(str(path))
print("updated", len(changed))
for c in changed:
    print(c)
