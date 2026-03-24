import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
import os
import time
from datetime import datetime, timezone

BOT_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

WF_API = "https://api.warframestat.us/pc"
STATE_FILE = "wf_bot_state.json"
LOG_FILE = "bot.log"
RARE_KEYWORDS = ["Orokin", "Forma", "Umbra", "Exilus", "Catalyst", "Reactor"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")
    print(msg)

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, "r", encoding="utf-8"))
    return {"alerts": [], "invasions": [], "events": [], "news": []}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), indent=2)

state = load_state()

async def fetch_json(url):
    for _ in range(3):
        try:
            async with bot.session.get(url) as r:
                if r.status == 429:
                    data = await r.json()
                    await asyncio.sleep(data.get("retry_after", 2))
                    continue
                return await r.json()
        except:
            await asyncio.sleep(2)
    return []

def is_rare(text):
    return any(k.lower() in text.lower() for k in RARE_KEYWORDS)

def build_alert_embed(alert):
    mission = alert.get("mission", {})
    reward = mission.get("reward", {})
    items = reward.get("itemString") or ", ".join(reward.get("items", [])) or "-"
    title = "🔥 РІДКИЙ Alert!" if is_rare(items) else "Новий Alert"
    embed = discord.Embed(title=title, color=0xFF4500, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Місія", value=f"{mission.get('node')} ({mission.get('type')})", inline=False)
    embed.add_field(name="Нагорода", value=items, inline=False)
    return embed

class RefreshView(discord.ui.View):
    @discord.ui.button(label="🔄 Оновити", style=discord.ButtonStyle.green)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Оновлюю...", ephemeral=True)
        await check_warframe_news()

@tasks.loop(minutes=5)
async def check_warframe_news():
    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        alerts = await fetch_json(f"{WF_API}/alerts")
        for alert in alerts:
            aid = alert.get("id")
            if aid and aid not in state["alerts"]:
                embed = build_alert_embed(alert)
                view = RefreshView() if "РІДКИЙ" in embed.title else None
                await channel.send(embed=embed, view=view)
                state["alerts"].append(aid)
                await asyncio.sleep(1)
        save_state(state)
    except:
        pass

@check_warframe_news.before_loop
async def before_loop():
    await bot.wait_until_ready()

@bot.tree.command(name="wf_status", description="Статус бота")
async def wf_status(interaction: discord.Interaction):
    embed = discord.Embed(title="📊 Статус", color=0x00FF88)
    embed.add_field(name="Alerts", value=len(state["alerts"]))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wf_reset", description="Скинути стан")
async def wf_reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Нема прав", ephemeral=True)
    global state
    state = {"alerts": [], "invasions": [], "events": [], "news": []}
    save_state(state)
    await interaction.response.send_message("Скинуто ✅")

@bot.event
async def on_ready():
    if not hasattr(bot, "session"):
        bot.session = aiohttp.ClientSession()
    if not check_warframe_news.is_running():
        check_warframe_news.start()
    await bot.tree.sync()

time.sleep(10)
bot.run(BOT_TOKEN)
