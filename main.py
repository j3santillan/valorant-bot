import discord
import statistics
import asyncio
import aiohttp
import os
import vlrdevapi as vlr
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from aiohttp import web

TOKEN            = os.environ.get("TOKEN")
ALERT_CHANNEL_ID = 1501813399137554434

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

async def health(request):
    return web.Response(text="OK")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()

KNOWN_PLAYER_IDS = {
    "jinggg":       2,
    "f0rsaken":     6,
    "d4v41":        5,
    "suggest":      8,
    "mono":         9,
    "something":    24895,
    "tennn":        4,
    "zyppan":       30,
    "zekken":       1585,
    "tenz":         11,
    "yay":          880,
    "crashies":     397,
    "victor":       398,
    "marved":       399,
    "leaf":         491,
    "bang":         492,
    "s0m":          493,
    "dephh":        300,
    "sacy":         200,
    "pancada":      201,
    "less":         202,
    "aspas":        100,
    "heat":         101,
    "tuyz":         102,
    "saadhak":      103,
    "nzr":          104,
    "cned":         50,
    "alfajer":      51,
    "derke":        52,
    "boaster":      53,
    "chronicle":    54,
    "leo":          55,
    "scream":       60,
    "rb":           61,
    "ardiis":       62,
    "ange1":        63,
    "mindfreak":    150,
    "liazz":        151,
    "benkai":       160,
    "f1nn":         161,
    "starxo":       162,
    "lakia":        170,
    "stax":         172,
    "meteor":       173,
    "buzz":         174,
    "mako":         180,
    "xeta":         181,
    "cgrs":         400,
    "ethan":        401,
    "valyn":        402,
    "jawgemo":      403,
    "demon1":       420,
    "cryo":         450,
    "asuna":        451,
}

TEAM_PACE = {
    "PRX":  {"avg_rounds": 24.1, "style": "Aggressive"},
    "T1":   {"avg_rounds": 23.8, "style": "Aggressive"},
    "ZETA": {"avg_rounds": 23.5, "style": "Fast"},
    "GENG": {"avg_rounds": 21.9, "style": "Structured"},
    "DRX":  {"avg_rounds": 22.2, "style": "Slow"},
    "RRQ":  {"avg_rounds": 23.0, "style": "Balanced"},
    "DFM":  {"avg_rounds": 22.5, "style": "Balanced"},
    "NRG":  {"avg_rounds": 23.1, "style": "Balanced"},
    "SEN":  {"avg_rounds": 22.8, "style": "Balanced"},
    "LEV":  {"avg_rounds": 23.0, "style": "Balanced"},
    "LOUD": {"avg_rounds": 23.2, "style": "Aggressive"},
    "100T": {"avg_rounds": 22.9, "style": "Balanced"},
    "EG":   {"avg_rounds": 22.7, "style": "Balanced"},
    "C9":   {"avg_rounds": 23.0, "style": "Balanced"},
    "FNC":  {"avg_rounds": 22.8, "style": "Balanced"},
    "NIP":  {"avg_rounds": 22.6, "style": "Balanced"},
    "TH":   {"avg_rounds": 22.6, "style": "Balanced"},
    "GEN":  {"avg_rounds": 22.4, "style": "Structured"},
    "KRU":  {"avg_rounds": 22.5, "style": "Balanced"},
    "MIBR": {"avg_rounds": 23.0, "style": "Aggressive"},
    "FUT":  {"avg_rounds": 22.8, "style": "Balanced"},
    "BBL":  {"avg_rounds": 22.6, "style": "Balanced"},
    "NAVI": {"avg_rounds": 23.0, "style": "Aggressive"},
    "TL":   {"avg_rounds": 22.9, "style": "Balanced"},
    "M80":  {"avg_rounds": 22.7, "style": "Balanced"},
}
DEFAULT_PACE = {"avg_rounds": 22.6, "style": "Unknown"}

vlr_id_cache = {}

def normalize_name(name: str) -> str:
    return name.lower().replace(" ", "").replace(".", "").replace("-", "")

