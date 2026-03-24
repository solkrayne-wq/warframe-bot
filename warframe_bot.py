import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, timezone

# ============================================================
#  НАЛАШТУВАННЯ — заповни ці значення перед запуском
# ============================================================
import os

BOT_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
```

- Натисни **Commit changes**

---

## КРОК 6 — Деплой на Render.com

👉 https://render.com

**6.1 Реєстрація:**
- Натисни **Get Started for Free**
- Вибери **Sign up with GitHub** — це найпростіше

**6.2 Створи сервіс:**
- Після входу натисни **New → Background Worker**
- У списку репозиторіїв знайди `warframe-bot` → натисни **Connect**
- Налаштування залишай як є — Render сам знайде `render.yaml`
- Натисни **Create Background Worker**

**6.3 Додай токен і ID (найважливіший крок!):**
- Відкрий свій сервіс на Render
- Зліва натисни **Environment**
- Натисни **Add Environment Variable** і додай два записи:

| Key | Value |
|-----|-------|
| `DISCORD_TOKEN` | токен бота зі Кроку 1 |
| `CHANNEL_ID` | ID каналу з Кроку 2 |

- Натисни **Save Changes**
- Render автоматично перезапустить бота ✅

---

## КРОК 7 — Перевірка

- На сторінці сервісу в Render натисни **Logs** (зліва)
- Якщо все добре, побачиш:
```
✅ Бот запущено як: Warframe News Bot#1234
📢 Канал для новин: 1234567890123456789
[09:00:00] Перевірку завершено.
# ============================================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

WF_API = "https://api.warframestat.us/pc"
HEADERS = {"Accept-Language": "uk"}   # Українська мова відповідей (де підтримується)

# Файл для зберігання вже відправлених даних (щоб не дублювати)
STATE_FILE = "wf_bot_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerts": [], "invasions": [], "events": [], "news": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

state = load_state()


# ──────────────────────────────────────────────
#  EMBED-БУДІВНИКИ
# ──────────────────────────────────────────────

