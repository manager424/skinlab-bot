"""
Skinlab Team Bot
-----------------
一個幫團隊記錄 To-Do 同 Reels/Poster 題材進度、並可以用 Gemini AI 自動摘要討論嘅 Discord Bot。

呢個檔案唔需要你識寫 code,跟住 README.md 嘅步驟做就得。
"""

import os
import json
import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import google.generativeai as genai

# ---------- 基本設定 ----------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    raise RuntimeError("搵唔到 DISCORD_TOKEN,請檢查環境變數設定")
if not GEMINI_API_KEY:
    raise RuntimeError("搵唔到 GEMINI_API_KEY,請檢查環境變數設定")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

HK_TZ = ZoneInfo("Asia/Hong_Kong")

# ---------- 團隊成員 ----------
MEMBER_CHOICES = [
    app_commands.Choice(name="Sandy (Manager)", value="Sandy"),
    app_commands.Choice(name="Agnes (CS)", value="Agnes"),
    app_commands.Choice(name="Camille (Marketing)", value="Camille"),
    app_commands.Choice(name="Vanessa (Marketing)", value="Vanessa"),
]

# ---------- Idea 拍攝進度 stage ----------
STAGE_CHOICES = [
    app_commands.Choice(name="未開始", value="未開始"),
    app_commands.Choice(name="拍攝中", value="拍攝中"),
    app_commands.Choice(name="拍攝完成待剪", value="拍攝完成待剪"),
    app_commands.Choice(name="剪接中", value="剪接中"),
    app_commands.Choice(name="已完成/已出街", value="已完成/已出街"),
]

DATA_FILE = "team_data.json"

# ---------- 資料儲存 (簡單 JSON 檔案,唔需要資料庫) ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"ideas": [], "todos": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ---------- Discord Bot 設定 ----------
intents = discord.Intents.default()
intents.message_content = True  # 需要喺 Discord Developer Portal 開啟呢個權限

class SkinlabBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        if not daily_reset.is_running():
            daily_reset.start()

bot = SkinlabBot()

# ---------- 每日凌晨自動清空 To-Do (香港時間 00:00) ----------
@tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=HK_TZ))
async def daily_reset():
    data["todos"] = []
    save_data(data)
    print(f"[{datetime.now(HK_TZ)}] To-Do list 已自動清空")

# ---------- 指令群組: To-Do (每人獨立清單) ----------
todo_group = app_commands.Group(name="todo", description="管理團隊每日 To-Do list (每日凌晨自動清空)")

@todo_group.command(name="add", description="幫某個成員新增一個 to-do")
@app_commands.describe(負責人="呢件事交畀邊個", 內容="to-do 內容")
@app_commands.choices(負責人=MEMBER_CHOICES)
async def todo_add(interaction: discord.Interaction, 負責人: app_commands.Choice[str], 內容: str):
    entry = {
        "content": 內容,
        "assignee": 負責人.value,
        "added_by": interaction.user.display_name,
        "done": False,
        "time": datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M"),
    }
    data["todos"].append(entry)
    save_data(data)
    await interaction.response.send_message(f"📝 已幫 **{負責人.value}** 新增 To-Do:\n> {內容}")

@todo_group.command(name="list", description="睇某個成員(或全部)嘅 to-do list")
@app_commands.describe(負責人="淨係想睇邊個嘅list?留空 = 睇全部")
@app_commands.choices(負責人=MEMBER_CHOICES)
async def todo_list(interaction: discord.Interaction, 負責人: app_commands.Choice[str] = None):
    todos = data["todos"]
    if 負責人:
        todos = [t for t in todos if t["assignee"] == 負責人.value]

    if not todos:
        await interaction.response.send_message("暫時未有 to-do 項目。(記住:list 每日凌晨會自動清空)")
        return

    if 負責人:
        lines = []
        for i, t in enumerate(todos, start=1):
            status = "✅" if t["done"] else "⬜"
            lines.append(f"{status} {i}. {t['content']}")
        text = f"**{負責人.value} 嘅 To-Do List:**\n" + "\n".join(lines)
    else:
        # 按負責人分組顯示
        grouped = {}
        for t in todos:
            grouped.setdefault(t["assignee"], []).append(t)
        blocks = []
        for person, items in grouped.items():
            lines = []
            for i, t in enumerate(items, start=1):
                status = "✅" if t["done"] else "⬜"
                lines.append(f"{status} {i}. {t['content']}")
            blocks.append(f"**{person}:**\n" + "\n".join(lines))
        text = "**今日全體 To-Do List:**\n\n" + "\n\n".join(blocks)

    for i in range(0, len(text), 1900):
        if i == 0:
            await interaction.response.send_message(text[i:i + 1900])
        else:
            await interaction.followup.send(text[i:i + 1900])