async def search_vlr_player(session, player_name: str):
    try:
        url     = f"https://www.vlr.gg/search/?q={player_name.replace(' ', '+')}&type=players"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            html = await r.text()

        soup        = BeautifulSoup(html, "html.parser")
        norm_target = normalize_name(player_name)
        selector_pairs = [
            ("a.search-item",       ".search-item-name"),
            ("a[href*='/player/']", ".name"),
            ("a[href*='/player/']", None),
        ]
        for link_sel, name_sel in selector_pairs:
            results = soup.select(link_sel)
            if not results:
                continue
            for result in results:
                href = result.get("href", "")
                if "/player/" not in href:
                    continue
                if name_sel:
                    name_el    = result.select_one(name_sel)
                    found_name = name_el.text.strip() if name_el else result.text.strip()
                else:
                    found_name = result.text.strip()
                norm_found = normalize_name(found_name)
                if norm_target in norm_found or norm_found in norm_target:
                    parts = href.strip("/").split("/")
                    if len(parts) >= 2 and parts[0] == "player":
                        try:
                            return int(parts[1])
                        except ValueError:
                            continue
            break
        return None
    except Exception as e:
        print(f"VLR search error for {player_name}: {e}")
        return None

async def get_vlr_id(session, player_name: str):
    if player_name in vlr_id_cache:
        return vlr_id_cache[player_name]
    norm = normalize_name(player_name)
    for known_name, known_id in KNOWN_PLAYER_IDS.items():
        if norm == normalize_name(known_name) or norm in normalize_name(known_name) or normalize_name(known_name) in norm:
            print(f"✅ Hardcoded ID for '{player_name}': {known_id}")
            vlr_id_cache[player_name] = known_id
            return known_id
    print(f"🔍 Scraping vlr.gg for '{player_name}'...")
    vlr_id = await search_vlr_player(session, player_name)
    if vlr_id:
        vlr_id_cache[player_name] = vlr_id
        print(f"✅ Scraped VLR ID for '{player_name}': {vlr_id}")
    else:
        print(f"❌ Could not find VLR ID for '{player_name}'")
    return vlr_id

async def fetch_recent_kpr(session, player_id: int, days: int = 60):
    try:
        url     = f"https://www.vlr.gg/player/matches/{player_id}/?agent=all&map=all&event_group_id=all&event_id=all&series_id=all"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            html = await r.text()

        soup     = BeautifulSoup(html, "html.parser")
        cutoff   = datetime.now() - timedelta(days=days)
        rows     = soup.select("tr.mod-web-hidden")
        kpr_list = []
        acs_list = []

        for row in rows:
            try:
                date_el = row.select_one(".mod-date")
                if not date_el:
                    continue
                date = datetime.strptime(date_el.text.strip(), "%Y-%m-%d")
                if date < cutoff:
                    break
                stats = row.select("td.mod-stat")
                if len(stats) < 4:
                    continue
                kills  = int(stats[0].text.strip())
                rounds = int(stats[3].text.strip())
                acs    = float(stats[1].text.strip())
                if rounds > 0:
                    kpr_list.append(kills / rounds)
                    acs_list.append(acs)
            except Exception:
                continue

        if not kpr_list:
            return None
        return {
            "recent_kpr":  round(sum(kpr_list) / len(kpr_list), 3),
            "recent_acs":  round(sum(acs_list) / len(acs_list), 1),
            "recent_maps": len(kpr_list),
        }
    except Exception as e:
        print(f"Recent stats scrape error: {e}")
        return None

