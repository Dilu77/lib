import os
import logging
import asyncio
import tempfile
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from motor import AsyncIOMotorClient
from libgen_api import LibgenSearch

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7756102128:AAFlYIwO70BLE1zT9iFi6Dc4yLpeJYPOemQ")
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://fdtekkz7:XbWjwqaWWOMu9RNI@cluster0.bc5z5.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB in bytes
MAX_RESULTS = 7  # Maximum number of search results to show at once

# Initialize LibGen API
libgen = LibgenSearch()

# MongoDB setup
client = AsyncIOMotorClient(MONGODB_URI)
db = client.book_bot_db
users_collection = db.users
downloads_collection = db.downloads

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    
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
    
    await update.message.reply_text(
        f"Hello {user.first_name}! Welcome to the 📚 Ultimate Book Fetch Bot 📚\n\n"
        "I can help you find and download books from Library Genesis.\n\n"
        "What would you like to do?",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "start":
        keyboard = [
            [InlineKeyboardButton("Search by Title", callback_data="search_title")],
            [InlineKeyboardButton("Search by Author", callback_data="search_author")],
            [InlineKeyboardButton("My Downloads", callback_data="my_downloads")],
            [InlineKeyboardButton("Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📚 *Ultimate Book Fetch Bot* 📚\n\n"
            "What would you like to do?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif query.data == "help":
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
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    elif query.data == "search_title":
        context.user_data["search_mode"] = "title"
        await query.edit_message_text(
            "📚 *Search by Title* 📚\n\n"
            "Please enter the title of the book you're looking for:",
            parse_mode="Markdown"
        )
    
    elif query.data == "search_author":
        context.user_data["search_mode"] = "author"
        await query.edit_message_text(
            "📚 *Search by Author* 📚\n\n"
            "Please enter the author's name:",
            parse_mode="Markdown"
        )
    
    elif query.data == "my_downloads":
        await show_downloads(query, context)
    
    elif query.data.startswith("book_"):
        book_id = query.data.split("_")[1]
        book_index = int(book_id)
        
        # Get book details from user data
        if "search_results" in context.user_data and book_index < len(context.user_data["search_results"]):
            book = context.user_data["search_results"][book_index]
            await show_book_details(query, context, book)
    
    elif query.data.startswith("download_"):
        book_id = query.data.split("_")[1]
        book_index = int(book_id)
        
        # Get book details from user data
        if "search_results" in context.user_data and book_index < len(context.user_data["search_results"]):
            book = context.user_data["search_results"][book_index]
            await download_book(query, context, book)
    
    elif query.data == "back_to_results":
        # Show previous search results
        if "search_results" in context.user_data and context.user_data["search_results"]:
            await show_search_results(query, context, context.user_data["search_results"])
    
    elif query.data.startswith("page_"):
        page = int(query.data.split("_")[1])
        await show_search_results(query, context, context.user_data["search_results"], page)

async def show_downloads(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's download history."""
    user_id = query.from_user.id
    downloads = await downloads_collection.find({"user_id": user_id}).sort("date", -1).limit(10).to_list(length=10)
    
    if not downloads:
        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
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
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="Markdown")

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle general search queries."""
    if not context.args:
        await update.message.reply_text(
            "Please specify what you want to search for. For example:\n"
            "/search The Hobbit"
        )
        return
    
    query = " ".join(context.args)
    
    # Try title search first, then author if no results
    results = libgen.search_title(query)
    search_type = "title"
    
    if not results:
        results = libgen.search_author(query)
        search_type = "author"
    
    if not results:
        await update.message.reply_text(
            f"Sorry, I couldn't find any books matching '{query}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    context.user_data["search_results"] = results
    context.user_data["search_mode"] = search_type
    context.user_data["search_query"] = query
    
    await show_search_results_message(update, context, results)

async def title_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle title search queries."""
    if not context.args:
        await update.message.reply_text("Please specify a title to search for.")
        return
    
    title = " ".join(context.args)
    results = libgen.search_title(title)
    
    if not results:
        await update.message.reply_text(
            f"Sorry, I couldn't find any books with title matching '{title}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    context.user_data["search_results"] = results
    context.user_data["search_mode"] = "title"
    context.user_data["search_query"] = title
    
    await show_search_results_message(update, context, results)

async def author_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle author search queries."""
    if not context.args:
        await update.message.reply_text("Please specify an author to search for.")
        return
    
    author = " ".join(context.args)
    results = libgen.search_author(author)
    
    if not results:
        await update.message.reply_text(
            f"Sorry, I couldn't find any books by author '{author}'.\n\n"
            "Please try a different search term or check your spelling."
        )
        return
    
    context.user_data["search_results"] = results
    context.user_data["search_mode"] = "author"
    context.user_data["search_query"] = author
    
    await show_search_results_message(update, context, results)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages for search queries."""
    if "search_mode" in context.user_data:
        search_mode = context.user_data["search_mode"]
        query = update.message.text.strip()
        
        if len(query) < 3:
            await update.message.reply_text(
                "Your search query is too short. Please use at least 3 characters."
            )
            return
        
        if search_mode == "title":
            results = libgen.search_title(query)
            if not results:
                await update.message.reply_text(
                    f"Sorry, I couldn't find any books with title matching '{query}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        else:  # author mode
            results = libgen.search_author(query)
            if not results:
                await update.message.reply_text(
                    f"Sorry, I couldn't find any books by author '{query}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        
        context.user_data["search_results"] = results
        context.user_data["search_query"] = query
        
        await show_search_results_message(update, context, results)
    else:
        # If no search mode is set, assume the user wants to search by title
        results = libgen.search_title(update.message.text)
        
        if not results:
            results = libgen.search_author(update.message.text)
            if not results:
                await update.message.reply_text(
                    f"Sorry, I couldn't find any books matching '{update.message.text}'.\n\n"
                    "Please try a different search term or check your spelling."
                )
                return
        
        context.user_data["search_results"] = results
        context.user_data["search_query"] = update.message.text
        
        await show_search_results_message(update, context, results)

async def show_search_results_message(update: Update, context: ContextTypes.DEFAULT_TYPE, results: List[Dict[str, Any]]) -> None:
    """Display search results as a message."""
    await show_search_results(update.message, context, results)

async def show_search_results(message_obj, context: ContextTypes.DEFAULT_TYPE, results: List[Dict[str, Any]], page: int = 0) -> None:
    """Display search results with pagination."""
    total_results = len(results)
    total_pages = (total_results + MAX_RESULTS - 1) // MAX_RESULTS
    
    start_idx = page * MAX_RESULTS
    end_idx = min(start_idx + MAX_RESULTS, total_results)
    
    page_results = results[start_idx:end_idx]
    
    query = context.user_data.get("search_query", "your search")
    search_mode = context.user_data.get("search_mode", "title")
    
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
    
    if hasattr(message_obj, "edit_message_text"):
        # It's a callback query
        await message_obj.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # It's a message
        await message_obj.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def show_book_details(query, context: ContextTypes.DEFAULT_TYPE, book: Dict[str, Any]) -> None:
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
    
    book_index = context.user_data["search_results"].index(book)
    
    keyboard = [
        [InlineKeyboardButton("📥 Download Book", callback_data=f"download_{book_index}")],
        [InlineKeyboardButton("🔙 Back to Results", callback_data="back_to_results")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def download_book(query, context: ContextTypes.DEFAULT_TYPE, book: Dict[str, Any]) -> None:
    """Handle book download."""
    await query.edit_message_text(
        "⏳ *Processing your download request...*\n\n"
        "This might take a moment, depending on the book size.",
        parse_mode="Markdown"
    )
    
    try:
        # Resolve download links
        download_links = libgen.resolve_download_links(book)
        
        if not download_links:
            await query.edit_message_text(
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
            await query.edit_message_text(
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
            "user_id": query.from_user.id,
            "title": title,
            "author": author,
            "extension": extension,
            "size": book.get("Size", "Unknown"),
            "date": datetime.now(),
            "download_url": download_url
        })
        
        # Update user download count
        await users_collection.update_one(
            {"user_id": query.from_user.id},
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
            
            await query.edit_message_text(
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
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=file,
                filename=f"{safe_title}.{extension}",
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
        
        await query.edit_message_text(
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
        
        await query.edit_message_text(
            "❌ *Download Failed*\n\n"
            f"Error: {str(e)[:200]}...\n\n"
            "Please try again later or choose another book.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics."""
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("This command is only available to admins.")
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
    
    message = f"📊 *Bot Statistics* 📊\n\n"
    message += f"*Total Users:* {total_users}\n"
    message += f"*Total Downloads:* {total_downloads}\n\n"
    message += "*Top 5 Books:*\n"
    
    for i, book in enumerate(top_books):
        title = book["_id"]["title"]
        author = book["_id"]["author"]
        count = book["count"]
        message += f"{i+1}. *{title}* by {author} - {count} downloads\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    # You can define admin user IDs here or store them in the database/env vars
    admin_ids = os.environ.get("ADMIN_IDS", "").split(",")
    admin_ids = [int(id_str) for id_str in admin_ids if id_str.strip()]
    return user_id in admin_ids

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_handler))
    application.add_handler(CommandHandler("title", title_search_handler))
    application.add_handler(CommandHandler("author", author_search_handler))
    application.add_handler(CommandHandler("downloads", lambda u, c: show_downloads(u.callback_query, c)))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
