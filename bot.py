import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.enums import ChatMemberStatus
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
import yt_dlp
import asyncpg

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Fallback to 0 if not set

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None

# ----------------- Translations -----------------
LANG_TEXT = {
    "uz": {
        "welcome_sub": "👋 Xush kelibsiz!\n\nBotdan foydalanish uchun avval quyidagi kanalga obuna bo'ling:",
        "btn_sub": "📢 Kanalga obuna bo'lish",
        "btn_check": "✅ Obunani tekshirish",
        "sub_success": "✅ Siz endi botdan bemalol foydalanishingiz mumkin!\n\nMenga TikTok yoki Instagram havolasini yuboring.",
        "sub_fail": "❌ Hali obuna bo'lmadingiz. Iltimos, kanalga a'zo bo'ling!",
        "welcome_download": "🎉 Video yuklab oluvchi botga xush kelibsiz!\n\nMenga TikTok yoki Instagram havolasini yuboring.",
        "sub_required": "🔒 Botdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak:",
        "downloading": "⏳ Video yuklanmoqda... Iltimos kuting.",
        "success_vid": "Mana sizning videongiz! 🎥\n\n@TargetSaver_bot",
        "fail_vid": "❌ Kechirasiz, videoni yuklab olib bo'lmadi. Havola to'g'riligini va akkaunt ochiqligini tekshiring."
    },
    "ru": {
        "welcome_sub": "👋 Добро пожаловать!\n\nЧтобы использовать бота, подпишитесь на наш канал:",
        "btn_sub": "📢 Подписаться на канал",
        "btn_check": "✅ Проверить подписку",
        "sub_success": "✅ Теперь вы можете использовать бота!\n\nОтправьте мне ссылку на TikTok или Instagram.",
        "sub_fail": "❌ Вы еще не подписались. Пожалуйста, присоединитесь к каналу!",
        "welcome_download": "🎉 Добро пожаловать в бота-загрузчика!\n\nОтправьте мне ссылку на TikTok или Instagram.",
        "sub_required": "🔒 Для использования бота необходимо подписаться на канал:",
        "downloading": "⏳ Загрузка видео... Пожалуйста, подождите.",
        "success_vid": "Вот ваше видео! 🎥\n\n@TargetSaver_bot",
        "fail_vid": "❌ Извините, не удалось скачать видео. Проверьте ссылку и убедитесь, что аккаунт открыт."
    },
    "en": {
        "welcome_sub": "👋 Welcome!\n\nTo use this bot, please subscribe to our channel first:",
        "btn_sub": "📢 Subscribe to Channel",
        "btn_check": "✅ Check Subscription",
        "sub_success": "✅ You can now use the bot freely!\n\nSend me a TikTok or Instagram link.",
        "sub_fail": "❌ You haven't subscribed yet. Please join the channel!",
        "welcome_download": "🎉 Welcome to the Video Downloader Bot!\n\nSend me a TikTok or Instagram link.",
        "sub_required": "🔒 You must be subscribed to our channel to use this bot:",
        "downloading": "⏳ Downloading video... Please wait.",
        "success_vid": "Here is your video! 🎥\n\n@TargetSaver_bot",
        "fail_vid": "❌ Sorry, couldn't download the video. Make sure the link is correct and the account is public."
    }
}

# ----------------- Database Functions -----------------
async def init_db():
    global db_pool
    if not DATABASE_URL:
        logging.warning("DATABASE_URL is not set. Bot will run without database tracking.")
        return
    
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                language VARCHAR(10) DEFAULT 'uz',
                downloads_count INT DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logging.info("Database connection up and tables verified.")