def get_player_data(player_id: int):
    try:
        profile    = vlr.players.profile(player_id)
        agent_data = vlr.players.agent_stats(player_id)
        match_data = vlr.players.matches(player_id)

        if not agent_data:
            return None

        total_rounds = sum(a.rounds_played for a in agent_data)
        if total_rounds == 0:
            return None

        weighted_kpr = sum(
            a.kpr * (a.rounds_played / total_rounds)
            for a in agent_data
            if a.kpr is not None
        )
        valid_acs    = [(a.acs, a.rounds_played) for a in agent_data if a.acs is not None]
        valid_adr    = [(a.adr, a.rounds_played) for a in agent_data if a.adr is not None]
        acs_rounds   = sum(r for _, r in valid_acs)
        adr_rounds   = sum(r for _, r in valid_adr)
        weighted_acs = sum(v * (r / acs_rounds) for v, r in valid_acs) if acs_rounds > 0 else 0
        weighted_adr = sum(v * (r / adr_rounds) for v, r in valid_adr) if adr_rounds > 0 else 0

        kpr_values = [a.kpr for a in agent_data if a.rounds_played >= 50 and a.kpr is not None]
        std_dev    = statistics.stdev(kpr_values) if len(kpr_values) > 1 else 0.10

        top_agents      = sorted(agent_data, key=lambda a: a.rounds_played, reverse=True)[:3]
        top_agent_names = [a.agent.title() for a in top_agents]

        recent_matches = match_data[:10]
        wins     = sum(1 for m in recent_matches if m.result == "win")
        total    = len(recent_matches)
        win_rate = wins / total if total > 0 else 0.5

        opp_tag = None
        if match_data and match_data[0].opponent_team and match_data[0].opponent_team.tag:
            opp_tag = match_data[0].opponent_team.tag.upper()

        return {
            "handle":       profile.handle,
            "real_name":    profile.real_name,
            "team":         profile.current_teams[0].name if profile.current_teams else "Unknown",
            "weighted_kpr": round(weighted_kpr, 3),
            "weighted_acs": round(weighted_acs, 1),
            "weighted_adr": round(weighted_adr, 1),
            "std_dev":      round(std_dev, 3),
            "total_rounds": total_rounds,
            "top_agents":   top_agent_names,
            "win_rate":     round(win_rate, 2),
            "match_data":   match_data,
            "recent_kpr":   None,
            "recent_maps":  0,
            "auto_opp":     opp_tag,
        }
    except vlr.exceptions.DataNotFoundError:
        print(f"  DataNotFoundError for player_id={player_id}")
        return None
    except Exception as e:
        print(f"Error fetching player {player_id}: {e}")
        return None

def get_h2h_adjustment(match_data, opp_tag: str) -> float:
    h2h_matches = [
        m for m in match_data
        if m.opponent_team is not None
        and m.opponent_team.tag is not None
        and m.opponent_team.tag.upper() == opp_tag.upper()
    ]
    if len(h2h_matches) < 2:
        return 0.0
    wins       = sum(1 for m in h2h_matches if m.result == "win")
    ratio      = wins / len(h2h_matches)
    adjustment = (ratio - 0.5) * 0.08
    return round(adjustment, 3)

def compute_projection(player: dict, opp: str, maps: int = 2) -> dict:
    career_kpr = player["weighted_kpr"]
    recent_kpr = player.get("recent_kpr")

    if recent_kpr and player.get("recent_maps", 0) >= 5:
        base_kpr   = (recent_kpr * 0.6) + (career_kpr * 0.4)
        kpr_source = "recent+career"
    else:
        base_kpr   = career_kpr
        kpr_source = "career only"

    h2h_adj      = get_h2h_adjustment(player["match_data"], opp)
    final_kpr    = base_kpr + h2h_adj
    pace_data    = TEAM_PACE.get(opp.upper(), DEFAULT_PACE)
    avg_rounds   = pace_data["avg_rounds"]
    total_rounds = avg_rounds * maps

    projection = final_kpr * total_rounds
    std_dev    = player["std_dev"]
    low_ci     = (final_kpr - std_dev) * total_rounds
    high_ci    = (final_kpr + std_dev) * total_rounds

    rounds = player["total_rounds"]
    if rounds >= 1500 and std_dev < 0.12:
        confidence = "High 🟢"
    elif rounds >= 800 and std_dev < 0.20:
        confidence = "Medium 🟡"
    else:
        confidence = "Low 🔴"

    h2h_matches = [
        m for m in player["match_data"]
        if m.opponent_team is not None
        and m.opponent_team.tag is not None
        and m.opponent_team.tag.upper() == opp.upper()
    ]

    return {
        "projection":  round(projection, 1),
        "low_ci":      round(low_ci, 1),
        "high_ci":     round(high_ci, 1),
        "final_kpr":   round(final_kpr, 3),
        "h2h_adj":     h2h_adj,
        "avg_rounds":  round(total_rounds, 1),
        "confidence":  confidence,
        "opp_style":   pace_data["style"],
        "h2h_count":   len(h2h_matches),
        "kpr_source":  kpr_source,
        "recent_kpr":  recent_kpr,
        "maps":        maps,
    }

