import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone

# ===== ENV =====
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise Exception("❌ DISCORD_TOKEN або CHANNEL_ID не задані!")

CHANNEL_ID = int(CHANNEL_ID)

# ===== CONFIG =====
WF_API = "https://api.warframestat.us/pc"
STATE_FILE = "wf_bot_state.json"
LOG_FILE = "bot.log"
RARE_KEYWORDS = ["Orokin", "Forma", "Umbra", "Exilus", "Catalyst", "Reactor"]

# ===== BOT =====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== LOG =====
def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

# ===== STATE =====
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerts": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

state = load_state()

# ===== HTTP =====
async def fetch_json(url):
    for i in range(3):
        try:
            async with bot.session.get(url) as r:
                if r.status == 200:
                    return await r.json()

                if r.status == 429:
                    retry = 2
                    try:
                        data = await r.json()
                        retry = data.get("retry_after", 2)
                    except:
                        pass

                    log(f"⏳ Rate limit, sleep {retry}s")
                    await asyncio.sleep(retry)
                    continue

                log(f"❌ HTTP {r.status}")
        except Exception as e:
            log(f"❌ FETCH ERROR: {e}")

        await asyncio.sleep(2)

    return []

# ===== LOGIC =====
def is_rare(text):
    return any(k.lower() in text.lower() for k in RARE_KEYWORDS)

def build_alert_embed(alert):
    mission = alert.get("mission", {})
    reward = mission.get("reward", {})

    items = reward.get("itemString") or ", ".join(reward.get("items", [])) or "-"

    title = "🔥 РІДКИЙ Alert!" if is_rare(items) else "Новий Alert"

    embed = discord.Embed(
        title=title,
        color=0xFF4500,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="Місія",
        value=f"{mission.get('node')} ({mission.get('type')})",
        inline=False
    )

    embed.add_field(
        name="Нагорода",
        value=items,
        inline=False
    )

    return embed

# ===== TASK =====
@tasks.loop(minutes=5)
async def check_warframe():
    log("🔄 Checking alerts...")

    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(CHANNEL_ID)

        alerts = await fetch_json(f"{WF_API}/alerts")

        for alert in alerts:
            aid = alert.get("id")

            if aid and aid not in state["alerts"]:
                embed = build_alert_embed(alert)

                await channel.send(embed=embed)
                log(f"✅ Sent alert {aid}")

                state["alerts"].append(aid)
                save_state(state)

                await asyncio.sleep(1)

    except Exception as e:
        log(f"❌ LOOP ERROR: {e}")

@check_warframe.before_loop
async def before_loop():
    await bot.wait_until_ready()

# ===== COMMAND =====
@bot.tree.command(name="wf_status", description="Статус бота")
async def wf_status(interaction: discord.Interaction):
    embed = discord.Embed(title="📊 Статус", color=0x00FF88)
    embed.add_field(name="Alerts", value=len(state["alerts"]))
    await interaction.response.send_message(embed=embed)

# ===== READY =====
@bot.event
async def on_ready():
    log(f"🤖 Logged in as {bot.user}")

    if not hasattr(bot, "session"):
        bot.session = aiohttp.ClientSession()

    if not check_warframe.is_running():
        check_warframe.start()

    await bot.tree.sync()

# ===== SHUTDOWN =====
@bot.event
async def on_disconnect():
    if hasattr(bot, "session"):
        await bot.session.close()

# ===== RUN =====
bot.run(BOT_TOKEN)
