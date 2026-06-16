#!/bin/bash
# Качает XAUUSD m5-свечи с Dukascopy (бесплатно, без регистрации).
# dukascopy-node — самый живой инструмент для этого, ставится сам через npx.
set -e
cd "$(dirname "$0")/.."

npx -y dukascopy-node \
  --instrument xauusd \
  --date-from 2021-01-01 \
  --date-to 2026-06-01 \
  --timeframe m5 \
  --format csv \
  --directory data/raw \
  --volumes true

echo "Готово. CSV в data/raw/"