async def upsert_user(user: types.User, lang: str = None):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        if lang:
            await conn.execute('''
                INSERT INTO users (user_id, username, first_name, language)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE 
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name, language = EXCLUDED.language
            ''', user.id, user.username, user.first_name, lang)
        else:
            await conn.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE 
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            ''', user.id, user.username, user.first_name)

async def get_user_lang(user_id: int) -> str:
    if not db_pool: return "uz"
    async with db_pool.acquire() as conn:
        lang = await conn.fetchval("SELECT language FROM users WHERE user_id = $1", user_id)
        return lang if lang else "uz"

async def increment_downloads(user_id: int):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = $1", user_id)

async def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        return False

# ----------------- Keyboards -----------------
def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")]
    ])

def get_sub_keyboard(lang="uz"):
    text_data = LANG_TEXT.get(lang, LANG_TEXT["uz"])
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text_data["btn_sub"], url=channel_url)],
        [InlineKeyboardButton(text=text_data["btn_check"], callback_data="check_sub")]
    ])

import aiohttp

# ----------------- Downloader Core -----------------
async def download_video(url: str, output_path: str) -> str:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    payload = {
        "url": url,
        "vQuality": "1080"
    }
    
    # Phase 1: Try Cobalt API (Bypasses AWS IP blocks)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.cobalt.tools/api/json", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    video_url = data.get("url")
                    if video_url:
                        async with session.get(video_url) as file_resp:
                            with open(output_path, 'wb') as f:
                                f.write(await file_resp.read())
                        return output_path
    except Exception as e:
        logging.warning(f"Cobalt download failed: {e}. Trying fallback...")

    # Phase 2: Fallback to yt-dlp
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4'
    }
    def _yt_dlp_run():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _yt_dlp_run)
    return output_path

# ----------------- User Handlers -----------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await upsert_user(message.from_user)
    lang = await get_user_lang(message.from_user.id)
    
    # Check if brand new user
    if not db_pool:
        # Fallback if no DB
        await message.answer("Please choose your language:", reply_markup=get_lang_keyboard())
        return
        
    async with db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT downloads_count FROM users WHERE user_id = $1", message.from_user.id)
        
    if val == 0:
        await message.answer("Please choose your language / Пожалуйста, выберите язык / Iltimos tilingizni tanlang:", reply_markup=get_lang_keyboard())
        return

    is_subbed = await check_subscription(message.from_user.id)
    if not is_subbed:
        await message.answer(LANG_TEXT[lang]["welcome_sub"], reply_markup=get_sub_keyboard(lang))
        return
    await message.answer(LANG_TEXT[lang]["welcome_download"])

@dp.callback_query(F.data.startswith("lang_"))
async def lang_callback(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    await upsert_user(callback.from_user, lang=lang)
    
    text_data = LANG_TEXT[lang]
    is_subbed = await check_subscription(callback.from_user.id)
    
    if not is_subbed:
        await callback.message.edit_text(text_data["welcome_sub"], reply_markup=get_sub_keyboard(lang))
    else:
        await callback.message.edit_text(text_data["welcome_download"])

@dp.callback_query(F.data == "check_sub")
async def verify_sub_callback(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    text_data = LANG_TEXT[lang]
    
    is_subbed = await check_subscription(callback.from_user.id)
    if is_subbed:
        await callback.message.edit_text(text_data["sub_success"])
    else:
        await callback.answer(text_data["sub_fail"], show_alert=True)

@dp.message(F.text.regexp(r'(https?://(www\.)?(tiktok\.com|instagram\.com)/[^\s]+)'))
async def process_link(message: types.Message):
    lang = await get_user_lang(message.from_user.id)
    text_data = LANG_TEXT[lang]
    await upsert_user(message.from_user)

    if not await check_subscription(message.from_user.id):
        await message.answer(text_data["sub_required"], reply_markup=get_sub_keyboard(lang))
        return

    url = message.text
    processing_msg = await message.answer(text_data["downloading"])

    try:
        file_name = f"video_{message.from_user.id}_{message.message_id}.mp4"
        output_file = await download_video(url, file_name)

        video = FSInputFile(output_file)
        await bot.send_video(
            chat_id=message.chat.id,
            video=video,
            caption=f"{text_data['success_vid']}",
            reply_to_message_id=message.message_id
        )

        os.remove(output_file)
        await processing_msg.delete()
        await increment_downloads(message.from_user.id)

    except Exception as e:
        logging.error(f"Download failed: {e}")
        await processing_msg.edit_text(text_data["fail_vid"])

# ----------------- Admin Commands -----------------
@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if not db_pool:
        await message.answer("Database is not connected.")
        return

    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_downloads = await conn.fetchval("SELECT SUM(downloads_count) FROM users")
    
    await message.answer(f"📊 **TargetSave Bot Stats:**\n\n👥 Total Users: {total_users}\n🎥 Total Downloads: {total_downloads}")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    if not db_pool:
        await message.answer("Database is not connected.")
        return
        
    if not command.args:
        await message.answer("To use broadast: `/broadcast Hello guys, check out my new video!`", parse_mode="Markdown")
        return

    msg_text = command.args
    status_msg = await message.answer("⏳ Broadcast starting...")
    
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
        
    success = 0
    fail = 0
    for user_row in users:
        try:
            await bot.send_message(user_row['user_id'], msg_text)
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05) # Prevent Telegram Flood Limits

    await status_msg.edit_text(f"✅ **Broadcast Complete!**\n\nDelivered: {success}\nFailed/Blocked: {fail}")

# ----------------- Startup Hooks -----------------
async def on_startup():
    await init_db()

async def on_shutdown():
    if db_pool:
        await db_pool.close()

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
