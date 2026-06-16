# Мгновенный /check через Cloudflare Worker (бесплатно)

Зачем: GitHub cron отвечает на команды с задержкой 5-20 мин. Webhook через
Worker даёт отклик ~1 мин и надёжно.

Поток: нажатие в Telegram → вебхук в Worker → Worker дёргает GitHub
(repository_dispatch) → workflow выполняет команду → ответ в Telegram.

## Шаги (один раз, ~10 мин)

### 1. GitHub PAT (токен для Worker)
- github.com → Settings → Developer settings → Personal access tokens →
  **Tokens (classic)** → Generate new token (classic)
- Scope: только **repo**. Срок — на твоё усмотрение. Скопируй токен.

### 2. Cloudflare Worker
- Заведи бесплатный аккаунт на cloudflare.com
- Workers & Pages → **Create** → Create Worker → имя `gold-bot` → Deploy
- Edit code → вставь содержимое `worker.js` (из этой папки) → Deploy
- Скопируй URL воркера: `https://gold-bot.<твой>.workers.dev`

### 3. Переменные Worker
Worker → Settings → Variables and Secrets → добавь:
- `OWNER_CHAT_ID` = `780116312`  (plaintext)
- `GH_REPO` = `adilzhan2/gold-bot`  (plaintext)
- `GH_TOKEN` = вставь PAT из шага 1  (**Encrypt** / secret)
Сохрани и задеплой.

### 4. Привязать вебхук Telegram к воркеру
Дай Claude URL воркера — он выполнит setWebhook. Или сам:
```
curl "https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=https://gold-bot.<твой>.workers.dev"
```

Готово. Теперь /check, /last, /status, /week отвечают за ~1 мин.

## Откатить (вернуться к cron-командам)
```
curl "https://api.telegram.org/bot<ТОКЕН>/deleteWebhook"
```
