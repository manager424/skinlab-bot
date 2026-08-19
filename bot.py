"""
Skinlab Team Bot
-----------------
一個幫團隊記錄 Idea 同 To-Do、並可以用 Claude AI 自動摘要討論嘅 Discord Bot。
 
呢個檔案唔需要你識寫 code,跟住 README.md 嘅步驟做就得。
"""
 
import os
import json
import discord
from discord import app_commands
from datetime import datetime
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
 
bot = SkinlabBot()
 
# ---------- 指令: 記錄 Idea ----------
@bot.tree.command(name="idea", description="記低一個團隊 idea")
@app_commands.describe(內容="你想記低嘅 idea 內容")
async def idea_cmd(interaction: discord.Interaction, 內容: str):
    entry = {
        "content": 內容,
        "author": interaction.user.display_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["ideas"].append(entry)
    save_data(data)
    await interaction.response.send_message(
        f"✅ 已記低 Idea:\n> {內容}\n(由 {entry['author']} 提出)"
    )
 
# ---------- 指令: 列出所有 Idea ----------
@bot.tree.command(name="ideas", description="列出晒之前記低嘅所有 idea")
async def ideas_list(interaction: discord.Interaction):
    if not data["ideas"]:
        await interaction.response.send_message("暫時未有任何 idea 記錄。")
        return
    lines = []
    for i, idea in enumerate(data["ideas"], start=1):
        lines.append(f"{i}. {idea['content']} (由 {idea['author']}, {idea['time']})")
    text = "**目前記錄嘅 Idea:**\n" + "\n".join(lines)
    # 分割長訊息 (Discord 單一訊息上限約2000字)
    for i in range(0, len(text), 1900):
        if i == 0:
            await interaction.response.send_message(text[i : i + 1900])
        else:
            await interaction.followup.send(text[i : i + 1900])
 
# ---------- 指令群組: To-Do ----------
todo_group = app_commands.Group(name="todo", description="管理 To-Do list")
 
@todo_group.command(name="add", description="新增一個 to-do")
@app_commands.describe(內容="to-do 內容")
async def todo_add(interaction: discord.Interaction, 內容: str):
    entry = {
        "content": 內容,
        "author": interaction.user.display_name,
        "done": False,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["todos"].append(entry)
    save_data(data)
    await interaction.response.send_message(f"📝 已新增 To-Do:\n> {內容}")
 
@todo_group.command(name="list", description="睇晒現有嘅 to-do list")
async def todo_list(interaction: discord.Interaction):
    if not data["todos"]:
        await interaction.response.send_message("暫時未有 to-do 項目。")
        return
    lines = []
    for i, t in enumerate(data["todos"], start=1):
        status = "✅" if t["done"] else "⬜"
        lines.append(f"{status} {i}. {t['content']} (由 {t['author']})")
    await interaction.response.send_message("**目前 To-Do List:**\n" + "\n".join(lines))
 
@todo_group.command(name="done", description="將某個 to-do 標記做完成")
@app_commands.describe(編號="to-do list 上面嘅編號")
async def todo_done(interaction: discord.Interaction, 編號: int):
    idx = 編號 - 1
    if idx < 0 or idx >= len(data["todos"]):
        await interaction.response.send_message("⚠️ 揾唔到呢個編號,請用 /todo list 檢查。")
        return
    data["todos"][idx]["done"] = True
    save_data(data)
    await interaction.response.send_message(f"🎉 已完成:{data['todos'][idx]['content']}")
 
bot.tree.add_command(todo_group)
 
# ---------- 指令: AI 摘要最近討論 ----------
@bot.tree.command(name="summarize", description="用 AI 摘要呢個 channel 最近嘅討論,自動抽出 idea 同 to-do")
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
2. 抽取當中提到嘅 Idea (如果有)
3. 抽取當中提到嘅 To-Do / 待辦事項 (如果有)
 
討論記錄:
{conversation_text}
 
請用清晰嘅列點格式回覆,分做「摘要」「Idea」「To-Do」三部分。"""
 
    response = gemini_model.generate_content(prompt)
    result_text = response.text
 
    # 分割長訊息 (Discord 單一訊息上限約2000字)
    for i in range(0, len(result_text), 1900):
        await interaction.followup.send(result_text[i : i + 1900])
 
# ---------- 啟動 ----------
@bot.event
async def on_ready():
    print(f"✅ Bot 已上線: {bot.user}")
 
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
 
