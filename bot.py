import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    CallbackContext,
    Filters,
)
from yt_dlp import YoutubeDL
from flask import Flask, request
from telegram.ext import Dispatcher

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
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎉 Welcome to the **YouTube Downloader Bot**!\n\n"
        "📽 Send me a YouTube link to download videos or audio in your preferred quality.\n"
        "Use /help for instructions."
    )


# Command: Help
def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📋 **How to use the bot:**\n\n"
        "1️⃣ Send a YouTube link.\n"
        "2️⃣ Choose the desired quality or audio-only option.\n"
        "3️⃣ The bot will process and upload the video/audio to Telegram.\n\n"
        "💡 *Note: Large videos are split into parts to comply with Telegram's file size limits.*"
    )


# Handle YouTube URL
def handle_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    update.message.reply_text("🔄 Fetching available formats...")
    formats = fetch_formats(url)
    if not formats:
        update.message.reply_text("❌ Could not fetch formats. Please check the URL.")
        return

    buttons = [
        [InlineKeyboardButton(f"{f['resolution']} - {f['ext']}", callback_data=f"{url}|{f['format_id']}")]
        for f in formats
    ]
    buttons.append([InlineKeyboardButton("🔊 Audio Only", callback_data=f"{url}|bestaudio")])
    update.message.reply_text(
        "🎥 Choose your desired format:", reply_markup=InlineKeyboardMarkup(buttons)
    )


# Download and upload
def download_and_upload(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    url, format_id = query.data.split("|")
    query.edit_message_text("⏳ Downloading your video... Please wait.")

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
            query.edit_message_text("📦 File too large! Splitting into smaller parts...")
            split_and_upload(output_file, query)
        else:
            # Upload directly
            with open(output_file, "rb") as file:
                query.message.reply_video(file, caption="🎬 Here is your video!")
        os.remove(output_file)
    except Exception as e:
        logger.error(f"Error: {e}")
        query.edit_message_text("❌ Failed to download or upload the video.")


# Split and upload large files
def split_and_upload(file_path, query):
    part_number = 1
    with open(file_path, "rb") as f:
        while chunk := f.read(TELEGRAM_FILE_LIMIT):
            part_filename = f"{file_path}.part{part_number}"
            with open(part_filename, "wb") as part_file:
                part_file.write(chunk)

            with open(part_filename, "rb") as part_file:
                query.message.reply_document(
                    part_file, caption=f"📦 Part {part_number} of the video."
                )
            os.remove(part_filename)
            part_number += 1


# Set up Webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"


def main():
    global bot, dispatcher
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)
    dispatcher = Dispatcher(bot, None, use_context=True)

    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_url))
    dispatcher.add_handler(CallbackQueryHandler(download_and_upload))

    # Set Webhook
    bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")

    # Run Flask app
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
