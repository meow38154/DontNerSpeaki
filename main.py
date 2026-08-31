import os

import discord
from discord import app_commands
from dotenv import load_dotenv
from discord.ext import tasks
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta, time

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
KST = ZoneInfo("Asia/Seoul")

allSchedules: list[tuple[date, str, bool]] = []

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)

        self.tree.copy_global_to(guild=guild)

        commands = await self.tree.sync(guild=guild)

        print(f"{len(commands)}개의 명령어 등록 완료")


bot = MyBot()

file_path = "Schedule.txt"

def load_schedules():
    allSchedules.clear()

    if not os.path.exists(file_path):
        return

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                date_text, rest = line.split(" ", 1)
                content, important_text = rest.rsplit(" ", 1)

                schedule_date = datetime.strptime(
                    date_text,
                    "%Y-%m-%d"
                ).date()

                important = important_text == "True"

                allSchedules.append(
                    (schedule_date, content, important)
                )

            except ValueError:
                print(f"잘못된 일정 형식: {line}")

    sort_schedules()

@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 성공!")

    load_schedules()

    if not schedule_notifier.is_running():
        schedule_notifier.start()


@bot.tree.command(
    name="일정추가",
    description="일정을 추가합니다."
)
@app_commands.describe(
    month="월",
    days="일정 날짜",
    content="일정 내용",
    important="중요 여부 (선택 사항, 기본값: False)"
)
async def add_schedule(
    interaction: discord.Interaction,
    month: str,
    days: str,
    content: str,
    important: bool = False
):
    
    if not days or not content:
        await interaction.response.send_message("일정 추가에 필요한 정보를 모두 입력해주세요.")
        return

    await interaction.response.send_message(
        f"일정이 추가되었습니다.\n"
        f"날짜: {month}월 {days}일\n"
        f"내용: {content}\n"
        f"중요한 일정 여부: {'맞음' if important else '아님'}",
        ephemeral=True
    )

    allSchedules.append((date(2026, int(month), int(days)), content, important))
    refresh_notepad()


@bot.tree.command(
    name="일정제거",
    description="가장 최근에 등록된 일정을 제거합니다."
)
async def remove_schedule(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    if not allSchedules:
        await interaction.edit_original_response(
            content="등록된 일정이 없습니다."
        )
        return

    removed_date, removed_content, removed_important = allSchedules.pop()

    await interaction.edit_original_response(
        content=(
        f"날짜: {removed_date}\n"
        f"내용: {removed_content}\n"
        f"일정이 제거되었습니다.")
    )

    refresh_notepad()


@bot.tree.command(
    name="일정정리",
    description="모든 일정을 표시합니다."
)
async def show_schedules(
    interaction: discord.Interaction
):
    if not allSchedules:
        await interaction.response.send_message(
            "등록된 일정이 없습니다.",
            ephemeral=True
        )
        return

    message = ""

    for schedule_date, content, important in allSchedules:
        message += f"날짜: {schedule_date} 내용: {content}\n"

    await interaction.response.send_message(message)


#일정 정렬
def sort_schedules():
    allSchedules.sort(key=lambda x: x[0])

#메모장 새로고침
def refresh_notepad():
    sort_schedules()

    with open(file_path, "w", encoding="utf-8") as f:
        for schedule_date, content, important in allSchedules:
            f.write(f"{schedule_date} {content} {important}\n")


@tasks.loop(minutes=1)
async def schedule_notifier():
    now = datetime.now(KST)
    today = now.date()

    allSchedules[:] = [
        schedule
        for schedule in allSchedules
        if schedule[0] >= today
    ]

    refresh_notepad()

    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        channel = await bot.fetch_channel(CHANNEL_ID)

    for schedule_date, content, important in allSchedules:
        notify_date = schedule_date - timedelta(days=1)

        if now.date() != notify_date:
            continue

        if now.hour == 20 and now.minute == 30:
            await channel.send(
                f"내일 {content} 일정이 있습니다.\n"
                f"날짜: {schedule_date}"
            )

    today = now.date()

    is_sunday = today.weekday() == 6

    if is_sunday and now.hour in [12, 15, 18, 21] and now.minute == 0:
        await channel.send("오늘까지 배움일지 작성하세요.")

    is_friday = today.weekday() == 4

    if is_friday and now.hour in [13] and now.minute == 0:
        for important_schedule in allSchedules:
            if important_schedule[2]:
                await channel.send(
                    f"{important_schedule[1]} 일정이 있습니다.\n"
                    f"날짜: {important_schedule[0]}"
                )


bot.run(TOKEN)