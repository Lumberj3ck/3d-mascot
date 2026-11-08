"""Generate style-locked concept images for items with the Codex CLI (image_generation tool).

Usage: python3 scripts/items/gen_concepts.py [--jobs 4] [--only id1,id2] [--force]
Reads inputs/items/items.json (method == "pixal3d" items), attaches inputs/raw/turnaround.png as
style reference, writes inputs/items/concepts/<id>.png (1024x1024). Logs in inputs/items/concepts/logs/.
"""
import argparse, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "inputs/items/items.json").read_text())
OUT = ROOT / "inputs/items/concepts"
REF = ROOT / "inputs/raw/turnaround.png"

ap = argparse.ArgumentParser()
ap.add_argument("--jobs", type=int, default=4)
ap.add_argument("--only", default="")
ap.add_argument("--force", action="store_true")
a = ap.parse_args()
only = set(filter(None, a.only.split(",")))
items = [i for i in CFG["items"] if i["method"] == "pixal3d" and (not only or i["id"] in only)]
(OUT / "logs").mkdir(parents=True, exist_ok=True)


def gen(item):
    dst = OUT / f"{item['id']}.png"
    if dst.exists() and not a.force:
        return item["id"], "skip (exists)"
    prompt = (
        "Use your image generation tool. The attached image is the STYLE REFERENCE. "
        f"Generate ONE new image: a product shot of a single item - {item['desc']}. {CFG['style']}\n"
        f"Save the resulting PNG to ./{dst.name} in the current directory, resized to 1024x1024, "
        "then reply with just the file path."
    )
    with open(OUT / "logs" / f"{item['id']}.log", "w") as log:
        r = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
                            "-C", str(OUT), "-i", str(REF), "-"],
                           input=prompt, text=True, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    return item["id"], ("ok" if dst.exists() else f"FAILED (exit {r.returncode})")


with ThreadPoolExecutor(a.jobs) as ex:
    for iid, status in ex.map(gen, items):
        print(f"{iid:15s} {status}", flush=True)
