import json
import os

def inspect_notebook(filename):
    print(f"=== Inspecting {filename} ===")
    if not os.path.exists(filename):
        print("File does not exist.")
        return
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("Number of cells:", len(data["cells"]))
    for i, cell in enumerate(data["cells"]):
        cell_type = cell["cell_type"]
        src = cell["source"]
        lines = src if isinstance(src, list) else src.splitlines()
        first_line = lines[0].strip() if len(lines) > 0 else "EMPTY"
        print(f"Cell {i:2d} ({cell_type}): {first_line[:100]}")

inspect_notebook("notebook5399bf943b.ipynb")
inspect_notebook("notebook000a1ff606.ipynb")
