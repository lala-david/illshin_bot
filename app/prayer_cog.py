import json
import os
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from discord import app_commands


DATA_DIR = "data"


def get_today_file() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(DATA_DIR, f"{today}.json")


def load_prayers_by_date(date_str: str) -> list:
    filepath = os.path.join(DATA_DIR, f"{date_str}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for p in data:
                p["date"] = date_str
            return data
    return []


def load_today_prayers() -> list:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = get_today_file()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_week_prayers() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    
    week_prayers = {}
    for i in range(7):
        date = monday + timedelta(days=i)
        if date > today:
            break
        date_str = date.strftime("%Y-%m-%d")
        prayers = load_prayers_by_date(date_str)
        if prayers:
            week_prayers[date_str] = prayers
    
    return week_prayers


def save_today_prayers(prayers: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(get_today_file(), "w", encoding="utf-8") as f:
        json.dump(prayers, f, ensure_ascii=False, indent=2)


def build_today_prayer_embed() -> discord.Embed | None:
    prayers = load_today_prayers()
    
    if not prayers:
        return None
    
    by_author = {}
    for p in prayers:
        aid = p["author_id"]
        if aid not in by_author:
            by_author[aid] = {"name": p["author"], "prayers": []}
        by_author[aid]["prayers"].append(p)
    
    for aid in by_author:
        by_author[aid]["prayers"].sort(key=lambda x: x["time"])
    
    sorted_authors = sorted(by_author.items(), key=lambda x: x[1]["name"])
    
    today = datetime.now().strftime("%Y년 %m월 %d일")
    
    e = discord.Embed(
        title=f"📋 오늘의 기도제목",
        description=f"**{today}** | 총 **{len(prayers)}개**",
        color=0x9B59B6
    )
    
    for aid, data in sorted_authors:
        lines = []
        for idx, p in enumerate(data["prayers"], 1):
            lines.append(f"**{idx}.** {p['content']}\n　　🕐 _{p['time']}_")
        
        e.add_field(
            name=f"✝️ {data['name']} ({len(data['prayers'])}개)",
            value="\n\n".join(lines),
            inline=False
        )
    
    e.set_footer(text="🙏 함께 기도해요! | ✝ 일신교회 청년부")
    return e


def build_week_prayer_embed() -> discord.Embed | None:
    week = load_week_prayers()
    
    if not week:
        return None
    
    all_prayers = []
    for prayers in week.values():
        all_prayers.extend(prayers)
    
    by_author = {}
    for p in all_prayers:
        aid = p["author_id"]
        if aid not in by_author:
            by_author[aid] = {"name": p["author"], "prayers": []}
        by_author[aid]["prayers"].append(p)
    
    for aid in by_author:
        by_author[aid]["prayers"].sort(key=lambda x: (x["date"], x["time"]))
    
    sorted_authors = sorted(by_author.items(), key=lambda x: x[1]["name"])
    
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    week_str = f"{monday.strftime('%m/%d')} ~ {sunday.strftime('%m/%d')}"
    
    e = discord.Embed(
        title=f"📅 이번주 기도제목",
        description=f"**{week_str}** | 총 **{len(all_prayers)}개**의 기도제목",
        color=0x3498DB
    )
    
    for aid, data in sorted_authors:
        lines = []
        for idx, p in enumerate(data["prayers"], 1):
            date = datetime.strptime(p["date"], "%Y-%m-%d")
            day_name = ["월", "화", "수", "목", "금", "토", "일"][date.weekday()]
            lines.append(f"**{idx}.** {p['content']}\n　　📆 _{date.strftime('%m/%d')}({day_name}) {p['time']}_")
        
        e.add_field(
            name=f"✝️ {data['name']} ({len(data['prayers'])}개)",
            value="\n\n".join(lines),
            inline=False
        )
    
    e.set_footer(text="🙏 함께 기도해요! | ✝ 일신교회 청년부")
    return e


class PrayerModal(discord.ui.Modal, title="🙏 기도제목 등록"):
    prayer = discord.ui.TextInput(
        label="기도제목",
        placeholder="기도제목을 입력해주세요...",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, i: discord.Interaction):
        prayers = load_today_prayers()
        
        new_prayer = {
            "id": max((p["id"] for p in prayers), default=0) + 1,
            "content": self.prayer.value,
            "author": i.user.display_name,
            "author_id": i.user.id,
            "time": datetime.now().strftime("%H:%M")
        }
        
        prayers.append(new_prayer)
        save_today_prayers(prayers)
        
        today = datetime.now().strftime("%Y년 %m월 %d일")
        e = discord.Embed(
            title="✅ 기도제목이 등록되었습니다!",
            description=f"```{self.prayer.value}```",
            color=0x2ECC71
        )
        e.set_footer(text=f"🙏 {today} | {i.user.display_name}")
        await i.response.send_message(embed=e)


class PrayerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="기도제목 등록", style=discord.ButtonStyle.primary, emoji="✏️")
    async def add_prayer(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.send_modal(PrayerModal())

    @discord.ui.button(label="오늘 기도제목", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_prayers(self, i: discord.Interaction, button: discord.ui.Button):
        embed = build_today_prayer_embed()
        if embed is None:
            today = datetime.now().strftime("%Y년 %m월 %d일")
            return await i.response.send_message(f"📭 오늘({today}) 등록된 기도제목이 없습니다.", ephemeral=True)
        await i.response.send_message(embed=embed)

    @discord.ui.button(label="이번주 기도제목", style=discord.ButtonStyle.success, emoji="📅")
    async def week_prayers(self, i: discord.Interaction, button: discord.ui.Button):
        embed = build_week_prayer_embed()
        if embed is None:
            return await i.response.send_message("📭 이번주 등록된 기도제목이 없습니다.", ephemeral=True)
        await i.response.send_message(embed=embed)


class Prayer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="기도", description="기도제목을 나누어요")
    async def prayer(self, i: discord.Interaction):
        today = datetime.now().strftime("%Y년 %m월 %d일")
        prayers = load_today_prayers()
        
        e = discord.Embed(
            title="🙏 기도제목",
            description=f"기도가 있으시면 일신봇에게 말해주세요!\n\n"
                       f"📅 오늘 ({today}) 기도제목: **{len(prayers)}개**",
            color=0xF39C12
        )
        e.set_footer(text="✝ 일신교회 청년부 | 함께 기도해요!")
        
        await i.response.send_message(embed=e, view=PrayerView())

    @app_commands.command(name="기도목록", description="오늘의 기도제목을 보여줍니다")
    async def prayer_list(self, i: discord.Interaction):
        embed = build_today_prayer_embed()
        if embed is None:
            today = datetime.now().strftime("%Y년 %m월 %d일")
            return await i.response.send_message(f"📭 오늘({today}) 등록된 기도제목이 없습니다.")
        await i.response.send_message(embed=embed)

    @app_commands.command(name="이번주기도목록", description="이번주 기도제목을 보여줍니다")
    async def week_prayer_list(self, i: discord.Interaction):
        embed = build_week_prayer_embed()
        if embed is None:
            return await i.response.send_message("📭 이번주 등록된 기도제목이 없습니다.")
        await i.response.send_message(embed=embed)

    @app_commands.command(name="기도삭제", description="기도제목을 삭제합니다")
    @app_commands.describe(번호="삭제할 기도제목 번호")
    async def delete_prayer(self, i: discord.Interaction, 번호: int):
        prayers = load_today_prayers()
        
        for idx, p in enumerate(prayers):
            if p["id"] == 번호:
                if p["author_id"] == i.user.id or i.user.guild_permissions.administrator:
                    prayers.pop(idx)
                    save_today_prayers(prayers)
                    return await i.response.send_message(f"🗑️ 기도제목 #{번호} 삭제됨", ephemeral=True)
                else:
                    return await i.response.send_message("❌ 본인의 기도제목만 삭제할 수 있어요!", ephemeral=True)
        
        await i.response.send_message(f"❌ #{번호} 기도제목을 찾을 수 없어요!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Prayer(bot))

