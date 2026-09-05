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

allSchedules: list[tuple[date, str, bool, str | None]] = []


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
op_file_path = "opList.txt"
mention_file_path = "mentionList.txt"
images_path = "Images"


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
                date_text, content, important_text, image = line.split("|", 3)

                schedule_date = datetime.strptime(
                    date_text,
                    "%Y-%m-%d"
                ).date()

                important = important_text == "True"

                if image == "None" or image == "":
                    image = None

                allSchedules.append(
                    (schedule_date, content, important, image)
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
    image="등록된 이미지 경로 (선택 사항, 예: Images/test.png)",
    important="중요 여부 (선택 사항, 기본값: False)"
)
async def add_schedule(
    interaction: discord.Interaction,
    month: str,
    days: str,
    content: str,
    image: str | None = None,
    important: bool = False
):
    now = datetime.now(KST)

    print(
        f"[{now:%Y-%m-%d %H:%M:%S}] "
        f"{interaction.user.display_name} "
        f"/일정추가 사용"
    )

    if not is_op_user(interaction.user):
        await interaction.response.send_message(
            "권한이 없습니다.",
            ephemeral=True
        )
        return

    if not days or not content:
        await interaction.response.send_message(
            "일정 추가에 필요한 정보를 모두 입력해주세요.",
            ephemeral=True
        )
        return

    try:
        schedule_date = date(
            2026,
            int(month),
            int(days)
        )
    except ValueError:
        await interaction.response.send_message(
            "올바른 날짜를 입력해주세요.",
            ephemeral=True
        )
        return

    if image and not os.path.isfile(image):
        await interaction.response.send_message(
            f"이미지를 찾을 수 없습니다.\n"
            f"경로: `{image}`",
            ephemeral=True
        )
        return

    allSchedules.append(
        (
            schedule_date,
            content,
            important,
            image
        )
    )

    refresh_notepad()

    await interaction.response.send_message(
        f"일정이 추가되었습니다.\n"
        f"날짜: {month}월 {days}일\n"
        f"내용: {content}\n"
        f"이미지: {image if image else '없음'}\n"
        f"중요한 일정 여부: {'맞음' if important else '아님'}",
        ephemeral=True
    )


@bot.tree.command(
    name="일정제거",
    description="가장 최근에 등록된 일정을 제거합니다."
)
async def remove_schedule(interaction: discord.Interaction):

    now = datetime.now(KST)

    print(
        f"[{now:%Y-%m-%d %H:%M:%S}] "
        f"{interaction.user.display_name} "
        f"/일정제거 사용"
    )

    if not is_op_user(interaction.user):
        await interaction.response.send_message(
            "권한이 없습니다.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    if not allSchedules:
        await interaction.edit_original_response(
            content="등록된 일정이 없습니다."
        )
        return

    removed_date, removed_content, removed_important, removed_image = allSchedules.pop()

    await interaction.edit_original_response(
        content=(
            f"날짜: {removed_date}\n"
            f"내용: {removed_content}\n"
            f"일정이 제거되었습니다."
        )
    )

    refresh_notepad()

class ScheduleImageButton(discord.ui.Button):
    def __init__(
        self,
        content: str,
        image_path: str
    ):
        super().__init__(
            label=f"{content} 이미지"[:80],
            style=discord.ButtonStyle.secondary
        )

        self.image_path = image_path

    async def callback(
        self,
        interaction: discord.Interaction
    ):
        if not os.path.isfile(self.image_path):
            await interaction.response.send_message(
                "등록된 이미지 파일을 찾을 수 없습니다.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(self.image_path),
            ephemeral=True
        )


class ScheduleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

        button_count = 0

        for schedule_date, content, important, image in allSchedules:
            if not image:
                continue

            if button_count >= 25:
                break

            self.add_item(
                ScheduleImageButton(
                    content,
                    image
                )
            )

            button_count += 1


@bot.tree.command(
    name="일정정리",
    description="모든 일정을 표시합니다."
)
async def show_schedules(
    interaction: discord.Interaction
):
    now = datetime.now(KST)

    print(
        f"[{now:%Y-%m-%d %H:%M:%S}] "
        f"{interaction.user.display_name} "
        f"/일정정리 사용"
    )

    if not allSchedules:
        await interaction.response.send_message(
            "등록된 일정이 없습니다.",
            ephemeral=True
        )
        return

    message = ""

    for schedule_date, content, important, image in allSchedules:
        message += f"날짜: {schedule_date} 내용: {content}\n"

    view = ScheduleView()

    await interaction.response.send_message(
        message,
        view=view if view.children else None,
        ephemeral=True
    )


@bot.tree.command(
    name="이미지등록",
    description="이미지를 등록합니다."
)
@app_commands.describe(
    name="저장할 이미지 이름",
    image="등록할 이미지"
)
async def register_image(
    interaction: discord.Interaction,
    name: str,
    image: discord.Attachment
):
    if not is_op_user(interaction.user):
        await interaction.response.send_message(
            "권한이 없습니다.",
            ephemeral=True
        )
        return

    # main.py가 있는 위치
    base_path = os.path.dirname(os.path.abspath(__file__))

    # /home/container/Images 같은 절대 경로
    image_directory = os.path.join(base_path, "Images")

    os.makedirs(image_directory, exist_ok=True)

    extension = os.path.splitext(image.filename)[1]
    file_name = f"{name}{extension}"

    image_path = os.path.join(
        image_directory,
        file_name
    )

    try:
        # 디스코드에 올라온 이미지 데이터 직접 읽기
        image_data = await image.read()

        # 실제 파일로 직접 저장
        with open(image_path, "wb") as f:
            f.write(image_data)

    except Exception as e:
        await interaction.response.send_message(
            f"이미지 저장 실패:\n`{e}`",
            ephemeral=True
        )
        return

    # 진짜 저장됐는지 검사
    if not os.path.isfile(image_path):
        await interaction.response.send_message(
            f"파일 저장에 실패했습니다.\n"
            f"`{image_path}`",
            ephemeral=True
        )
        return

    file_size = os.path.getsize(image_path)

    print(f"이미지 저장 완료: {image_path}")
    print(f"파일 크기: {file_size} bytes")
    print(f"Images 폴더 내용: {os.listdir(image_directory)}")

    await interaction.response.send_message(
        f"이미지가 등록되었습니다.\n"
        f"이름: `{file_name}`\n"
        f"크기: `{file_size} bytes`\n"
        f"저장 경로: `{image_path}`",
        ephemeral=True
    )
# 일정 정렬
def sort_schedules():
    allSchedules.sort(
        key=lambda x: x[0]
    )


# 메모장 새로고침
def refresh_notepad():
    sort_schedules()

    with open(file_path, "w", encoding="utf-8") as f:
        for schedule_date, content, important, image in allSchedules:
            f.write(
                f"{schedule_date}|{content}|{important}|{image}\n"
            )


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

    for schedule_date, content, important, image in allSchedules:
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
        await channel.send(
            "오늘까지 배움일지 작성하세요."
        )

    is_friday = today.weekday() == 4

    if is_friday and now.hour in [13] and now.minute == 0:
        for important_schedule in allSchedules:
            if important_schedule[2]:
                await channel.send(
                    f"{important_schedule[1]} 일정이 있습니다.\n"
                    f"날짜: {important_schedule[0]}"
                )


def is_op_user(user: discord.Member) -> bool:
    if not os.path.exists(op_file_path):
        return False

    with open(op_file_path, "r", encoding="utf-8") as f:
        op_list = [
            line.strip()
            for line in f
            if line.strip()
        ]

    return user.display_name in op_list


bot.run(TOKEN)