import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, timezone

BOT_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

WF_API = "https://api.warframestat.us/pc"
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

def build_alert_embed(alert):
    mission = alert.get("mission", {})
    reward = mission.get("reward", {})
    items = reward.get("itemString") or ", ".join(reward.get("items", [])) or "-"
    embed = discord.Embed(title="Novyi Alert!", color=0xFF4500, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Misiya", value=f"{mission.get('node', '?')} ({mission.get('type', '?')})", inline=False)
    embed.add_field(name="Tsvil", value=mission.get("faction", "?"), inline=True)
    embed.add_field(name="Nahoroda", value=items, inline=True)
    embed.add_field(name="Zakinchuyetsya", value=alert.get("eta", "?"), inline=False)
    embed.set_footer(text="Warframe Alerts")
    return embed

def build_invasion_embed(inv):
    embed = discord.Embed(title="Nova Invaziya!", color=0x8B0000, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Mistse", value=inv.get("node", "?"), inline=False)
    embed.add_field(name="Atakuye", value=inv.get("attackingFaction", "?"), inline=True)
    embed.add_field(name="Zakhyshchaye", value=inv.get("defendingFaction", "?"), inline=True)
    embed.add_field(name="Nahoroda atakuyuchykh", value=inv.get("attackerReward", {}).get("itemString", "-"), inline=True)
    embed.add_field(name="Nahoroda zakhysnykiv", value=inv.get("defenderReward", {}).get("itemString", "-"), inline=True)
    completion = inv.get("completion", 0)
    bar = "X" * int(completion / 10) + "." * (10 - int(completion / 10))
    embed.add_field(name=f"Prohres {completion:.1f}%", value=bar, inline=False)
    embed.set_footer(text="Warframe Invasions")
    return embed

def build_event_embed(event):
    embed = discord.Embed(title=f"Podiya: {event.get('description', 'Bez nazvy')}", description=event.get("tooltip", ""), color=0xFFD700, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Zakinchuyetsya", value=event.get("expiry", "?"), inline=True)
    embed.set_footer(text="Warframe Events")
    return embed

def build_news_embed(item):
    embed = discord.Embed(title=item.get("message", "Novyna"), url=item.get("link", ""), color=0x1E90FF, timestamp=datetime.now(timezone.utc))
    if item.get("imageLink"):
        embed.set_image(url=item["imageLink"])
    embed.set_footer(text="Warframe News")
    return embed

@tasks.loop(minutes=5)
async def check_warframe_news():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Kanal {CHANNEL_ID} ne znaydeno!")
        return

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{WF_API}/alerts") as r:
                alerts = await r.json()
            for alert in alerts:
                aid = alert.get("id")
                if aid and aid not in state["alerts"]:
                    await channel.send(embed=build_alert_embed(alert))
                    state["alerts"].append(aid)
                    state["alerts"] = state["alerts"][-200:]
        except Exception as e:
            print(f"Alerts error: {e}")

        try:
            async with session.get(f"{WF_API}/invasions") as r:
                invasions = await r.json()
            for inv in invasions:
                iid = inv.get("id")
                if iid and iid not in state["invasions"] and not inv.get("completed", False):
                    await channel.send(embed=build_invasion_embed(inv))
                    state["invasions"].append(iid)
                    state["invasions"] = state["invasions"][-200:]
        except Exception as e:
            print(f"Invasions error: {e}")

        try:
            async with session.get(f"{WF_API}/events") as r:
                events = await r.json()
            for event in events:
                eid = event.get("id")
                if eid and eid not in state["events"]:
                    await channel.send(embed=build_event_embed(event))
                    state["events"].append(eid)
                    state["events"] = state["events"][-100:]
        except Exception as e:
            print(f"Events error: {e}")

        try:
            async with session.get(f"{WF_API}/news") as r:
                news = await r.json()
            for item in news:
                nid = item.get("id")
                if nid and nid not in state["news"]:
                    await channel.send(embed=build_news_embed(item))
                    state["news"].append(nid)
                    state["news"] = state["news"][-100:]
        except Exception as e:
            print(f"News error: {e}")

    save_state(state)
    print(f"Check done: {datetime.now().strftime('%H:%M:%S')}")

@check_warframe_news.before_loop
async def before_check():
    await bot.wait_until_ready()

@bot.command(name="wf_status")
async def wf_status(ctx):
    embed = discord.Embed(title="Warframe Bot - Status", color=0x00FF88, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Interval", value="5 min", inline=True)
    embed.add_field(name="Alerts", value=str(len(state["alerts"])), inline=True)
    embed.add_field(name="Invasions", value=str(len(state["invasions"])), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="wf_reset")
@commands.has_permissions(administrator=True)
async def wf_reset(ctx):
    global state
    state = {"alerts": [], "invasions": [], "events": [], "news": []}
    save_state(state)
    await ctx.send("State reset!")

@bot.event
async def on_ready():
    print(f"Bot started: {bot.user}")
    print(f"Channel: {CHANNEL_ID}")
    check_warframe_news.start()

bot.run(BOT_TOKEN)