def build_embed(player: dict, result: dict, line: float, opp: str, maps: int) -> tuple:
    proj = result["projection"]
    edge = round(proj - line, 1)
    low  = result["low_ci"]
    high = result["high_ci"]

    if edge > 2.0 and low > line:
        rec   = "✅ BET MORE (OVER)"
        color = 0x2ecc71
        note  = f"{opp}'s {result['opp_style'].lower()} pace supports kill volume across {maps} maps."
    elif edge < -2.0 and high < line:
        rec   = "📉 BET LESS (UNDER)"
        color = 0xe74c3c
        note  = "Projection sits below line even at the top of the confidence range."
    else:
        rec   = "🛑 SKIP"
        color = 0x95a5a6
        note  = f"CI ({low}–{high}) straddles the line — no clean edge."

    if result["h2h_count"] > 0 and result["h2h_adj"] != 0:
        h2h_text = f"{result['h2h_count']} games found (nudge: {result['h2h_adj']:+.3f})"
    elif result["h2h_count"] > 0:
        h2h_text = str(result["h2h_count"]) + " games found (no adjustment)"
    else:
        h2h_text = "No H2H data"

    recent_kpr  = result.get("recent_kpr")
    kpr_display = (
        f"{result['final_kpr']} ({result['kpr_source']})"
        if recent_kpr
        else f"{result['final_kpr']} (career only)"
    )

    embed = discord.Embed(
        title=f"🎯 {player['handle']} ({player['real_name']}) vs {opp} · Maps 1-{maps}",
        description=f"**{rec}**\n{note}",
        color=color,
    )
    embed.add_field(name="Team",             value=player["team"],                          inline=True)
    embed.add_field(name="Our Projection",   value=f"**{proj}** kills",                     inline=True)
    embed.add_field(name="PrizePicks Line",  value=str(line),                               inline=True)
    embed.add_field(name="Edge",             value=f"{edge:+.1f}",                          inline=True)
    embed.add_field(name="Confidence Range", value=f"{low} – {high}",                       inline=True)
    embed.add_field(name="Confidence Tier",  value=result["confidence"],                    inline=True)
    embed.add_field(name="Adjusted KPR",     value=kpr_display,                             inline=True)
    embed.add_field(name="Avg Rounds Total", value=str(result["avg_rounds"]),                inline=True)
    embed.add_field(name="H2H vs Opponent",  value=h2h_text,                                inline=True)
    embed.add_field(name="Career ACS",       value=str(player["weighted_acs"]),              inline=True)
    embed.add_field(name="Career ADR",       value=str(player["weighted_adr"]),              inline=True)
    embed.add_field(name="Recent Win Rate",  value=f"{int(player['win_rate']*100)}%",        inline=True)
    embed.add_field(name="Top Agents",       value=", ".join(player["top_agents"]) or "N/A", inline=False)
    embed.set_footer(text="2026 VCT Matchup Engine v5.0 | Not financial advice")
    return embed, edge

async def fetch_all_prizepicks_valorant():
    try:
        api_url = "https://api.prizepicks.com/projections?league_id=35&per_page=250&single_stat=true&game_mode=pickem"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer":    "https://app.prizepicks.com/",
            "Accept":     "application/json",
            "Origin":     "https://app.prizepicks.com",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                print(f"PrizePicks API status: {r.status}")
                if r.status != 200:
                    print(f"PrizePicks error: {await r.text()}")
                    return None
                data = await r.json()

        projections = data.get("data", [])
        included    = data.get("included", [])
        print(f"PrizePicks: {len(projections)} projections, {len(included)} included")

        pp_players = {
            p["id"]: p["attributes"]["name"]
            for p in included
            if p["type"] == "new_player"
        }

        results = []
        for proj in projections:
            attrs     = proj["attributes"]
            pid       = proj["relationships"]["new_player"]["data"]["id"]
            name      = pp_players.get(pid, "")
            stat_type = attrs.get("stat_type", "")
            if not name or "kills" not in stat_type.lower():
                continue
            if "combo" in stat_type.lower() or "+" in name:
                continue
            maps = 2 if "1-2" in stat_type else 1
            results.append({
                "player":    name,
                "stat_type": stat_type,
                "line":      float(attrs["line_score"]),
                "opponent":  attrs.get("description", ""),
                "maps":      maps,
            })

        print(f"PrizePicks: {len(results)} kills props after filtering")
        return results if results else None
    except Exception as e:
        print(f"PrizePicks fetch error: {e}")
        return None

