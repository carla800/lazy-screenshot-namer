import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path

import ollama

MODEL = "gemma4:e2b-it-qat"
IMAGE_TYPES = {".png", ".jpg", ".jpeg"}

DESCRIBE_PROMPT = """Describe in one sentence what this screenshot is about. Focus on its content (what is being shown, asked or answered), not only on the tool.
Then, on a new line, write: sensitive: yes or no (yes only if a password, API key, token or connection string with a password is visible)"""

NAME_PROMPT = """Turn this description of a screenshot into a file name of 2 to 5 lowercase English words separated by hyphens.
Start with the tool or project, then the most specific topic. Avoid generic words like screenshot, results, interface, image, data or query.
Answer with the file name only.

Description: {description}"""


def clean_name(text):
    """Keeps at most 5 lowercase words made of letters and digits, joined by hyphens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:5]) or "screenshot"


def suggest(image):
    """Two steps: describe the image, then turn the description into a name."""
    # Step 1 (slow): the model looks at the image and describes it
    first = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": DESCRIBE_PROMPT, "images": [str(image)]}],
        think=False,
        options={"temperature": 0.2, "num_predict": 80},
    )
    text = first["message"]["content"]
    sensitive = re.search(r"sensitive:\s*yes", text, re.IGNORECASE) is not None
    description = re.split(r"sensitive:", text, flags=re.IGNORECASE)[0].strip()

    # Step 2 (fast, text only): turn the description into a file name
    second = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": NAME_PROMPT.format(description=description)}],
        think=False,
        options={"temperature": 0.2, "num_predict": 20},
    )
    return clean_name(second["message"]["content"]), sensitive, description


parser = argparse.ArgumentParser(description="Rename screenshots with names suggested by a local model")
parser.add_argument("folder", nargs="?", default="samples", help="folder with the screenshots")
parser.add_argument("--apply", action="store_true", help="really rename the files (default: only show suggestions)")
args = parser.parse_args()

folder = Path(args.folder)
images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_TYPES)
taken = {p.name for p in folder.iterdir()}
log_rows = []

for image in images:
    start = time.perf_counter()
    name, sensitive, description = suggest(image)
    seconds = time.perf_counter() - start
    if sensitive:
        name = "sensitive-" + name
    new_name = name + image.suffix.lower()
    counter = 2
    while new_name in taken:  # never overwrite an existing file
        new_name = f"{name}-{counter}{image.suffix.lower()}"
        counter += 1
    taken.add(new_name)
    flag = "   (!) may contain a secret" if sensitive else ""
    print(f"{image.name}  ->  {new_name}   ({seconds:.0f}s){flag}")
    print(f"    {description}")
    if args.apply:
        image.rename(folder / new_name)
        log_rows.append([datetime.now().isoformat(timespec="seconds"), image.name, new_name, sensitive])

if args.apply:
    with open("rename_log.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(log_rows)
    print("\nRenamed", len(log_rows), "files. Log saved to rename_log.csv")
else:
    print("\nDry run: nothing renamed. Add --apply to rename.")