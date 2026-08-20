"""
Skinlab Team Bot
-----------------
一個幫團隊追蹤 Social Media (Reels/Poster) 題材同拍攝進度嘅 Discord Bot。

呢個檔案唔需要你識寫 code,跟住 README.md 嘅步驟做就得。
"""

import os
import re
import json
import uuid
import discord
from discord import app_commands, ui, TextStyle
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
DONE_STAGE = "已完成/已出街"

DATA_FILE = "team_data.json"

# ---------- 資料儲存 (簡單 JSON 檔案,唔需要資料庫) ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("ideas", [])
            d.setdefault("archive", [])
            return d
    return {"ideas": [], "archive": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ---------- 解析「一次過貼多個題材」嘅文字 ----------
URL_PATTERN = re.compile(r"^https?://\S+")
NUMBERING_PATTERN = re.compile(r"^\d+[\.\)]\s*")

def parse_bulk_ideas(text: str):
    """
    支援格式:
      分類標題 (無編號、無連結嘅一行,例如 'Branding Content')
      https://link...
      1. 題材描述...

      https://link2...
      2. 另一個題材...
    """
    current_category = "未分類"
    pending_link = None
    entries = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if URL_PATTERN.match(line):
            pending_link = line
            continue
        if NUMBERING_PATTERN.match(line):
            desc = NUMBERING_PATTERN.sub("", line).strip()
            if not desc:
                continue
            content = desc
            if pending_link:
                content += f"\n🔗 {pending_link}"
                pending_link = None
            entries.append({"content": content, "category": current_category})
        else:
            # 冇編號、冇連結嘅一行 = 當佢係分類標題
            current_category = line
            pending_link = None

    return entries

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

@idea_group.command(name="add", description="快速新增一個題材")
@app_commands.describe(題材="題材/內容簡述", 分類="例如 Branding Content / Educational Content / Poster (可留空)")
async def idea_add(interaction: discord.Interaction, 題材: str, 分類: str = "未分類"):
    entry = {
        "id": uuid.uuid4().hex[:8],
        "content": 題材,
        "category": 分類,
        "author": interaction.user.display_name,
        "stage": "未開始",
        "time": datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M"),
    }
    data["ideas"].append(entry)
    save_data(data)
    await interaction.response.send_message(
        f"✅ 已記低題材 [{分類}]:\n> {題材}\n狀態:未開始 (由 {entry['author']} 提出)"
    )

# ---------- Modal: 一次過貼多個題材 ----------
class BulkIdeaModal(ui.Modal, title="批量新增 Social Media 題材"):
    content_input = ui.TextInput(
        label="貼入題材清單 (支援分類標題+連結+編號)",
        style=TextStyle.paragraph,
        placeholder=(
            "Branding Content\n"
            "https://instagram.com/reel/xxx\n"
            "1. 題材描述...\n\n"
            "https://instagram.com/reel/yyy\n"
            "2. 另一個題材...\n\n"
            "Educational Content\n"
            "https://instagram.com/reel/zzz\n"
            "3. 題材描述..."
        ),
        max_length=4000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        entries = parse_bulk_ideas(self.content_input.value)
        if not entries:
            await interaction.response.send_message(
                "⚠️ 冇解析到任何題材,請確保每個題材前面有編號 (例如 `1. `、`2. `)。"
            )
            return
        for e in entries:
            data["ideas"].append({
                "id": uuid.uuid4().hex[:8],
                "content": e["content"],
                "category": e["category"],
                "author": interaction.user.display_name,
                "stage": "未開始",
                "time": datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M"),
            })
        save_data(data)
        await interaction.response.send_message(f"✅ 已一次過加咗 **{len(entries)}** 個題材!用 `/idea list` 睇晒佢哋。")

@idea_group.command(name="addmany", description="一次過貼入好多個題材 (支援連結、分類、編號自動識別)")
async def idea_addmany(interaction: discord.Interaction):
    await interaction.response.send_modal(BulkIdeaModal())

@idea_group.command(name="list", description="列出晒所有未完成嘅題材同目前拍攝進度")
async def idea_list(interaction: discord.Interaction):
    if not data["ideas"]:
        await interaction.response.send_message("暫時未有任何進行緊嘅題材。(已完成嘅題材可以用 /idea archive 睇返)")
        return

    grouped = {}
    for idea in data["ideas"]:
        grouped.setdefault(idea.get("category", "未分類"), []).append(idea)

    blocks = []
    for category, ideas in grouped.items():
        lines = []
        for i, idea in enumerate(ideas, start=1):
            lines.append(f"{i}. [{idea['stage']}] {idea['content']}")
        blocks.append(f"**📂 {category}**\n" + "\n".join(lines))

    text = "**題材 / 拍攝進度:**\n\n" + "\n\n".join(blocks)
    for i in range(0, len(text), 1900):
        if i == 0:
            await interaction.response.send_message(text[i:i + 1900])
        else:
            await interaction.followup.send(text[i:i + 1900])

@idea_group.command(name="status", description="更新某個題材嘅拍攝進度 (打幾個字自動彈出題材揀,唔使打編號)")
@app_commands.describe(題材="打幾個字,自動彈出現存題材畀你揀", 階段="更新做咩階段")
@app_commands.choices(階段=STAGE_CHOICES)
async def idea_status(interaction: discord.Interaction, 題材: str, 階段: app_commands.Choice[str]):
    match = next((idea for idea in data["ideas"] if idea["id"] == 題材), None)
    if match is None:
        await interaction.response.send_message(
            "⚠️ 揾唔到呢個題材,請打幾個字等自動彈出建議,再揀返正確嗰個。"
        )
        return

    match["stage"] = 階段.value

    if 階段.value == DONE_STAGE:
        # 完成 -> 自動由活躍list搬去archive
        data["ideas"].remove(match)
        match["completed_time"] = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M")
        data["archive"].append(match)
        save_data(data)
        await interaction.response.send_message(
            f"🎉 「{match['content'].splitlines()[0]}」已完成/已出街!已自動由list移除,存入 /idea archive。"
        )
    else:
        save_data(data)
        await interaction.response.send_message(
            f"🎬 已更新:「{match['content'].splitlines()[0]}」→ **{階段.value}**"
        )

@idea_status.autocomplete("題材")
async def idea_status_autocomplete(interaction: discord.Interaction, current: str):
    filtered = [idea for idea in data["ideas"] if current.lower() in idea["content"].lower()]
    return [
        app_commands.Choice(
            name=f"[{idea['stage']}] {idea['content'].splitlines()[0][:80]}",
            value=idea["id"],
        )
        for idea in filtered[:25]
    ]

@idea_group.command(name="delete", description="刪除一個題材 (打幾個字自動彈出題材揀)")
@app_commands.describe(題材="打幾個字,自動彈出現存題材畀你揀")
async def idea_delete(interaction: discord.Interaction, 題材: str):
    match = next((idea for idea in data["ideas"] if idea["id"] == 題材), None)
    if match is None:
        await interaction.response.send_message(
            "⚠️ 揾唔到呢個題材,請打幾個字等自動彈出建議,再揀返正確嗰個。"
        )
        return
    data["ideas"].remove(match)
    save_data(data)
    await interaction.response.send_message(f"🗑️ 已刪除題材:「{match['content'].splitlines()[0]}」")

@idea_delete.autocomplete("題材")
async def idea_delete_autocomplete(interaction: discord.Interaction, current: str):
    filtered = [idea for idea in data["ideas"] if current.lower() in idea["content"].lower()]
    return [
        app_commands.Choice(
            name=f"[{idea['stage']}] {idea['content'].splitlines()[0][:80]}",
            value=idea["id"],
        )
        for idea in filtered[:25]
    ]

@idea_group.command(name="archive", description="睇返已完成/已出街嘅題材歷史記錄")
async def idea_archive(interaction: discord.Interaction):
    if not data["archive"]:
        await interaction.response.send_message("暫時未有已完成嘅題材。")
        return
    lines = []
    for i, idea in enumerate(data["archive"], start=1):
        lines.append(f"{i}. {idea['content'].splitlines()[0]} (完成於 {idea.get('completed_time', '?')})")
    text = "**✅ 已完成題材歷史:**\n" + "\n".join(lines)
    for i in range(0, len(text), 1900):
        if i == 0:
            await interaction.response.send_message(text[i:i + 1900])
        else:
            await interaction.followup.send(text[i:i + 1900])

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
