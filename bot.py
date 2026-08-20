"""
Skinlab Team Bot
-----------------
一個幫團隊追蹤 Social Media (Reels/Poster) 題材同拍攝進度嘅 Discord Bot。

呢個檔案唔需要你識寫 code,跟住 README.md 嘅步驟做就得。
"""

import os
import json
import discord
from discord import app_commands
from datetime import datetime
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

# ---------- 題材拍攝進度 stage ----------
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
    return {"ideas": []}

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

bot = SkinlabBot()

# ---------- 指令群組: Idea (Social Media 題材拍攝進度) ----------
idea_group = app_commands.Group(name="idea", description="管理 Social Media 題材同拍攝進度")

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

@idea_group.command(name="status", description="更新某個題材嘅拍攝進度 (打幾個字會自動彈出題材揀,唔使打編號)")
@app_commands.describe(題材="打幾個字,自動彈出現存題材畀你揀", 階段="更新做咩階段")
@app_commands.choices(階段=STAGE_CHOICES)
async def idea_status(interaction: discord.Interaction, 題材: str, 階段: app_commands.Choice[str]):
    match = next((idea for idea in data["ideas"] if idea["content"] == 題材), None)
    if match is None:
        await interaction.response.send_message(
            "⚠️ 揾唔到呢個題材,請打幾個字等自動彈出建議,再揀返正確嗰個。"
        )
        return
    match["stage"] = 階段.value
    save_data(data)
    await interaction.response.send_message(f"🎬 已更新:「{match['content']}」→ **{階段.value}**")

@idea_status.autocomplete("題材")
async def idea_status_autocomplete(interaction: discord.Interaction, current: str):
    filtered = [idea for idea in data["ideas"] if current.lower() in idea["content"].lower()]
    return [
        app_commands.Choice(name=f"[{idea['stage']}] {idea['content'][:80]}", value=idea["content"])
        for idea in filtered[:25]
    ]

@idea_group.command(name="delete", description="刪除一個題材 (打幾個字會自動彈出題材揀)")
@app_commands.describe(題材="打幾個字,自動彈出現存題材畀你揀")
async def idea_delete(interaction: discord.Interaction, 題材: str):
    match = next((idea for idea in data["ideas"] if idea["content"] == 題材), None)
    if match is None:
        await interaction.response.send_message(
            "⚠️ 揾唔到呢個題材,請打幾個字等自動彈出建議,再揀返正確嗰個。"
        )
        return
    data["ideas"].remove(match)
    save_data(data)
    await interaction.response.send_message(f"🗑️ 已刪除題材:「{match['content']}」")

@idea_delete.autocomplete("題材")
async def idea_delete_autocomplete(interaction: discord.Interaction, current: str):
    filtered = [idea for idea in data["ideas"] if current.lower() in idea["content"].lower()]
    return [
        app_commands.Choice(name=f"[{idea['stage']}] {idea['content'][:80]}", value=idea["content"])
        for idea in filtered[:25]
    ]

bot.tree.add_command(idea_group)

# ---------- 指令: AI 摘要最近討論,抽取題材 ----------
@bot.tree.command(name="summarize", description="用 AI 摘要呢個 channel 最近嘅討論,自動抽出 social media 題材")
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

    prompt = f"""以下係一個 Discord channel 嘅團隊討論記錄,團隊主要傾緊social media (reels/poster) 嘅題材。請用廣東話/中文幫我:
1. 摘要討論咗啲咩重點
2. 抽取當中提到嘅 social media 題材 idea (如果有)

討論記錄:
{conversation_text}

請用清晰嘅列點格式回覆,分做「摘要」「題材Idea」兩部分。"""

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
