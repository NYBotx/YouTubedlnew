import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.ext import Application, ContextTypes
from yt_dlp import YoutubeDL
import asyncio
from flask import Flask, request
from hypercorn.asyncio import serve
from hypercorn.config import Config
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Set up logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram bot token (set your bot API key here)
BOT_API_KEY = os.getenv("BOT_API_KEY")

# Initialize Flask app
app = Flask(__name__)

# Initialize the Telegram bot application
bot_app = Application.builder().token(BOT_API_KEY).build()

# Function to start the bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.mention_html()}! I'm a YouTube Downloader bot. Send me a YouTube link!",
        parse_mode="HTML",
    )

# Function to help the user
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text("Just send me a YouTube URL to download the video!")

# Function to handle the YouTube URL
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with URLs"""
    url = update.message.text
    await update.message.reply_text(f"Processing the URL: {url}...")

    # Use yt-dlp to download the video/audio
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': './downloads/%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',  # Change this if needed
        }],
        'quiet': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_url = info_dict.get("url", None)
            filename = f"./downloads/{info_dict['id']}.mp4"

            # Check if the file exists, then send it to the user
            if os.path.exists(filename):
                await update.message.reply_text("Sending your video...")
                await update.message.reply_video(video=open(filename, 'rb'))
                os.remove(filename)
            else:
                await update.message.reply_text("Sorry, there was an issue processing the video.")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Function to handle download and upload inline button press
async def download_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download and upload inline button press"""
    await update.callback_query.answer()

    # Extract the YouTube URL from the callback data (you can add additional data as needed)
    url = update.callback_query.data
    await handle_url(update, context)

# Flask route for handling updates
@app.route('/' + BOT_API_KEY, methods=['POST'])
async def webhook():
    """Handle incoming updates from Telegram"""
    json_str = await request.get_data(as_text=True)
    update = Update.de_json(json_str, bot_app.bot)
    await bot_app.process_update(update)
    return 'OK'

def main():
    """Main function to start the Flask app and the Telegram bot"""
    
    # Add handlers for commands and messages
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    bot_app.add_handler(CallbackQueryHandler(download_and_upload))

    # Configure the ASGI server (Hypercorn)
    config = Config()
    config.bind = ["0.0.0.0:8080"]

    # Run the ASGI server with Hypercorn, wrapped in asyncio
    asyncio.run(serve(app, config))

if __name__ == "__main__":
    main()
                     
