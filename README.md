# gold-bot

Нейронка, которая учится фильтровать SMC-сетапы на XAUUSD.

## Пайплайн

```
свечи (Dukascopy) → SMC-фичи → triple-barrier разметка → MLP (PyTorch) → walk-forward → бэктест со спредом
```

iOS-аналогия: `features/` — это ViewModel (вся логика), модель — просто `func score(_ vm: SetupViewModel) -> Float`.

## Структура

```
goldbot/
  data/        загрузка и чтение свечей (Dukascopy через dukascopy-node)
  features/    SMC-структура: swing points, BOS/CHoCH, FVG, order blocks
  labeling/    triple-barrier: для каждого сетапа — TP / SL / таймаут
  model/       PyTorch MLP + walk-forward тренировка
  backtest/    симуляция со спредом и комиссиями
scripts/       CLI-точки входа
data/raw/      сырые свечи (csv, в git не идут)
data/processed/  датасеты с фичами и метками
```

## Команды

```bash
source .venv/bin/activate

# 1. Скачать свечи (m1/m5, ~5 лет)
./scripts/download_data.sh

# 2. Посчитать фичи + разметку → датасет
python -m scripts.build_dataset

# 3. Тренировка с walk-forward
python -m scripts.train

# 4. Бэктест на out-of-sample
python -m scripts.backtest
```

## Алертер + разметка (режим «торгуй как я»)

```bash
# нагенерить батч исторических сетапов картинками
python -m scripts.make_label_batch

# веб-разметка: http://127.0.0.1:8000, хоткеи ← ✕ / → ✓ / ↓ скип
python -m scripts.label_app

# live-алертер: полл GC=F раз в минуту, уведомление на каждый сетап
# (опционально: export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...)
python -m scripts.alerter
```

Разметка копится в `data/labels/labels.csv` — на ней потом учится
имитационная модель (предсказывает твоё «взял бы», а не исход рынка).

## Жёсткое правило

Пока walk-forward не бьёт спред + комиссии — никакого реального депозита.
