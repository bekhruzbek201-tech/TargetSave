import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
import yt_dlp

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Simple in-memory storage for user languages (MVP version)
user_langs = {}

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
        "success_vid": "Mana sizning videongiz! 🎥",
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
        "success_vid": "Вот ваше видео! 🎥",
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
        "success_vid": "Here is your video! 🎥",
        "fail_vid": "❌ Sorry, couldn't download the video. Make sure the link is correct and the account is public."
    }
}

def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
        ]
    ])

def get_sub_keyboard(lang="uz"):
    text_data = LANG_TEXT.get(lang, LANG_TEXT["uz"])
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text_data["btn_sub"], url=channel_url)],
        [InlineKeyboardButton(text=text_data["btn_check"], callback_data="check_sub")]
    ])
    return keyboard

async def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def download_video(url: str, output_path: str = "temp_video.mp4") -> str:
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_langs:
        await message.answer("Please choose your language / Пожалуйста, выберите язык / Iltimos tilingizni tanlang:", reply_markup=get_lang_keyboard())
        return

    lang = user_langs[user_id]
    text_data = LANG_TEXT[lang]
    is_subbed = await check_subscription(user_id)
    if not is_subbed:
        await message.answer(text_data["welcome_sub"], reply_markup=get_sub_keyboard(lang))
        return
    await message.answer(text_data["welcome_download"])

@dp.callback_query(F.data.startswith("lang_"))
async def lang_callback(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    user_langs[user_id] = lang
    
    text_data = LANG_TEXT[lang]
    is_subbed = await check_subscription(user_id)
    
    if not is_subbed:
        await callback.message.edit_text(text_data["welcome_sub"], reply_markup=get_sub_keyboard(lang))
    else:
        await callback.message.edit_text(text_data["welcome_download"])

@dp.callback_query(F.data == "check_sub")
async def verify_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = user_langs.get(user_id, "uz")
    text_data = LANG_TEXT[lang]
    
    is_subbed = await check_subscription(user_id)
    if is_subbed:
        await callback.message.edit_text(text_data["sub_success"])
    else:
        await callback.answer(text_data["sub_fail"], show_alert=True)

@dp.message(F.text.regexp(r'(https?://(www\.)?(tiktok\.com|instagram\.com)/[^\s]+)'))
async def process_link(message: types.Message):
    user_id = message.from_user.id
    lang = user_langs.get(user_id, "uz")
    text_data = LANG_TEXT[lang]

    is_subbed = await check_subscription(user_id)
    if not is_subbed:
        await message.answer(text_data["sub_required"], reply_markup=get_sub_keyboard(lang))
        return

    url = message.text
    processing_msg = await message.answer(text_data["downloading"])

    try:
        loop = asyncio.get_running_loop()
        output_file = await loop.run_in_executor(None, download_video, url)

        video = FSInputFile(output_file)
        await bot.send_video(
            chat_id=message.chat.id,
            video=video,
            caption=f"{text_data['success_vid']}",
            reply_to_message_id=message.message_id
        )

        os.remove(output_file)
        await processing_msg.delete()

    except Exception as e:
        logging.error(f"Download failed: {e}")
        await processing_msg.edit_text(text_data["fail_vid"])

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
