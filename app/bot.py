import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Windows에서는 discord.py 번들 opus를 명시적으로 로드해야 음성 송출이 됨
if not discord.opus.is_loaded():
    try:
        opus_path = os.path.join(os.path.dirname(discord.__file__), "bin", "libopus-0.x64.dll")
        discord.opus.load_opus(opus_path)
        print(f"[OK] opus 로드: {discord.opus.is_loaded()}")
    except Exception as e:
        print(f"[ERROR] opus 로드 실패: {e}")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
STATUS = os.getenv("BOT_STATUS", "/도움말")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"[OK] {bot.user.name} 시작됨 | 서버 {len(bot.guilds)}개")
    
    for vc in bot.voice_clients:
        try:
            await vc.disconnect(force=True)
            print(f"[OK] 기존 음성 연결 정리: {vc.guild.name}")
        except Exception:
            pass
    
    try:
        synced = await bot.tree.sync()
        print(f"[OK] 명령어 {len(synced)}개 동기화")
    except Exception as e:
        print(f"[ERROR] {e}")

    activity = discord.Activity(type=discord.ActivityType.listening, name=STATUS)
    await bot.change_presence(activity=activity)


@bot.event
async def on_guild_join(guild):
    try:
        await bot.tree.sync(guild=guild)
    except Exception:
        pass


async def main():
    if not TOKEN:
        print("[ERROR] DISCORD_TOKEN 없음")
        return

    for cog in ["music_cog", "prayer_cog"]:
        try:
            await bot.load_extension(cog)
            print(f"[OK] {cog} 로드")
        except Exception as e:
            print(f"[ERROR] {cog}: {e}")

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
