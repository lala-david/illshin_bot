import os
import asyncio
import random
from collections import deque
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Song:
    def __init__(self, source: str, data: dict, requester: discord.Member):
        self.source = source
        self.title = data.get("title", "알 수 없음")
        self.url = data.get("webpage_url", "")
        self.duration = data.get("duration", 0)
        self.thumbnail = data.get("thumbnail", "")
        self.uploader = data.get("uploader", "알 수 없음")
        self.requester = requester

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "LIVE"
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def embed(self, title: str = "🎵 현재 재생 중") -> discord.Embed:
        e = discord.Embed(title=title, description=f"**[{self.title}]({self.url})**", color=0x2ECC71)
        e.add_field(name="⏱️", value=self.duration_str, inline=True)
        e.add_field(name="📺", value=self.uploader, inline=True)
        e.add_field(name="👤", value=self.requester.mention, inline=True)
        if self.thumbnail:
            e.set_thumbnail(url=self.thumbnail)
        return e


class Player:
    def __init__(self, bot: commands.Bot, guild: discord.Guild, channel: discord.TextChannel):
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.queue: deque[Song] = deque()
        self.current: Song | None = None
        self.volume = 0.5
        self.loop = False
        self.loop_queue = False
        self.stopped = False
        self.next = asyncio.Event()
        self.task = bot.loop.create_task(self._loop())

    async def _loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            if not self.loop:
                try:
                    async with asyncio.timeout(600):
                        if self.queue:
                            self.current = self.queue.popleft()
                            if self.loop_queue:
                                self.queue.append(self.current)
                        else:
                            self.current = None
                            if not self.stopped:
                                await self.channel.send("📭 재생목록이 비어있습니다.")
                            self.stopped = False
                            await self.next.wait()
                            continue
                except asyncio.TimeoutError:
                    await self.channel.send("⏰ 10분간 활동이 없어 퇴장합니다.")
                    if self.guild.voice_client:
                        await self.guild.voice_client.disconnect()
                    return

            if not self.current:
                continue

            try:
                vc = self.guild.voice_client
                if not vc or not vc.is_connected():
                    await self.channel.send("❌ 음성 채널 연결이 끊어졌습니다.")
                    return

                source = discord.FFmpegPCMAudio(self.current.source, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=self.volume)

                def _after(error):
                    if error:
                        print(f"[PLAYER ERROR] {error}")
                        asyncio.run_coroutine_threadsafe(
                            self.channel.send(f"⚠️ 재생 오류: {error}"),
                            self.bot.loop,
                        )
                    self.bot.loop.call_soon_threadsafe(self.next.set)

                vc.play(source, after=_after)
                if not self.loop:
                    await self.channel.send(embed=self.current.embed())
            except Exception as e:
                await self.channel.send(f"❌ 오류: {e}")

            await self.next.wait()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, Player] = {}

    def _player(self, guild: discord.Guild, channel: discord.TextChannel) -> Player:
        # 죽은 Player 제거 (타임아웃 퇴장 후 재사용 방지)
        if guild.id in self.players and self.players[guild.id].task.done():
            self.players.pop(guild.id)
        if guild.id not in self.players:
            self.players[guild.id] = Player(self.bot, guild, channel)
        return self.players[guild.id]

    async def _cleanup(self, guild: discord.Guild):
        if guild.voice_client:
            await guild.voice_client.disconnect()
        self.players.pop(guild.id, None)

    async def _get_songs(self, url: str, requester: discord.Member) -> tuple[list[Song], str | None]:
        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )
            
            songs = []

            if data is None:
                return [], "영상 정보를 가져올 수 없습니다. 다시 시도해주세요."

            if "entries" in data:
                for entry in data["entries"]:
                    if entry and entry.get("url"):
                        songs.append(Song(entry["url"], entry, requester))
            else:
                song_url = data.get("url") or data.get("webpage_url")
                if song_url:
                    songs.append(Song(song_url, data, requester))
                else:
                    return [], "영상 URL을 가져올 수 없습니다."
            
            return songs, None
        except Exception as e:
            return [], str(e)

    @app_commands.command(name="입장", description="음성 채널 입장")
    async def join(self, i: discord.Interaction):
        if not i.user.voice:
            return await i.response.send_message("❌ 음성 채널에 먼저 입장하세요!", ephemeral=True)
        await i.response.defer()
        ch = i.user.voice.channel
        try:
            if i.guild.voice_client:
                await i.guild.voice_client.move_to(ch)
            else:
                await ch.connect(timeout=20.0, reconnect=True)
        except Exception as e:
            return await i.followup.send(f"❌ 입장 실패: {e}")
        await i.followup.send(f"🔊 **{ch.name}** 입장!")

    @app_commands.command(name="퇴장", description="음성 채널 퇴장")
    async def leave(self, i: discord.Interaction):
        if not i.guild.voice_client:
            return await i.response.send_message("❌ 봇이 채널에 없습니다!", ephemeral=True)
        await i.response.defer()
        await self._cleanup(i.guild)
        await i.followup.send("👋 퇴장!")

    @app_commands.command(name="재생", description="음악 재생 (재생목록 URL도 가능)")
    @app_commands.describe(url="유튜브 URL, 재생목록 URL 또는 검색어")
    async def play(self, i: discord.Interaction, url: str):
        if not i.user.voice:
            return await i.response.send_message("❌ 음성 채널에 먼저 입장하세요!", ephemeral=True)

        # 순수 재생목록 URL인지 확인 (/playlist?list=... 형식만)
        is_playlist = "/playlist" in url and "list=" in url

        # 단일 영상 URL에 list= 파라미터가 붙어있으면 제거 (전체 재생목록 로딩 방지)
        if not is_playlist and "list=" in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            params.pop("list", None)
            params.pop("index", None)
            url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

        if is_playlist:
            await i.response.send_message("📂 재생목록이네요!\n\n곡들이 많아 조금 기다려주세요! 😎\n\n⏳ 불러오는 중...")
            msg = await i.original_response()
        else:
            await i.response.defer()

        if not i.guild.voice_client:
            try:
                await i.user.voice.channel.connect(timeout=20.0, reconnect=True)
            except Exception as e:
                if is_playlist:
                    return await msg.edit(content=f"❌ 음성 연결 실패: {e}")
                return await i.followup.send(f"❌ 음성 연결 실패: {e}")

        songs, err = await self._get_songs(url, i.user)
        if err:
            if is_playlist:
                return await msg.edit(content=f"❌ 오류: {err}")
            return await i.followup.send(f"❌ {err}")
        if not songs:
            if is_playlist:
                return await msg.edit(content="❌ 노래를 찾을 수 없습니다!")
            return await i.followup.send("❌ 노래를 찾을 수 없습니다!")

        p = self._player(i.guild, i.channel)
        
        for song in songs:
            p.queue.append(song)

        if len(songs) == 1:
            song = songs[0]
            if len(p.queue) > 1 or p.current:
                e = discord.Embed(title="📋 추가됨", description=f"**{song.title}**", color=0x3498DB)
                e.add_field(name="대기", value=f"{len(p.queue)}번째")
                await i.followup.send(embed=e)
            else:
                p.next.set()
                await i.followup.send(f"🎵 **{song.title}** 재생 준비...")
        else:
            e = discord.Embed(
                title="✅ 재생목록 추가 완료!",
                description=f"**{len(songs)}곡**이 추가되었습니다!",
                color=0x2ECC71
            )
            
            song_list = []
            for idx, s in enumerate(songs[:15], 1):
                song_list.append(f"`{idx}.` {s.title}")
            if len(songs) > 15:
                song_list.append(f"... 외 **{len(songs)-15}곡**")
            
            e.add_field(name="🎵 추가된 곡 목록", value="\n".join(song_list), inline=False)
            await msg.edit(content=None, embed=e)
            
            if not p.current:
                p.next.set()

    @app_commands.command(name="일시정지", description="일시정지")
    async def pause(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if not vc or not vc.is_playing():
            return await i.response.send_message("❌ 재생 중인 음악이 없습니다!", ephemeral=True)
        vc.pause()
        await i.response.send_message("⏸️ 일시정지")

    @app_commands.command(name="계속", description="다시 재생")
    async def resume(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if not vc:
            return await i.response.send_message("❌ 봇이 채널에 없습니다!", ephemeral=True)
        if vc.is_paused():
            vc.resume()
            await i.response.send_message("▶️ 재생")
        else:
            await i.response.send_message("❌ 일시정지 상태가 아닙니다!", ephemeral=True)

    @app_commands.command(name="정지", description="정지")
    async def stop(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if not vc:
            return await i.response.send_message("❌ 봇이 채널에 없습니다!", ephemeral=True)
        p = self._player(i.guild, i.channel)
        p.queue.clear()
        p.current = None
        p.loop = False
        p.loop_queue = False
        p.stopped = True
        if vc.is_playing():
            vc.stop()
        await i.response.send_message("⏹️ 정지")

    @app_commands.command(name="스킵", description="다음 곡")
    async def skip(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if not vc or not vc.is_playing():
            return await i.response.send_message("❌ 재생 중인 음악이 없습니다!", ephemeral=True)
        self._player(i.guild, i.channel).loop = False
        vc.stop()
        await i.response.send_message("⏭️ 스킵")

    @app_commands.command(name="재생목록", description="재생목록")
    async def queue(self, i: discord.Interaction):
        p = self._player(i.guild, i.channel)
        if not p.current and not p.queue:
            return await i.response.send_message("📭 비어있습니다!", ephemeral=True)

        e = discord.Embed(title="📋 재생목록", color=0x9B59B6)
        if p.current:
            e.add_field(name="🎵 현재" + (" 🔂" if p.loop else ""), value=f"**{p.current.title}**", inline=False)
        if p.queue:
            items = [f"`{n}.` {s.title}" for n, s in enumerate(list(p.queue)[:10], 1)]
            if len(p.queue) > 10:
                items.append(f"... 외 {len(p.queue)-10}곡")
            e.add_field(name=f"📑 대기 ({len(p.queue)}곡)", value="\n".join(items), inline=False)
        await i.response.send_message(embed=e)

    @app_commands.command(name="반복", description="현재 곡 반복")
    async def loop(self, i: discord.Interaction):
        p = self._player(i.guild, i.channel)
        p.loop = not p.loop
        await i.response.send_message(f"🔂 반복 **{'ON' if p.loop else 'OFF'}**")

    @app_commands.command(name="전체반복", description="재생목록 반복")
    async def loop_queue(self, i: discord.Interaction):
        p = self._player(i.guild, i.channel)
        p.loop_queue = not p.loop_queue
        await i.response.send_message(f"🔁 전체반복 **{'ON' if p.loop_queue else 'OFF'}**")

    @app_commands.command(name="셔플", description="재생목록 섞기")
    async def shuffle(self, i: discord.Interaction):
        p = self._player(i.guild, i.channel)
        if len(p.queue) < 2:
            return await i.response.send_message("❌ 2곡 이상 필요!", ephemeral=True)
        items = list(p.queue)
        random.shuffle(items)
        p.queue = deque(items)
        await i.response.send_message("🔀 셔플!")

    @app_commands.command(name="현재곡", description="현재 곡 정보")
    async def now(self, i: discord.Interaction):
        p = self._player(i.guild, i.channel)
        if not p.current:
            return await i.response.send_message("❌ 재생 중인 음악이 없습니다!", ephemeral=True)
        await i.response.send_message(embed=p.current.embed())

    @app_commands.command(name="볼륨", description="볼륨 (0-100)")
    @app_commands.describe(vol="볼륨")
    async def volume(self, i: discord.Interaction, vol: int | None = None):
        p = self._player(i.guild, i.channel)
        if vol is None:
            return await i.response.send_message(f"🔊 **{int(p.volume*100)}%**")
        if not 0 <= vol <= 100:
            return await i.response.send_message("❌ 0~100!", ephemeral=True)
        p.volume = vol / 100
        if i.guild.voice_client and i.guild.voice_client.source:
            i.guild.voice_client.source.volume = p.volume
        await i.response.send_message(f"🔊 **{vol}%**")

    @app_commands.command(name="비우기", description="재생목록 비우기")
    async def clear(self, i: discord.Interaction):
        self._player(i.guild, i.channel).queue.clear()
        await i.response.send_message("🗑️ 비움!")

    @app_commands.command(name="도움말", description="명령어")
    async def help(self, i: discord.Interaction):
        e = discord.Embed(title="🎵 일신봇", color=0xF1C40F)
        e.add_field(name="기본", value="`/입장` `/퇴장`", inline=False)
        e.add_field(name="재생", value="`/재생` `/일시정지` `/계속` `/정지` `/스킵`", inline=False)
        e.add_field(name="목록", value="`/재생목록` `/비우기` `/셔플`", inline=False)
        e.add_field(name="기타", value="`/반복` `/전체반복` `/현재곡` `/볼륨`", inline=False)
        e.add_field(name="🙏 기도", value="`/기도` `/기도목록` `/이번주기도목록` `/기도삭제`", inline=False)
        e.set_footer(text="✝ 일신교회 청년부")
        await i.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
