/**
 * Cloudflare Worker — мгновенный приём команд Telegram.
 *
 * Telegram шлёт сюда вебхук на каждое сообщение боту. Worker проверяет, что
 * это владелец, и дёргает GitHub (repository_dispatch) — там workflow
 * "gold-bot webhook command" выполняет команду и отвечает в Telegram.
 *
 * Переменные окружения Worker (Settings → Variables):
 *   OWNER_CHAT_ID — твой chat_id (780116312)
 *   GH_REPO       — adilzhan2/gold-bot
 *   GH_TOKEN      — GitHub PAT (classic, scope: repo) — как СЕКРЕТ
 */
export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");

    let update;
    try { update = await request.json(); } catch { return new Response("bad"); }

    const msg = update.message || update.edited_message;
    const text = (msg && msg.text) || "";
    const chatId = msg && msg.chat && msg.chat.id;

    // только владелец и только команды
    if (String(chatId) !== String(env.OWNER_CHAT_ID)) return new Response("ignored");
    if (!text.startsWith("/")) return new Response("ok");

    await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "gold-bot-worker",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ event_type: "tg-command", client_payload: { cmd: text } }),
    });

    return new Response("ok");
  },
};