@todo_group.command(name="done", description="將某個成員嘅 to-do 標記完成 (直接打字就會自動彈出清單揀,唔使打編號)")
@app_commands.describe(負責人="邊個嘅 to-do", 內容="打幾個字,Discord會自動彈出佗個人現存嘅to-do畀你揀")
@app_commands.choices(負責人=MEMBER_CHOICES)
async def todo_done(interaction: discord.Interaction, 負責人: app_commands.Choice[str], 內容: str):
    match = next(
        (t for t in data["todos"] if t["assignee"] == 負責人.value and not t["done"] and t["content"] == 內容),
        None,
    )
    if match is None:
        await interaction.response.send_message(
            "⚠️ 揾唔到呢件事,請打幾個字等佗個人嘅to-do自動彈出嚟,再揀返正確嗰個。"
        )
        return
    match["done"] = True
    save_data(data)
    await interaction.response.send_message(f"🎉 {負責人.value} 已完成:{match['content']}")

@todo_done.autocomplete("內容")
async def todo_done_content_autocomplete(interaction: discord.Interaction, current: str):
    assignee = getattr(interaction.namespace, "負責人", None)
    pending = [t for t in data["todos"] if not t["done"]]
    if assignee:
        pending = [t for t in pending if t["assignee"] == assignee]
    filtered = [t for t in pending if current.lower() in t["content"].lower()]
    return [
        app_commands.Choice(name=t["content"][:100], value=t["content"])
        for t in filtered[:25]
    ]

bot.tree.add_command(todo_group)

# ---------- 指令: 手動清空 to-do (唔等凌晨自動reset) ----------
@bot.tree.command(name="cancelall", description="手動清空 to-do list (可指定負責人,或留空清空全部人)")
@app_commands.describe(負責人="淨係清空邊個嘅list?留空 = 清空全部人")
@app_commands.choices(負責人=MEMBER_CHOICES)
async def cancelall_cmd(interaction: discord.Interaction, 負責人: app_commands.Choice[str] = None):
    if 負責人:
        before = len(data["todos"])
        data["todos"] = [t for t in data["todos"] if t["assignee"] != 負責人.value]
        removed = before - len(data["todos"])
        save_data(data)
        await interaction.response.send_message(f"🗑️ 已清空 **{負責人.value}** 嘅 to-do list(共 {removed} 件)。")
    else:
        count = len(data["todos"])
        data["todos"] = []
        save_data(data)
        await interaction.response.send_message(f"🗑️ 已清空全部 to-do list(共 {count} 件)。")

# ---------- 指令: 一次過標記所有 to-do 做完成 ----------
@bot.tree.command(name="tododone-all", description="一次過將 to-do 全部標記做完成 (可指定負責人,或留空 = 全部人)")
@app_commands.describe(負責人="淨係標記邊個嘅list?留空 = 全部人")
@app_commands.choices(負責人=MEMBER_CHOICES)
async def tododone_all_cmd(interaction: discord.Interaction, 負責人: app_commands.Choice[str] = None):
    target = data["todos"]
    if 負責人:
        target = [t for t in target if t["assignee"] == 負責人.value]
    count = 0
    for t in target:
        if not t["done"]:
            t["done"] = True
            count += 1
    save_data(data)
    who = 負責人.value if 負責人 else "全體"
    await interaction.response.send_message(f"🎉 已一次過將 **{who}** 嘅 {count} 件 to-do 標記做完成!")

