
import os
import sqlite3
from datetime import datetime, timezone

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
DB = "trades.db"

PAIR, DIRECTION, ENTRY, EXIT, PNL, NOTES = range(6)

MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add Trade", "📊 Dashboard"],
        ["📚 History", "❌ Cancel"],
    ],
    resize_keyboard=True
)


def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT,
                direction TEXT,
                entry REAL,
                exit REAL,
                pnl REAL,
                notes TEXT,
                date TEXT
            )
        """)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📒 Welcome to Professional Trade Journal!\n\n"
        "Track your trades and analyze your performance.",
        reply_markup=MENU
    )


async def add_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter trading pair (Example: EURUSD):")
    return PAIR


async def get_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pair"] = update.message.text.upper()
    await update.message.reply_text("Direction? Type BUY or SELL:")
    return DIRECTION


async def get_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    direction = update.message.text.upper()
    if direction not in ["BUY", "SELL"]:
        await update.message.reply_text("Please type BUY or SELL.")
        return DIRECTION

    context.user_data["direction"] = direction
    await update.message.reply_text("Enter entry price:")
    return ENTRY


async def get_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["entry"] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ENTRY

    await update.message.reply_text("Enter exit price:")
    return EXIT


async def get_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["exit"] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return EXIT

    await update.message.reply_text(
        "Enter profit or loss amount (Example: 25 or -10):"
    )
    return PNL


async def get_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["pnl"] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return PNL

    await update.message.reply_text("Add trade notes (or type NONE):")
    return NOTES


async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes = update.message.text
    if notes.upper() == "NONE":
        notes = ""

    data = context.user_data

    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT INTO trades
            (pair, direction, entry, exit, pnl, notes, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["pair"],
            data["direction"],
            data["entry"],
            data["exit"],
            data["pnl"],
            notes,
            datetime.now(timezone.utc).isoformat()
        ))

    context.user_data.clear()

    await update.message.reply_text(
        "✅ Trade saved successfully!",
        reply_markup=MENU
    )
    return ConversationHandler.END


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB) as conn:
        rows = conn.execute(
            "SELECT pnl FROM trades"
        ).fetchall()

    total = len(rows)
    wins = sum(1 for row in rows if row[0] > 0)
    losses = sum(1 for row in rows if row[0] < 0)
    net = sum(row[0] for row in rows)
    winrate = (wins / total * 100) if total else 0

    await update.message.reply_text(
        f"📊 TRADING DASHBOARD\n\n"
        f"Total Trades: {total}\n"
        f"Winning Trades: {wins}\n"
        f"Losing Trades: {losses}\n"
        f"Win Rate: {winrate:.2f}%\n"
        f"Net P/L: {net:.2f}",
        reply_markup=MENU
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB) as conn:
        rows = conn.execute("""
            SELECT pair, direction, pnl, date
            FROM trades ORDER BY id DESC LIMIT 10
        """).fetchall()

    if not rows:
        await update.message.reply_text("No trades recorded yet.")
        return

    result = "📚 LAST 10 TRADES\n\n"

    for pair, direction, pnl, date in rows:
        result += (
            f"{pair} | {direction}\n"
            f"P/L: {pnl:.2f}\n"
            f"Date: {date[:10]}\n\n"
        )

    await update.message.reply_text(result, reply_markup=MENU)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Trade entry cancelled.",
        reply_markup=MENU
    )
    return ConversationHandler.END


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing!")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    trade_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^➕ Add Trade$"),
                add_trade
            )
        ],
        states={
            PAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pair)],
            DIRECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_direction)],
            ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_entry)],
            EXIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_exit)],
            PNL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pnl)],
            NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(trade_conversation)
    app.add_handler(MessageHandler(filters.Regex("^📊 Dashboard$"), dashboard))
    app.add_handler(MessageHandler(filters.Regex("^📚 History$"), history))

    print("Trade Journal Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
