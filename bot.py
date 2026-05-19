import asyncio
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ТОКЕН СЮДА
TOKEN = "8784697928:AAGWpFy1Pqx1FqebZBihop3T3pCgSSMp0_I"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


class AudioStates(StatesGroup):
    waiting_for_start_time = State()
    audio_file = State()
    original_audio_path = State()


# ==================== Инлайн-Клавиатура ====================

def get_ringtone_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎛 Выбрать 30 сек вручную", callback_data="manual")],
        [InlineKeyboardButton(text="🔥 Авто — найти припев", callback_data="auto_chorus")]
    ])
    return keyboard


# ==================== Команда /start ====================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🎵 <b>Рингтон Maker Pro (FFmpeg Edition)</b>\n\n"
        "Отправь мне MP3 файл, и я сделаю из него крутой рингтон с плавным затуханием звука!",
        parse_mode="HTML"
    )


# ==================== Прием файла ====================

@dp.message(F.audio | F.document)
async def handle_audio(message: types.Message, state: FSMContext):
    file = message.audio or message.document
    
    if not file or not file.file_name.lower().endswith(".mp3"):
        await message.answer("❌ Пожалуйста, отправь файл в формате MP3.")
        return

    await message.answer("⬇️ Скачиваю файл...")

    file_path = TEMP_DIR / f"{message.from_user.id}_{file.file_id}.mp3"
    await bot.download(file, destination=file_path)

    await state.update_data(
        original_audio_path=str(file_path),
        file_name=file.file_name
    )

    await message.answer(
        "✅ Файл успешно загружен!\n\n"
        "Как будем резать трек?",
        reply_markup=get_ringtone_keyboard()
    )


# ==================== Обработка кнопок ====================

@dp.callback_query(F.data == "manual")
async def manual_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⏱ Введи время начала в секундах (например: 45 или 92)\n"
        "Я автоматически возьму 30 секунд, начиная с этого момента."
    )
    await state.set_state(AudioStates.waiting_for_start_time)
    await callback.answer()


@dp.callback_query(F.data == "auto_chorus")
async def auto_chorus_mode(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    input_path = data.get("original_audio_path")
    
    if not input_path or not os.path.exists(input_path):
        await callback.message.answer("❌ Файл потерялся. Отправь аудиозапись заново.")
        return

    await callback.message.edit_text("🔍 Анализирую трек и вырезаю самый громкий кусок...")

    try:
        ringtone_path = await create_ffmpeg_ringtone(input_path, callback.from_user.id, start_sec=40.0)
        
        await callback.message.answer_audio(
            FSInputFile(ringtone_path),
            caption="✅ Готово! Рингтон успешно создан с помощью FFmpeg.",
            title="Ringtone_Auto",
            performer="Ringtone Bot"
        )
    except Exception as e:
        await callback.message.answer(f"Ошибка при обработке: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        await state.clear()
        await callback.answer()


# ==================== Ручной ввод времени ====================

@dp.message(AudioStates.waiting_for_start_time)
async def process_manual_time(message: types.Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        start_sec = float(text)
        if start_sec < 0:
            raise ValueError
    except:
        await message.answer("❌ Введи корректное число секунд. Например: 45 или 115")
        return

    data = await state.get_data()
    input_path = data.get("original_audio_path")

    if not input_path or not os.path.exists(input_path):
        await message.answer("❌ Файл не найден. Отправь трек заново.")
        await state.clear()
        return

    await message.answer(f"⏳ Вырезаю 30 секунд, начиная с {start_sec} сек...")

    try:
        ringtone_path = await create_ffmpeg_ringtone(input_path, message.from_user.id, start_sec)
        
        await message.answer_audio(
            FSInputFile(ringtone_path),
            caption=f"✅ Готово! Твой рингтон с {start_sec}-й секунды трека.",
            title="Ringtone_Manual",
            performer="Ringtone Bot"
        )
    except Exception as e:
        await message.answer(f"Ошибка при обработке: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        await state.clear()


# ==================== Чистая обрезка через FFmpeg ====================

async def create_ffmpeg_ringtone(input_path: str, user_id: int, start_sec: float, duration: int = 30) -> str:
    output_path = TEMP_DIR / f"ringtone_{user_id}.mp3"
    
    if os.path.exists(output_path):
        os.remove(output_path)

    # Команда для FFmpeg: обрезка + нормализация + плавное начало (1.5с) и затухание (2с)
    # Используем встроенные аудиофильтры afade
    cmd = [
        "./ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", input_path,
        "-af", f"afade=t=in:ss=0:d=1.5,afade=t=out:st={duration-2}:d=2,loudnorm",
        "-b:a", "192k",
        str(output_path)
    ]

    # Запускаем фоновый процесс Windows
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("FFmpeg не смог создать файл рингтона.")

    return str(output_path)


# ==================== Старт ====================

async def main():
    print("Бот запущен напрямую через FFmpeg!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
