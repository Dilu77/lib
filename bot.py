import os
import logging
import asyncio
import tempfile
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from libgen_api import LibgenSearch

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
API_ID = int(os.environ.get("API_ID", 18329555))
API_HASH = os.environ.get("API_HASH", "7bf83fddf8244fddfb270701e31470a8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7829564109:AAFJlA6CckL3gaHamJDsTI7ulAyHn39idAg")
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://fdtekkz7:XbWjwqaWWOMu9RNI@cluster0.bc5z5.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB in bytes
MAX_RESULTS = 7  # Maximum number of search results to show at once
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://senior-netty-devadamax-cad459fb.koyeb.app")

# Initialize LibGen API
libgen = LibgenSearch()

# MongoDB setup
client = AsyncIOMotorClient(MONGODB_URI)
db = client.book_bot_db
users_collection = db.users
downloads_collection = db.downloads

# Initialize Pyrogram client
app = Client(
    "book_fetch_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Dict to store user data (equivalent to context.user_data in python-telegram-bot)
user_data = {}

# Helper function to get user data
def get_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {}
    return user_data[user_id]

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Send a welcome message when the command /start is issued."""
    user = message.from_user
    
    # Store user in database
    await users_collection.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "last_active": datetime.now()
            },
            "$setOnInsert": {
                "joined_date": datetime.now(),
                "downloads": 0
            }
        },
        upsert=True
    )
    
    keyboard = [
        [InlineKeyboardButton("Search by Title", callback_data="search_title")],
        [InlineKeyboardButton("Search by Author", callback_data="search_author")],
        [InlineKeyboardButton("My Downloads", callback_data="my_downloads")],
        [InlineKeyboardButton("Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        f"Hello {user.first_name}! Welcome to the 📚 Ultimate Book Fetch Bot 📚\n\n"
        "I can help you find and download books from Library Genesis.\n\n"
        "What would you like to do?",
        reply_markup=reply_markup
    )

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    """Send a help message when the command /help is issued."""
    help_text = (
        "📚 *Book Fetch Bot Help* 📚\n\n"
        "*Commands:*\n"
        "/start - Start the bot and show main menu\n"
        "/search - Search for books (followed by title or author)\n"
        "/author - Search books by author\n"
        "/title - Search books by title\n"
        "/downloads - View your download history\n"
        "/help - Show this help message\n\n"
        
        "*How to search:*\n"
        "You can use the buttons or commands to search. For example:\n"
        "• /title The Hobbit\n"
        "• /author J.R.R. Tolkien\n\n"
        
        "*Download limits:*\n"
        "Books under 50MB will be sent directly to you. For larger books, you'll receive a download link.\n\n"
        
        "Happy reading! 📖"
    )
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(help_text, reply_markup=reply_markup, parse_mode="Markdown")

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle button clicks."""
    user_id = callback_query.from_user.id
    data = callback_query.data
    user_data_dict = get_user_data(user_id)
    
    # Answer the callback query to remove the loading state
    await callback_query.answer()
    
    if data == "start":
        keyboard = [
            [InlineKeyboardButton("Search by Title", callback_data="search_title")],
            [InlineKeyboardButton("Search by Author", callback_data="search_author")],
            [InlineKeyboardButton("My Downloads", callback_data="my_downloads")],
            [InlineKeyboardButton("Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_text(
            "📚 *Ultimate Book Fetch Bot* 📚\n\n"
            "What would you like to do?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif data == "help":
        help_text = (
            "📚 *Book Fetch Bot Help* 📚\n\n"
            "*Commands:*\n"
            "/start - Start the bot and show main menu\n"
            "/search - Search for books (followed by title or author)\n"
            "/author - Search books by author\n"
            "/title - Search books by title\n"
            "/downloads - View your download history\n"
            "/help - Show this help message\n\n"
            
            "*How to search:*\n"
            "You can use the buttons or commands to search. For example:\n"
            "• /title The Hobbit\n"
            "• /author J.R.R. Tolkien\n\n"
            
            "*Download limits:*\n"
            "Books under 50MB will be sent directly to you. For larger books, you'll receive a download link.\n\n"
            
            "Happy reading! 📖"
        )
        
        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_text(
            help_text, 
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif data == "search_title":
        user_data_dict["search_mode"] = "title"
        await callback_query.message.edit_text(
            "📚 *Search by Title* 📚\n\n"
            "Please enter the title of the book you're looking for:",
            parse_mode="Markdown"
        )
    
    elif data == "search_author":
        user_data_dict["search_mode"] = "author"
        await callback_query.message.edit_text(
            "📚 *Search by Author* 📚\n\n"
            "Please enter the author's name:",
            parse_mode="Markdown"
        )
    
    elif data == "my_downloads":
        await show_downloads(client, callback_query)
    
    elif data.startswith("book_"):
        book_id = data.split("_")[1]
        book_index = int(book_id)
        
        # Get book details from user data
        if "search_results" in user_data_dict and book_index < len(user_data_dict["search_results"]):
            book = user_data_dict["search_results"][book_index]
            await show_book_details(client, callback_query, book)
    
    elif data.startswith("download_"):
        book_id = data.split("_")[1]
        book_index = int(book_id)
        
        # Get book details from user data
        if "search_results" in user_data_dict and book_index < len(user_data_dict["search_results"]):
            book = user_data_dict["search_results"][book_index]
            await download_book(client, callback_query, book)
    
    elif data == "back_to_results":
        # Show previous search results
        if "search_results" in user_data_dict and user_data_dict["search_results"]:
            await show_search_results(client, callback_query.message, user_id, user_data_dict["search_results"])
    
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        await show_search_results(client, callback_query.message, user_id, user_data_dict["search_results"], page)

async def show_downloads(client, callback_query: CallbackQuery):
    """Show user's download history."""
    user_id = callback_query.from_user.id
    downloads = await downloads_collection.find({"user_id": user_id}).sort("date", -1).limit(10).to_list(length=10)
    
    if not downloads:
        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_text(
            "📚 *My Downloads* 📚\n\n"
            "You haven't downloaded any books yet.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    message = "📚 *Your Recent Downloads* 📚\n\n"
    for i, download in enumerate(downloads):
        date_str = download["date"].strftime("%Y-%m-%d %H:%M")
        message += f"{i+1}. *{download['title']}* by {download['author']}\n"
        message += f"   Format: {download['extension']} | Downloaded: {date_str}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await callback_query.message.edit_text(
        message, 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

@app.on_message(filters.command("search"))
async def search_command(client, message: Message):
    """Handle general search queries."""
    query = message.text.split(' ', 1)
    if len(query) < 2:
        await message.reply_text(
            "Please specify what you want to search for. For example:\n"
            "/search The Hobbit"
        )
        return
    
    query = query[1].strip()
    
    # Try title search first, then author if no results
    results = libgen.search_title(query)
    search_type = "title"
    
    if not results:
        results = libgen.search_author(query)
        search_type = "author"
    
    if not results:
        await message.reply_text(
            f"Sorry, I couldn't find any books matching '{query}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    user_id = message.from_user.id
    user_data_dict = get_user_data(user_id)
    user_data_dict["search_results"] = results
    user_data_dict["search_mode"] = search_type
    user_data_dict["search_query"] = query
    
    await show_search_results(client, message, user_id, results)

@app.on_message(filters.command("title"))
async def title_search_command(client, message: Message):
    """Handle title search queries."""
    query = message.text.split(' ', 1)
    if len(query) < 2:
        await message.reply_text("Please specify a title to search for.")
        return
    
    title = query[1].strip()
    results = libgen.search_title(title)
    
    if not results:
        await message.reply_text(
            f"Sorry, I couldn't find any books with title matching '{title}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    user_id = message.from_user.id
    user_data_dict = get_user_data(user_id)
    user_data_dict["search_results"] = results
    user_data_dict["search_mode"] = "title"
    user_data_dict["search_query"] = title
    
    await show_search_results(client, message, user_id, results)

@app.on_message(filters.command("author"))
async def author_search_command(client, message: Message):
    """Handle author search queries."""
    query = message.text.split(' ', 1)
    if len(query) < 2:
        await message.reply_text("Please specify an author to search for.")
        return
    
    author = query[1].strip()
    results = libgen.search_author(author)
    
    if not results:
        await message.reply_text(
            f"Sorry, I couldn't find any books by author '{author}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    user_id = message.from_user.id
    user_data_dict = get_user_data(user_id)
    user_data_dict["search_results"] = results
    user_data_dict["search_mode"] = "author"
    user_data_dict["search_query"] = author
    
    await show_search_results(client, message, user_id, results)

@app.on_message(filters.command("downloads"))
async def downloads_command(client, message: Message):
    """Handle downloads command."""
    user_id = message.from_user.id
    downloads = await downloads_collection.find({"user_id": user_id}).sort("date", -1).limit(10).to_list(length=10)
    
    if not downloads:
        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            "📚 *My Downloads* 📚\n\n"
            "You haven't downloaded any books yet.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    message_text = "📚 *Your Recent Downloads* 📚\n\n"
    for i, download in enumerate(downloads):
        date_str = download["date"].strftime("%Y-%m-%d %H:%M")
        message_text += f"{i+1}. *{download['title']}* by {download['author']}\n"
        message_text += f"   Format: {download['extension']} | Downloaded: {date_str}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        message_text, 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

@app.on_message((filters.private | filters.group) & filters.text)
async def text_handler(client, message: Message):
    """Handle text messages for search queries."""
    user_id = message.from_user.id
    user_data_dict = get_user_data(user_id)
    
    if "search_mode" in user_data_dict:
        search_mode = user_data_dict["search_mode"]
        query = message.text.strip()
        
        if len(query) < 3:
            await message.reply_text(
                "Your search query is too short. Please use at least 3 characters."
            )
            return
        
        if search_mode == "title":
            results = libgen.search_title(query)
            if not results:
                await message.reply_text(
                    f"Sorry, I couldn't find any books with title matching '{query}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        else:  # author mode
            results = libgen.search_author(query)
            if not results:
                await message.reply_text(
                    f"Sorry, I couldn't find any books by author '{query}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        
        user_data_dict["search_results"] = results
        user_data_dict["search_query"] = query
        
        await show_search_results(client, message, user_id, results)
    else:
        # If no search mode is set, assume the user wants to search by title
        results = libgen.search_title(message.text)
        
        if not results:
            results = libgen.search_author(message.text)
            if not results:
                await message.reply_text(
                    f"Sorry, I couldn't find any books matching '{message.text}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        
        user_data_dict["search_results"] = results
        user_data_dict["search_query"] = message.text
        
        await show_search_results(client, message, user_id, results)

async def show_search_results(client, message_obj, user_id: int, results: List[Dict[str, Any]], page: int = 0):
    """Display search results with pagination."""
    user_data_dict = get_user_data(user_id)
    total_results = len(results)
    total_pages = (total_results + MAX_RESULTS - 1) // MAX_RESULTS
    
    start_idx = page * MAX_RESULTS
    end_idx = min(start_idx + MAX_RESULTS, total_results)
    
    page_results = results[start_idx:end_idx]
    
    query = user_data_dict.get("search_query", "your search")
    search_mode = user_data_dict.get("search_mode", "title")
    
    if search_mode == "title":
        header = f"📚 *Found {total_results} books matching title:* '{query}' 📚"
    else:
        header = f"📚 *Found {total_results} books by author:* '{query}' 📚"
    
    message = f"{header}\n\n"
    
    for i, book in enumerate(page_results):
        global_idx = start_idx + i
        title = book.get("Title", "Unknown Title")
        author = book.get("Author", "Unknown Author")
        year = book.get("Year", "N/A")
        extension = book.get("Extension", "N/A")
        size = book.get("Size", "N/A")
        
        message += f"{global_idx + 1}. *{title}*\n"
        message += f"   Author: {author}\n"
        message += f"   Year: {year} | Format: {extension} | Size: {size}\n\n"
    
    # Pagination and back buttons
    keyboard = []
    
    # Book selection buttons
    for i, book in enumerate(page_results):
        global_idx = start_idx + i
        keyboard.append([
            InlineKeyboardButton(
                f"{global_idx + 1}. {book.get('Title', 'Unknown')[:25]}...",
                callback_data=f"book_{global_idx}"
            )
        ])
    
    # Pagination buttons
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton("◀️ Previous", callback_data=f"page_{page-1}")
        )
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton("Next ▶️", callback_data=f"page_{page+1}")
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Back to main menu button
    keyboard.append([InlineKeyboardButton("Back to Main Menu", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(message_obj, "edit_text"):
        # It's a message that can be edited (callback query message)
        await message_obj.edit_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # It's a new message
        await message_obj.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def show_book_details(client, callback_query: CallbackQuery, book: Dict[str, Any]):
    """Show detailed information about a book."""
    title = book.get("Title", "Unknown Title")
    author = book.get("Author", "Unknown Author")
    year = book.get("Year", "N/A")
    publisher = book.get("Publisher", "N/A")
    pages = book.get("Pages", "N/A")
    language = book.get("Language", "N/A")
    size = book.get("Size", "N/A")
    extension = book.get("Extension", "N/A")
    
    message = f"📖 *Book Details* 📖\n\n"
    message += f"*Title:* {title}\n"
    message += f"*Author:* {author}\n"
    message += f"*Year:* {year}\n"
    message += f"*Publisher:* {publisher}\n"
    message += f"*Pages:* {pages}\n"
    message += f"*Language:* {language}\n"
    message += f"*Size:* {size}\n"
    message += f"*Format:* {extension.upper()}\n\n"
    
    user_id = callback_query.from_user.id
    user_data_dict = get_user_data(user_id)
    book_index = user_data_dict["search_results"].index(book)
    
    keyboard = [
        [InlineKeyboardButton("📥 Download Book", callback_data=f"download_{book_index}")],
        [InlineKeyboardButton("🔙 Back to Results", callback_data="back_to_results")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await callback_query.message.edit_text(
        message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def download_book(client, callback_query: CallbackQuery, book: Dict[str, Any]):
    """Handle book download."""
    await callback_query.message.edit_text(
        "⏳ *Processing your download request...*\n\n"
        "This might take a moment, depending on the book size.",
        parse_mode="Markdown"
    )
    
    try:
        # Resolve download links
        download_links = libgen.resolve_download_links(book)
        
        if not download_links:
            await callback_query.message.edit_text(
                "❌ *Download Failed*\n\n"
                "Sorry, I couldn't find valid download links for this book.",
                parse_mode="Markdown"
            )
            return
        
        # Choose the first available download link
        download_url = None
        for link_type in ["GET", "Cloudflare", "IPFS.io", "Infura"]:
            if link_type in download_links and download_links[link_type]:
                download_url = download_links[link_type]
                break
        
        if not download_url:
            await callback_query.message.edit_text(
                "❌ *Download Failed*\n\n"
                "Sorry, I couldn't find valid download links for this book.",
                parse_mode="Markdown"
            )
            return
        
        # Get book size in bytes
        response = requests.head(download_url, allow_redirects=True)
        content_length = int(response.headers.get("Content-Length", 0))
        
        title = book.get("Title", "Unknown Title")
        author = book.get("Author", "Unknown Author")
        extension = book.get("Extension", "Unknown").lower()
        
        # Record the download in the database
        await downloads_collection.insert_one({
            "user_id": callback_query.from_user.id,
            "title": title,
            "author": author,
            "extension": extension,
            "size": book.get("Size", "Unknown"),
            "date": datetime.now(),
            "download_url": download_url
        })
        
        # Update user download count
        await users_collection.update_one(
            {"user_id": callback_query.from_user.id},
            {"$inc": {"downloads": 1}}
        )
        
        # If file is too large, just provide the link
        if content_length > MAX_DOWNLOAD_SIZE:
            keyboard = [
                [InlineKeyboardButton("🔗 Download Link", url=download_url)],
                [InlineKeyboardButton("🔙 Back to Results", callback_data="back_to_results")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await callback_query.message.edit_text(
                f"📚 *Book Too Large for Direct Download* 📚\n\n"
                f"*Title:* {title}\n"
                f"*Author:* {author}\n"
                f"*Size:* {book.get('Size', 'Unknown')}\n\n"
                f"This book is larger than 50MB, so I can't send it directly through Telegram.\n"
                f"Please use the download link below:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return
        
        # Download the file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
            temp_filename = temp_file.name
            
            response = requests.get(download_url, stream=True)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
        
        # Send the file
        safe_title = "".join(c for c in title if c.isalnum() or c.isspace()).strip()
        safe_title = safe_title[:50]  # Limit filename length
        
        caption = f"📖 *{title}*\nby {author}"
        
        with open(temp_filename, "rb") as file:
            await client.send_document(
                chat_id=callback_query.message.chat.id,
                document=temp_filename,
                file_name=f"{safe_title}.{extension}",
                caption=caption,
                parse_mode="Markdown"
            )
        
        # Clean up the temp file
        os.unlink(temp_filename)
        
        # Send a success message
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Results", callback_data="back_to_results")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_text(
            "✅ *Download Complete!*\n\n"
            "Your book has been sent. Enjoy reading!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Results", callback_data="back_to_results")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_text(
            "❌ *Download Failed*\n\n"
            f"Error: {str(e)[:200]}...\n\n"
            "Please try again later or choose another book.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

@app.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    """Show bot statistics."""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not await is_admin(user_id):
        await message.reply_text("This command is only available to admins.")
        return
    
    total_users = await users_collection.count_documents({})
    total_downloads = await downloads_collection.count_documents({})
    
    # Get top 5 most downloaded books
    pipeline = [
        {"$group": {"_id": {"title": "$title", "author": "$author"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_books = await downloads_collection.aggregate(pipeline).to_list(length=5)
    
    message_text = f"📊 *Bot Statistics* 📊\n\n"
    message_text += f"*Total Users:* {total_users}\n"
    message_text += f"*Total Downloads:* {total_downloads}\n\n"
    message_text += "*Top 5 Books:*\n"
    
    for i, book in enumerate(top_books):
        title = book["_id"]["title"]
        author = book["_id"]["author"]
        count = book["count"]
        message_text += f"{i+1}. *{title}* by {author} - {count} downloads\n"
    
    await message.reply_text(message_text, parse_mode="Markdown")

async def is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    # You can define admin user IDs here or store them in the database/env vars
    admin_ids = os.environ.get("ADMIN_IDS", "1195233863").split(",")
    admin_ids = [int(id_str) for id_str in admin_ids if id_str.strip()]
    return user_id in admin_ids

# At the top of your file, add:
#WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://senior-netty-devadamax-cad459fb.koyeb.app")  # Your Koyeb app URL
#WEBHOOK_PORT = int(os.environ.get("PORT", 8000))

async def main():
    # Start the bot in polling mode
    await app.start()
    print("Bot started successfully in polling mode!")
    
    # Set up a minimal web server for health checks
    async def health_check(request):
        return web.Response(text="Bot is running", status=200)

    web_app = web.Application()
    web_app.router.add_get('/health', health_check)
    web_app.router.add_get('/', health_check)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8000)))
    await site.start()
    
    print(f"Health check server started at port {os.environ.get('PORT', 8000)}")
    
    # Keep the bot running
    await idle()
    
    # Clean shutdown
    await app.stop()
    await runner.cleanup()