def build_alert_embed(alert):
    mission = alert.get("mission", {})
    reward = mission.get("reward", {})
    items = reward.get("itemString") or ", ".join(reward.get("items", [])) or "—"

    embed = discord.Embed(
        title="🚨 Новий Алерт!",
        color=0xFF4500,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📍 Місія", value=f"{mission.get('node', '?')} ({mission.get('type', '?')})", inline=False)
    embed.add_field(name="🎯 Ціль", value=mission.get("faction", "?"), inline=True)
    embed.add_field(name="🏆 Нагорода", value=items, inline=True)
    embed.add_field(name="⚔️ Рівень ворогів", value=f"{mission.get('minEnemyLevel', '?')}–{mission.get('maxEnemyLevel', '?')}", inline=True)
    embed.add_field(name="⏳ Закінчується", value=alert.get("eta", "?"), inline=False)
    embed.set_footer(text="Warframe Alerts")
    return embed


def build_invasion_embed(inv):
    embed = discord.Embed(
        title="⚔️ Нова Інвазія!",
        color=0x8B0000,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📍 Місце", value=inv.get("node", "?"), inline=False)

    atk = inv.get("attackingFaction", "?")
    dfd = inv.get("defendingFaction", "?")
    embed.add_field(name="Атакує", value=atk, inline=True)
    embed.add_field(name="Захищає", value=dfd, inline=True)

    atk_reward = inv.get("attackerReward", {}).get("itemString", "—")
    def_reward = inv.get("defenderReward", {}).get("itemString", "—")
    embed.add_field(name="🎁 Нагорода атакуючих", value=atk_reward, inline=True)
    embed.add_field(name="🎁 Нагорода захисників", value=def_reward, inline=True)

    completion = inv.get("completion", 0)
    bar = "█" * int(completion / 10) + "░" * (10 - int(completion / 10))
    embed.add_field(name=f"📊 Прогрес {completion:.1f}%", value=bar, inline=False)
    embed.set_footer(text="Warframe Invasions")
    return embed


def build_event_embed(event):
    embed = discord.Embed(
        title=f"🎉 Подія: {event.get('description', 'Без назви')}",
        description=event.get("tooltip", ""),
        color=0xFFD700,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="⏳ Закінчується", value=event.get("expiry", "?"), inline=True)
    if event.get("rewards"):
        rewards = ", ".join([r.get("itemString", "") for r in event["rewards"] if r.get("itemString")])
        embed.add_field(name="🏆 Нагороди", value=rewards or "—", inline=True)
    embed.set_footer(text="Warframe Events")
    return embed


def build_news_embed(item):
    embed = discord.Embed(
        title=item.get("message", "Новина"),
        url=item.get("link", ""),
        color=0x1E90FF,
        timestamp=datetime.now(timezone.utc)
    )
    if item.get("imageLink"):
        embed.set_image(url=item["imageLink"])
    embed.set_footer(text="Warframe News")
    return embed


# ──────────────────────────────────────────────
#  ГОЛОВНЕ ЗАВДАННЯ — перевірка кожні 5 хвилин
# ──────────────────────────────────────────────

@tasks.loop(minutes=5)
async def check_warframe_news():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"[ПОМИЛКА] Канал {CHANNEL_ID} не знайдено!")
        return

    async with aiohttp.ClientSession() as session:

        # ── Алерти ──────────────────────────────
        try:
            async with session.get(f"{WF_API}/alerts", headers=HEADERS) as r:
                alerts = await r.json()
            for alert in alerts:
                aid = alert.get("id")
                if aid and aid not in state["alerts"]:
                    await channel.send(embed=build_alert_embed(alert))
                    state["alerts"].append(aid)
                    # Зберігаємо лише останні 200 ID
                    state["alerts"] = state["alerts"][-200:]
        except Exception as e:
            print(f"[Alerts] Помилка: {e}")

        # ── Інвазії ──────────────────────────────
        try:
            async with session.get(f"{WF_API}/invasions", headers=HEADERS) as r:
                invasions = await r.json()
            for inv in invasions:
                iid = inv.get("id")
                if iid and iid not in state["invasions"] and not inv.get("completed", False):
                    await channel.send(embed=build_invasion_embed(inv))
                    state["invasions"].append(iid)
                    state["invasions"] = state["invasions"][-200:]
        except Exception as e:
            print(f"[Invasions] Помилка: {e}")

        # ── Події ────────────────────────────────
        try:
            async with session.get(f"{WF_API}/events", headers=HEADERS) as r:
                events = await r.json()
            for event in events:
                eid = event.get("id")
                if eid and eid not in state["events"]:
                    await channel.send(embed=build_event_embed(event))
                    state["events"].append(eid)
                    state["events"] = state["events"][-100:]
        except Exception as e:
            print(f"[Events] Помилка: {e}")

        # ── Новини з сайту ───────────────────────
        try:
            async with session.get(f"{WF_API}/news", headers=HEADERS) as r:
                news = await r.json()
            for item in news:
                nid = item.get("id")
                if nid and nid not in state["news"]:
                    await channel.send(embed=build_news_embed(item))
                    state["news"].append(nid)
                    state["news"] = state["news"][-100:]
        except Exception as e:
            print(f"[News] Помилка: {e}")

    save_state(state)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Перевірку завершено.")


@check_warframe_news.before_loop
async def before_check():
    await bot.wait_until_ready()


# ──────────────────────────────────────────────
#  КОМАНДИ
# ──────────────────────────────────────────────

@bot.command(name="wf_status")
async def wf_status(ctx):
    """Показує поточний статус моніторингу"""
    embed = discord.Embed(
        title="📡 Warframe Bot — Статус",
        color=0x00FF88,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Інтервал перевірки", value="5 хвилин", inline=True)
    embed.add_field(name="Алертів в базі", value=str(len(state["alerts"])), inline=True)
    embed.add_field(name="Інвазій в базі", value=str(len(state["invasions"])), inline=True)
    embed.add_field(name="Подій в базі", value=str(len(state["events"])), inline=True)
    embed.add_field(name="Новин в базі", value=str(len(state["news"])), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="wf_reset")
@commands.has_permissions(administrator=True)
async def wf_reset(ctx):
    """[Адмін] Скидає стан — бот перепостить усі поточні новини"""
    global state
    state = {"alerts": [], "invasions": [], "events": [], "news": []}
    save_state(state)
    await ctx.send("✅ Стан скинуто! Наступна перевірка покаже всі актуальні новини.")


# ──────────────────────────────────────────────
#  ЗАПУСК
# ──────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Бот запущено як: {bot.user}")
    print(f"📢 Канал для новин: {CHANNEL_ID}")
    check_warframe_news.start()

bot.run(BOT_TOKEN)