async def run_scanner():
    await client.wait_until_ready()
    channel = client.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        print(f"⚠️ Alert channel {ALERT_CHANNEL_ID} not found")
        return

    while not client.is_closed():
        try:
            print("🔄 Running full auto prop scan...")
            props = await fetch_all_prizepicks_valorant()

            if not props:
                print("No Valorant kills props found.")
                await asyncio.sleep(1800)
                continue

            print(f"Found {len(props)} props — analyzing...")
            alerts_sent = 0
            skipped     = 0

            async with aiohttp.ClientSession() as session:
                for prop in props:
                    player_name = prop["player"]
                    line        = prop["line"]
                    maps        = prop["maps"]

                    vlr_id = await get_vlr_id(session, player_name)
                    if not vlr_id:
                        skipped += 1
                        continue

                    loop   = asyncio.get_event_loop()
                    player = await loop.run_in_executor(None, get_player_data, vlr_id)
                    if not player:
                        skipped += 1
                        continue

                    recent = await fetch_recent_kpr(session, vlr_id)
                    if recent:
                        player["recent_kpr"]  = recent["recent_kpr"]
                        player["recent_maps"] = recent["recent_maps"]

                    opp    = player.get("auto_opp") or "UNK"
                    result = compute_projection(player, opp, maps)

                    proj_val = result["projection"]
                    edge     = round(proj_val - line, 1)
                    low      = result["low_ci"]
                    high     = result["high_ci"]

                    if edge > 2.0 and low > line:
                        rec   = "✅ OVER"
                        color = 0x2ecc71
                    elif edge < -2.0 and high < line:
                        rec   = "📉 UNDER"
                        color = 0xe74c3c
                    else:
                        continue

                    embed = discord.Embed(
                        title=f"🚨 PROP ALERT — {player['handle']} vs {opp} · Maps 1-{maps}",
                        description=f"**{rec}** | Line: {line} | Projection: {proj_val} | Edge: {edge:+.1f}",
                        color=color,
                    )
                    embed.add_field(name="Team",             value=player["team"],                           inline=True)
                    embed.add_field(name="Confidence Range", value=f"{low} – {high}",                        inline=True)
                    embed.add_field(name="Confidence Tier",  value=result["confidence"],                     inline=True)
                    embed.add_field(name="KPR",              value=str(result["final_kpr"]),                 inline=True)
                    embed.add_field(name="KPR Source",       value=result["kpr_source"],                     inline=True)
                    embed.add_field(name="Top Agents",       value=", ".join(player["top_agents"]) or "N/A", inline=False)
                    embed.set_footer(text="Auto-scan | Not financial advice")
                    await channel.send(embed=embed)
                    alerts_sent += 1
                    await asyncio.sleep(2)

            print(f"✅ Scan complete — {alerts_sent} alert(s) sent, {skipped} skipped.")

        except Exception as e:
            print(f"Scanner error: {e}")

        await asyncio.sleep(1800)