# ---------- 指令群組: Idea (Reels/Poster 題材拍攝進度) ----------
idea_group = app_commands.Group(name="idea", description="管理 Reels/Poster 題材同拍攝進度")

@idea_group.command(name="add", description="新增一個 reels/poster 題材")
@app_commands.describe(題材="題材/內容簡述")
async def idea_add(interaction: discord.Interaction, 題材: str):
    entry = {
        "content": 題材,
        "author": interaction.user.display_name,
        "stage": "未開始",
        "time": datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M"),
    }
    data["ideas"].append(entry)
    save_data(data)
    await interaction.response.send_message(
        f"✅ 已記低題材:\n> {題材}\n狀態:未開始 (由 {entry['author']} 提出)"
    )

@idea_group.command(name="list", description="列出晒所有題材同目前拍攝進度")
async def idea_list(interaction: discord.Interaction):
    if not data["ideas"]:
        await interaction.response.send_message("暫時未有任何題材記錄。")
        return
    lines = []
    for i, idea in enumerate(data["ideas"], start=1):
        lines.append(f"{i}. [{idea['stage']}] {idea['content']} (提出人: {idea['author']})")
    text = "**題材 / 拍攝進度:**\n" + "\n".join(lines)
    for i in range(0, len(text), 1900):
        if i == 0:
            await interaction.response.send_message(text[i:i + 1900])
        else:
            await interaction.followup.send(text[i:i + 1900])

@idea_group.command(name="status", description="更新某個題材嘅拍攝進度")
@app_commands.describe(編號="喺 /idea list 上面嘅編號", 階段="更新做咩階段")
@app_commands.choices(階段=STAGE_CHOICES)
async def idea_status(interaction: discord.Interaction, 編號: int, 階段: app_commands.Choice[str]):
    idx = 編號 - 1
    if idx < 0 or idx >= len(data["ideas"]):
        await interaction.response.send_message("⚠️ 揾唔到呢個編號,請用 /idea list 檢查。")
        return
    data["ideas"][idx]["stage"] = 階段.value
    save_data(data)
    await interaction.response.send_message(
        f"🎬 已更新:「{data['ideas'][idx]['content']}」→ **{階段.value}**"
    )

bot.tree.add_command(idea_group)

# ---------- 指令: AI 摘要最近討論 ----------
@bot.tree.command(name="summarize", description="用 AI 摘要呢個 channel 最近嘅討論,自動抽出重點")
@app_commands.describe(訊息數量="要睇幾多個最近訊息 (預設50)")
async def summarize_cmd(interaction: discord.Interaction, 訊息數量: int = 50):
    await interaction.response.defer(thinking=True)

    messages = []
    async for msg in interaction.channel.history(limit=訊息數量):
        if not msg.author.bot:
            messages.append(f"{msg.author.display_name}: {msg.content}")
    messages.reverse()
    conversation_text = "\n".join(messages)

    if not conversation_text.strip():
        await interaction.followup.send("呢度未有足夠討論內容可以摘要。")
        return

    prompt = f"""以下係一個 Discord channel 嘅團隊討論記錄。請用廣東話/中文幫我:
1. 摘要討論咗啲咩重點
2. 抽取當中提到嘅內容題材 idea (如果有)
3. 抽取當中提到嘅 To-Do / 待辦事項 (如果有)

討論記錄:
{conversation_text}

請用清晰嘅列點格式回覆,分做「摘要」「題材Idea」「To-Do」三部分。"""

    response = gemini_model.generate_content(prompt)
    result_text = response.text

    for i in range(0, len(result_text), 1900):
        await interaction.followup.send(result_text[i:i + 1900])

# ---------- 啟動 ----------
@bot.event
async def on_ready():
    print(f"✅ Bot 已上線: {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
