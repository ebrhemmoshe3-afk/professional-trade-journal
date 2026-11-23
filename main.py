import os
import asyncio
import sqlite3
from datetime import datetime, date, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
DB = "trades.db"

MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add Trade", "📊 Dashboard"],
        ["📈 Reports", "📚 History"],
        ["❌ Cancel"],
    ],
    resize_keyboard=True
)

# Each item: (database column, prompt, input type)
STEPS = [
    ("date", "📅 Trade Date  (YYYY-MM-DD ወይም TODAY)", "date"),
    ("pair", "💱 Trading Pair? (ለምሳሌ EURUSD)", "required"),
    ("direction", "↕️ Direction? (BUY ወይም SELL)", "direction"),
    ("entry", "🎯 Entry Price?", "number"),
    ("exit", "🏁 Exit Price?", "number"),
    ("pnl", "💰 Profit/Loss? (ለምሳሌ 50 ወይም -20)", "number"),
    ("news", "📰 News / News Event? (ወይም SKIP)", "optional"),
    ("context", "🧭 Market Context? (ወይም SKIP)", "optional"),
    ("pd_array", "🧩 PD Array? (FVG, Order Block, Internal Liquidity...)", "optional"),
    ("entry_timeframe", "⏱️ Entry Time Frame? (M1, M5, M15...)", "optional"),
    ("kill_zone", "🕒 Entry Kill Zone? (London / New York / Asia)", "optional"),
    ("entry_model", "📐 Entry Model? (ወይም SKIP)", "optional"),
    ("sl_pips", "🛑 Stop Loss (Pips)? (ወይም SKIP)", "optional_number"),
    ("risk_amount", "⚖️ Risk per Trade? (ወይም SKIP)", "optional_number"),
    ("duration", "⌛ Trade Duration? (ወይም SKIP)", "optional"),
    ("rr", "📏 Risk/Reward? (ለምሳሌ 1:3 ወይም SKIP)", "optional"),
    ("result", "📌 Result? (WIN / LOSS / BREAKEVEN / SKIP)", "result"),
    ("follow_rules", "✅ Did you follow your rules? (YES / NO / PARTIAL / SKIP)", "optional"),
    ("emotion", "🧠 Emotion during trade? (Calm, Fear, Greed... / SKIP)", "optional"),
    ("context_photo", "📸 Send CONTEXT screenshot, or type SKIP.", "photo"),
    ("pd_photo", "📸 Send PD ARRAY screenshot, or type SKIP.", "photo"),
    ("before_photo", "📸 Send BEFORE ENTRY screenshot, or type SKIP.", "photo"),
    ("after_photo", "📸 Send AFTER RESULT screenshot, or type SKIP.", "photo"),
]

def connect():
    return sqlite3.connect(DB)

