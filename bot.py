import os
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from yt_dlp import YoutubeDL
from flask import Flask, request, jsonify

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram file size limit in bytes (2GB)
TELEGRAM_FILE_LIMIT = 2 * 1024 * 1024 * 1024

# Flask app setup
app = Flask(__name__)

# Initialize global variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # Automatically provided by Render
PORT = int(os.environ.get("PORT", 8080))

# Application initialization
bot_app = Application.builder().token(BOT_TOKEN).build()


# Fetch video formats
def fetch_formats(url):
    try:
        with YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            return [
                {
                    "format_id": f["format_id"],
                    "resolution": f"{f.get('height', 'Audio')}p" if f.get("height") else "Audio",
                    "ext": f["ext"],
                }
                for f in formats
                if f.get("filesize", 0) <= TELEGRAM_FILE_LIMIT
            ]
    except Exception as e:
        logger.error(f"Error fetching formats: {e}")
        return None


# Command: Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉 Welcome to the **YouTube Downloader Bot**!\n\n"
        "📽 Send me a YouTube link to download videos or audio in your preferred quality.\n"
        "Use /help for instructions."
    )


# Command: Help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **How to use the bot:**\n\n"
        "1️⃣ Send a YouTube link.\n"
        "2️⃣ Choose the desired quality or audio-only option.\n"
        "3️⃣ The bot will process and upload the video/audio to Telegram.\n\n"
        "💡 *Note: Large videos are split into parts to comply with Telegram's file size limits.*"
    )


# Handle YouTube URL
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text("🔄 Fetching available formats...")
    formats = fetch_formats(url)
    if not formats:
        await update.message.reply_text("❌ Could not fetch formats. Please check the URL.")
        return

    buttons = [
        [InlineKeyboardButton(f"{f['resolution']} - {f['ext']}", callback_data=f"{url}|{f['format_id']}")]
        for f in formats
    ]
    buttons.append([InlineKeyboardButton("🔊 Audio Only", callback_data=f"{url}|bestaudio")])
    await update.message.reply_text(
        "🎥 Choose your desired format:", reply_markup=InlineKeyboardMarkup(buttons)
    )


# Download and upload
async def download_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url, format_id = query.data.split("|")
    await query.edit_message_text("⏳ Downloading your video... Please wait.")

    output_file = f"{url.split('=')[-1]}_{format_id}.mp4"
    ydl_opts = {
        "format": format_id,
        "outtmpl": output_file,
        "quiet": True,
    }

    try:
        # Download video
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Check file size
        file_size = os.path.getsize(output_file)
        if file_size > TELEGRAM_FILE_LIMIT:
            await query.edit_message_text("📦 File too large! Splitting into smaller parts...")
            await split_and_upload(output_file, query)
        else:
            # Upload directly
            with open(output_file, "rb") as file:
                await query.message.reply_video(file, caption="🎬 Here is your video!")
        os.remove(output_file)
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text("❌ Failed to download or upload the video.")


# Split and upload large files
async def split_and_upload(file_path, query):
    part_number = 1
    with open(file_path, "rb") as f:
        while chunk := f.read(TELEGRAM_FILE_LIMIT):
            part_filename = f"{file_path}.part{part_number}"
            with open(part_filename, "wb") as part_file:
                part_file.write(chunk)

            with open(part_filename, "rb") as part_file:
                await query.message.reply_document(
                    part_file, caption=f"📦 Part {part_number} of the video."
                )
            os.remove(part_filename)
            part_number += 1


# Flask webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    await bot_app.process_update(update)
    return jsonify({"status": "ok"})


# Main function
async def main():
    # Add handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    bot_app.add_handler(CallbackQueryHandler(download_and_upload))

    # Set webhook
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")

    # Run Flask app
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    asyncio.run(main())