@client.event
async def on_ready():
    print("🤖 2026 MATCHUP MASTER IS LIVE!")
    asyncio.ensure_future(run_scanner())

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!prop"):
        parts = message.content.split()
        if len(parts) < 4:
            await message.channel.send(
                "Usage: `!prop [player_id] [line] [opp] [maps]`\n"
                "Example: `!prop 24895 34.5 DFM 2`"
            )
            return
        try:
            p_id  = int(parts[1])
            line  = float(parts[2])
            opp   = parts[3].upper()
            maps  = int(parts[4]) if len(parts) > 4 else 2
        except ValueError:
            await message.channel.send("⚠️ Invalid arguments.")
            return

        await message.channel.send(f"📡 *Pulling data for `{p_id}` vs `{opp}` — Maps 1-{maps}...*")
        loop   = asyncio.get_event_loop()
        player = await loop.run_in_executor(None, get_player_data, p_id)
        if not player:
            await message.channel.send("❌ Couldn't fetch player data.")
            return

        async with aiohttp.ClientSession() as session:
            recent = await fetch_recent_kpr(session, p_id)
        if recent:
            player["recent_kpr"]  = recent["recent_kpr"]
            player["recent_maps"] = recent["recent_maps"]

        result   = compute_projection(player, opp, maps)
        embed, _ = build_embed(player, result, line, opp, maps)
        await message.channel.send(embed=embed)

    elif message.content.startswith("!addplayer"):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Usage: `!addplayer [name] [vlr_id]`\nExample: `!addplayer Jinggg 2`")
            return
        name = parts[1].lower()
        try:
            pid = int(parts[2])
        except ValueError:
            await message.channel.send("⚠️ VLR ID must be a number.")
            return
        vlr_id_cache[parts[1]] = pid
        KNOWN_PLAYER_IDS[name] = pid
        await message.channel.send(f"✅ Added `{parts[1]}` → VLR ID `{pid}`")

    elif message.content.startswith("!lines"):
        parts = message.content.split(maxsplit=1)
        if len(parts) < 2:
            await message.channel.send("Usage: `!lines [player name]`")
            return
        name  = parts[1]
        props = await fetch_all_prizepicks_valorant()
        if not props:
            await message.channel.send("❌ Couldn't reach PrizePicks right now.")
            return
        matches = [p for p in props if name.lower() in p["player"].lower()]
        if not matches:
            await message.channel.send(f"❌ No active kills lines found for `{name}`.")
            return
        embed = discord.Embed(title=f"📋 PrizePicks Lines — {name}", color=0x9b59b6)
        for entry in matches:
            embed.add_field(name=entry["stat_type"], value=f"Line: **{entry['line']}**", inline=False)
        embed.set_footer(text="Live from PrizePicks | Not financial advice")
        await message.channel.send(embed=embed)

    elif message.content.startswith("!analyze"):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send(
                "Usage: `!analyze [player_name] [opp]`\n"
                "Example: `!analyze Jinggg PRX`"
            )
            return
        player_name = parts[1]
        opp         = parts[2].upper()

        await message.channel.send(f"📡 *Looking up `{player_name}`...*")

        async with aiohttp.ClientSession() as session:
            vlr_id, props = await asyncio.gather(
                get_vlr_id(session, player_name),
                fetch_all_prizepicks_valorant(),
            )

        if not vlr_id:
            await message.channel.send(
                f"❌ Couldn't find `{player_name}` on vlr.gg.\n"
                f"Add manually: `!addplayer {player_name} [vlr_id]`"
            )
            return

        loop   = asyncio.get_event_loop()
        player = await loop.run_in_executor(None, get_player_data, vlr_id)
        if not player:
            await message.channel.send("❌ Couldn't fetch player data.")
            return

        async with aiohttp.ClientSession() as session:
            recent = await fetch_recent_kpr(session, vlr_id)
        if recent:
            player["recent_kpr"]  = recent["recent_kpr"]
            player["recent_maps"] = recent["recent_maps"]

        kills_line = None
        maps       = 2
        if props:
            for p in props:
                if player_name.lower() in p["player"].lower():
                    kills_line = p["line"]
                    maps       = p["maps"]
                    break

        if not kills_line:
            await message.channel.send(
                f"⚠️ No kills line on PrizePicks for `{player_name}`.\n"
                f"Use: `!prop {vlr_id} [line] {opp} 2`"
            )
            return

        result   = compute_projection(player, opp, maps)
        embed, _ = build_embed(player, result, kills_line, opp, maps)
        await message.channel.send(embed=embed)

    elif message.content.startswith("!scan"):
        await message.channel.send("🔄 *Triggering manual scan...*")
        asyncio.ensure_future(run_scanner())

    elif message.content.startswith("!help"):
        embed = discord.Embed(title="🤖 Matchup Master — Commands", color=0x9b59b6)
        embed.add_field(name="!analyze [player] [opp]",        value="Auto-lookup + live line.\n`!analyze Jinggg PRX`",   inline=False)
        embed.add_field(name="!addplayer [name] [vlr_id]",     value="Manually cache a VLR ID.\n`!addplayer Jinggg 2`",   inline=False)
        embed.add_field(name="!lines [player]",                value="See active PrizePicks lines.\n`!lines Jinggg`",      inline=False)
        embed.add_field(name="!prop [id] [line] [opp] [maps]", value="Manual entry.\n`!prop 24895 34.5 DFM 2`",           inline=False)
        embed.add_field(name="!scan",                          value="Trigger immediate full scan.",                       inline=False)
        embed.add_field(name="Auto-scanner",                   value="Runs every 30 min, posts alerts for strong edges.",  inline=False)
        embed.set_footer(text="2026 VCT Matchup Engine v5.0 | Not financial advice")
        await message.channel.send(embed=embed)

async def main():
    await asyncio.gather(
        start_webserver(),
        client.start(TOKEN),
    )

asyncio.run(main())
