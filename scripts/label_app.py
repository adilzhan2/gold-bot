"""Веб-разметка сетапов: «взял бы / пропустил бы».

Запуск:  python -m scripts.label_app  →  http://127.0.0.1:8000
Хоткеи:  ← пропустил, → взял, ↓ не уверен (скип)

Результат копится в data/labels/labels.csv — это твой датасет
для имитационной модели («торгуй как я»).
"""
import csv
from pathlib import Path

import pandas as pd
import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = ROOT / "data" / "labels"
QUEUE = LABELS_DIR / "queue.csv"
LABELS = LABELS_DIR / "labels.csv"

app = FastAPI()


def _labeled_ids() -> set[int]:
    if not LABELS.exists():
        return set()
    return set(pd.read_csv(LABELS)["id"].astype(int))


def _next_item():
    queue = pd.read_csv(QUEUE)
    done = _labeled_ids()
    todo = queue[~queue["id"].isin(done)]
    return (None, len(done), len(queue)) if todo.empty else (todo.iloc[0], len(done), len(queue))


PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>gold-bot разметка</title>
<style>
 body {{ background:#1e1f29; color:#eee; font-family:-apple-system,sans-serif; text-align:center; }}
 img {{ max-width:95%; border-radius:8px; margin-top:8px; }}
 .row {{ margin:14px; }}
 button {{ font-size:20px; padding:12px 36px; margin:0 12px; border:none; border-radius:10px; cursor:pointer; }}
 .take {{ background:#50fa7b; }} .pass {{ background:#ff5555; color:#fff; }} .skip {{ background:#555; color:#ddd; }}
 .meta {{ color:#888; font-size:14px; }}
</style></head><body>
 <div class="meta">{progress} размечено · #{id} · {time} · {dir}</div>
 <img src="/img/{id}.png">
 <div class="row">
  <form style="display:inline" method="post" action="/label">
   <input type="hidden" name="item_id" value="{id}"><input type="hidden" name="take" value="0">
   <button class="pass">✕ Пропустил бы (←)</button></form>
  <form style="display:inline" method="post" action="/label">
   <input type="hidden" name="item_id" value="{id}"><input type="hidden" name="take" value="-1">
   <button class="skip">? Не уверен (↓)</button></form>
  <form style="display:inline" method="post" action="/label">
   <input type="hidden" name="item_id" value="{id}"><input type="hidden" name="take" value="1">
   <button class="take">✓ Взял бы (→)</button></form>
 </div>
<script>
 const send = t => {{ const f=document.createElement('form'); f.method='post'; f.action='/label';
   f.innerHTML=`<input name="item_id" value="{id}"><input name="take" value="${{t}}">`;
   document.body.appendChild(f); f.submit(); }};
 addEventListener('keydown', e => {{
   if (e.key==='ArrowRight') send(1); if (e.key==='ArrowLeft') send(0); if (e.key==='ArrowDown') send(-1); }});
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    item, done, total = _next_item()
    if item is None:
        return f"<body style='background:#1e1f29;color:#50fa7b;font-size:28px;text-align:center'><p>Готово! {done}/{total} размечено.</p></body>"
    return PAGE.format(
        id=int(item["id"]),
        progress=f"{done}/{total}",
        time=str(item["time"])[:16],
        dir="LONG" if item["direction"] == 1 else "SHORT",
    )


@app.get("/img/{item_id}.png")
def img(item_id: int):
    return FileResponse(LABELS_DIR / "img" / f"{item_id}.png")


@app.post("/label")
def label(item_id: int = Form(...), take: int = Form(...)):
    new = not LABELS.exists()
    with open(LABELS, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["id", "take"])
        w.writerow([item_id, take])
    return RedirectResponse("/", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