def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT, direction TEXT, entry REAL, exit REAL,
                pnl REAL, notes TEXT, date TEXT
            )
        """)
        existing = {row[1] for row in con.execute("PRAGMA table_info(trades)")}
        additions = {
            "news": "TEXT", "context": "TEXT", "pd_array": "TEXT",
            "entry_timeframe": "TEXT", "kill_zone": "TEXT",
            "entry_model": "TEXT", "sl_pips": "REAL",
            "risk_amount": "REAL", "duration": "TEXT", "rr": "TEXT",
            "result": "TEXT", "follow_rules": "TEXT", "emotion": "TEXT",
            "context_photo": "TEXT", "pd_photo": "TEXT",
            "before_photo": "TEXT", "after_photo": "TEXT"
        }
        for col, typ in additions.items():
            if col not in existing:
                con.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome to your Professional ICT/SMC Trade Journal!\n\n"
        "➕ Add Trade — record a trade and upload 4 screenshots.\n"
        "📊 Dashboard — performance overview.\n"
        "📈 Reports — daily, weekly, monthly performance.\n"
        "📚 History — recent trades.",
        reply_markup=MENU
    )

async def ask_step(update, context):
    i = context.user_data.get("trade_step", 0)
    if i >= len(STEPS):
        return await save_trade(update, context)
    await update.message.reply_text(STEPS[i][1] + "\n\n(ለመዝለል SKIP ጻፍ።)", reply_markup=MENU)

async def add_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["trade_data"] = {}
    context.user_data["trade_step"] = 0
    await update.message.reply_text(
        "📝 Let's record a new ICT/SMC trade.\n"
        "በተከታታይ ጥያቄዎቹን መልስ።\n\n"
        + STEPS[0][1],
        reply_markup=MENU
    )

async def handle_trade_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "trade_data" not in context.user_data:
        return
    i = context.user_data.get("trade_step", 0)
    if i >= len(STEPS):
        return
    col, prompt, kind = STEPS[i]
    msg = update.message

    if kind == "photo":
        if msg.photo:
            value = msg.photo[-1].file_id
        elif msg.text and msg.text.strip().upper() == "SKIP":
            value = None
        else:
            await msg.reply_text("እባክህ Screenshot ላክ ወይም SKIP ጻፍ።")
            return
    else:
        if not msg.text:
            await msg.reply_text("እባክህ ጽሑፍ አስገባ።")
            return
        raw = msg.text.strip()
        upper = raw.upper()
        if kind == "date":
            if upper == "TODAY":
                value = date.today().isoformat()
            else:
                try:
                    value = datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    await msg.reply_text("ቀኑን YYYY-MM-DD ቅርጽ አስገባ፣ ለምሳሌ 2026-11-23፣ ወይም TODAY ጻፍ።")
                    return
        elif kind == "required":
            if not raw:
                await msg.reply_text("ይህ መረጃ ያስፈልጋል።")
                return
            value = raw.upper()
        elif kind == "direction":
            if upper not in ("BUY", "SELL"):
                await msg.reply_text("BUY ወይም SELL ብለህ አስገባ።")
                return
            value = upper
        elif kind in ("number", "optional_number"):
            if kind == "optional_number" and upper == "SKIP":
                value = None
            else:
                try:
                    value = float(raw.replace(",", ""))
                except ValueError:
                    await msg.reply_text("እባክህ ቁጥር አስገባ።")
                    return
                if kind == "number" and col in ("entry", "exit") and value <= 0:
                    await msg.reply_text("Entry/Exit ከ0 በላይ መሆን አለበት።")
                    return
        elif kind == "result":
            if upper == "SKIP":
                value = None
            elif upper in ("WIN", "LOSS", "BREAKEVEN"):
                value = upper
            else:
                await msg.reply_text("WIN, LOSS, BREAKEVEN ወይም SKIP ጻፍ።")
                return
        else:
            value = None if upper == "SKIP" else raw

    context.user_data["trade_data"][col] = value
    context.user_data["trade_step"] = i + 1
    if context.user_data["trade_step"] < len(STEPS):
        await ask_step(update, context)
    else:
        await save_trade(update, context)

async def save_trade(update, context):
    d = context.user_data.get("trade_data", {})
    # Infer result from P/L when the user skipped the result field.
    if not d.get("result"):
        p = float(d.get("pnl", 0))
        d["result"] = "WIN" if p > 0 else ("LOSS" if p < 0 else "BREAKEVEN")
    cols = [c for c, _, _ in STEPS]
    values = [d.get(c) for c in cols]
    with connect() as con:
        marks = ",".join("?" for _ in cols)
        con.execute(
            f"INSERT INTO trades ({','.join(cols)}) VALUES ({marks})",
            values
        )
        trade_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    context.user_data.clear()
    await update.message.reply_text(
        f"✅ Trade #{trade_id} saved successfully!\n"
        "Your 4 screenshot fields have been saved when uploaded.",
        reply_markup=MENU
    )

def stats_for_period(start_date, end_date=None):
    with connect() as con:
        if end_date:
            row = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl),0), "
                "SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) "
                "FROM trades WHERE substr(date,1,10)>=? AND substr(date,1,10)<?",
                (start_date, end_date)
            ).fetchone()
        else:
            row = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl),0), "
                "SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) "
                "FROM trades WHERE substr(date,1,10)=?",
                (start_date,)
            ).fetchone()
    return row

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    next_week = (today + timedelta(days=7-today.weekday())).isoformat()
    month_start = today.replace(day=1).isoformat()
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()
    d = stats_for_period(today.isoformat())
    w = stats_for_period(week_start, next_week)
    m = stats_for_period(month_start, next_month)
    with connect() as con:
        total, wins, losses, net = con.execute(
            "SELECT COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END), COALESCE(SUM(pnl),0) FROM trades"
        ).fetchone()
        best = con.execute(
            "SELECT pair, SUM(pnl) AS s FROM trades GROUP BY pair ORDER BY s DESC LIMIT 1"
        ).fetchone()
        recent = con.execute("SELECT pnl FROM trades ORDER BY id DESC").fetchall()
    streak = 0
    for (pnl,) in recent:
        if pnl is not None and pnl < 0:
            streak += 1
        else:
            break
    winrate = (wins or 0) / total * 100 if total else 0
    text = (
        "📊 PROFESSIONAL TRADE DASHBOARD\n\n"
        f"Trades: {total}\nWins: {wins or 0} | Losses: {losses or 0}\n"
        f"Win Rate: {winrate:.1f}%\nTotal P/L: {net:.2f}\n"
        f"Best Pair: {best[0]} ({best[1]:.2f})\n"
        f"Current Losing Streak: {streak}\n\n"
        f"Today P/L: {d[1]:.2f} ({d[0]} trades)\n"
        f"This Week P/L: {w[1]:.2f} ({w[0]} trades)\n"
        f"This Month P/L: {m[1]:.2f} ({m[0]} trades)"
    )
    await update.message.reply_text(text, reply_markup=MENU)

async def reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    ws = today - timedelta(days=today.weekday())
    we = ws + timedelta(days=7)
    ms = today.replace(day=1)
    nm = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    d = stats_for_period(today.isoformat())
    w = stats_for_period(ws.isoformat(), we.isoformat())
    m = stats_for_period(ms.isoformat(), nm.isoformat())
    await update.message.reply_text(
        "📈 PERFORMANCE REPORTS\n\n"
        f"DAILY ({today}):\nTrades: {d[0]} | P/L: {d[1]:.2f}\n\n"
        f"WEEKLY ({ws} to {we-timedelta(days=1)}):\nTrades: {w[0]} | P/L: {w[1]:.2f}\n\n"
        f"MONTHLY ({today.strftime('%B %Y')}):\nTrades: {m[0]} | P/L: {m[1]:.2f}",
        reply_markup=MENU
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with connect() as con:
        rows = con.execute(
            "SELECT id, pair, direction, pnl, substr(date,1,10), result "
            "FROM trades ORDER BY id DESC LIMIT 10"
        ).fetchall()
    if not rows:
        await update.message.reply_text("No trades saved yet.", reply_markup=MENU)
        return
    lines = ["📚 LAST 10 TRADES"]
    for tid, pair, direction, pnl, dt, result in rows:
        lines.append(f"#{tid} | {dt} | {pair} {direction} | P/L {pnl or 0:.2f} | {result or '—'}")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Main menu:", reply_markup=MENU)

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "trade_data" in context.user_data:
        await handle_trade_input(update, context)
    elif text == "➕ Add Trade":
        await add_trade(update, context)
    elif text == "📊 Dashboard":
        await dashboard(update, context)
    elif text == "📈 Reports":
        await reports(update, context)
    elif text == "📚 History":
        await history(update, context)
    elif text == "❌ Cancel":
        await cancel(update, context)
    else:
        await update.message.reply_text("Please choose an option from the menu.", reply_markup=MENU)

async def photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "trade_data" in context.user_data:
        await handle_trade_input(update, context)
    else:
        await update.message.reply_text("To add a screenshot, first choose ➕ Add Trade.", reply_markup=MENU)

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Enter your bot token securely first.")
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.PHOTO, photo_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    print("Professional ICT/SMC Trade Journal Bot is running...")
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling()

if __name__ == "__main__":
    main()
