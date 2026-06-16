"""Имитационная модель: учится предсказывать ТВОЁ «взял бы / пропустил»,
а не исход рынка. Цель — take (1/0), фичи — те же FEATURE_COLS сетапа.

При малом числе разметок обычная нейронка переобучится мгновенно,
поэтому здесь логистическая регрессия с cross-val: меньше параметров,
честная оценка на отложенных фолдах. Пересядем на нейронку, когда
размеченных станет много (сотни).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

from goldbot.features.setups import FEATURE_COLS

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "labels" / "queue.csv"  # фичи сэмпла, ключ = id картинки
LABELS = ROOT / "data" / "labels" / "labels.csv"
MODELS = ROOT / "models"


def main():
    # ВАЖНО: мёрджим по id картинки (queue.csv), а не по индексу полного датасета —
    # иначе метки цепляются к чужим сетапам.
    queue = pd.read_csv(QUEUE)
    lab = pd.read_csv(LABELS)
    lab = lab[lab["take"] != -1]  # «не уверен» в обучение не идёт

    df = queue.merge(lab, on="id")
    X = df[FEATURE_COLS].fillna(0).values
    y = df["take"].values
    n_take, n_pass = int((y == 1).sum()), int((y == 0).sum())
    print(f"размечено в обучении: {len(y)}  (взял {n_take} / пропустил {n_pass})")

    if len(y) < 20 or n_take < 5 or n_pass < 5:
        print("СЛИШКОМ МАЛО данных для осмысленной оценки — разметь ещё.")

    clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=1000))

    # честная оценка: предсказания на отложенных фолдах (out-of-fold)
    folds = min(5, n_take, n_pass)
    if folds >= 2:
        oof = cross_val_predict(clf, X, y, cv=folds, method="predict_proba")[:, 1]
        auc = roc_auc_score(y, oof)
        print(f"cross-val AUC: {auc:.3f}  (0.5 = угадайка; >0.65 — модель уловила твой вкус)")

    clf.fit(X, y)

    # какие фичи толкают к «взял бы» (знак коэффициента)
    coef = clf.named_steps["logisticregression"].coef_[0]
    order = np.argsort(np.abs(coef))[::-1][:8]
    print("\nчто влияет на твоё решение (по модулю):")
    for i in order:
        sign = "→ берёшь" if coef[i] > 0 else "→ пропускаешь"
        print(f"  {FEATURE_COLS[i]:22s} {coef[i]:+.2f}  (больше {sign})")

    MODELS.mkdir(exist_ok=True)
    import pickle
    from goldbot.model.imitation import export_json
    with open(MODELS / "imitation.pkl", "wb") as f:
        pickle.dump(clf, f)
    export_json(clf)  # JSON-версия для serverless-алертера (GitHub Actions)
    print(f"\nСохранил → {MODELS}/imitation.pkl + imitation.json")
    print("Алертер подхватит её для фильтрации, когда AUC станет уверенным.")


if __name__ == "__main__":
    main()
