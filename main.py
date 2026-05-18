import asyncio
import logging
import os
import sys
from datetime import datetime

# ============================================================
# PROXY PATCH — Sabse pehle karo
# ============================================================
import httpx

_original_async_init = httpx.AsyncClient.__init__
def _patched_async_init(self, *args, **kwargs):
    kwargs.pop('proxy', None)
    kwargs.pop('proxies', None)
    _original_async_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _patched_async_init

_original_sync_init = httpx.Client.__init__
def _patched_sync_init(self, *args, **kwargs):
    kwargs.pop('proxy', None)
    kwargs.pop('proxies', None)
    _original_sync_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_sync_init
# ============================================================

import pandas as pd
import numpy as np

sys.path.insert(0, '/app/pyquotex')

from pyquotex.stable_api import Quotex
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# CONFIG
# ============================================================
QUOTEX_EMAIL    = os.environ.get("QUOTEX_EMAIL", "kkvv65473@gmail.com")
QUOTEX_PASSWORD = os.environ.get("QUOTEX_PASSWORD", "kkvv@12345")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "8847055481:AAGN50WHuD1VJDE_c9e7PZhh6cTUu8aVQEU")
CHAT_ID         = int(os.environ.get("5535893135", "0"))
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = None
bot_running = False
trade_stats = {"wins": 0, "losses": 0, "total": 0}

ASSETS = ["EURUSD_otc", "GBPUSD_otc", "AUDCAD_otc"]
TIMEFRAME = 60
TRADE_AMOUNT = 1

# ============================================================
# STRATEGY — RSI + Bollinger Bands
# ============================================================
def calculate_rsi(prices, period=14):
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger(prices, period=20):
    s = pd.Series(prices)
    mid = s.rolling(period).mean()
    std = s.rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return upper.iloc[-1], mid.iloc[-1], lower.iloc[-1]

def get_signal(candles):
    if len(candles) < 25:
        return None
    closes = [c['close'] for c in candles]
    rsi = calculate_rsi(closes)
    rsi_val = rsi.iloc[-1]
    upper, mid, lower = calculate_bollinger(closes)
    price = closes[-1]

    if rsi_val < 35 and price <= lower * 1.001:
        return "call", round(rsi_val, 1), round(price, 5)
    if rsi_val > 65 and price >= upper * 0.999:
        return "put", round(rsi_val, 1), round(price, 5)
    return None

# ============================================================
# QUOTEX CONNECTION
# ============================================================
async def get_client():
    global client
    try:
        if client is None:
            client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)
        check, reason = await client.connect()
        if not check:
            client = None
            raise Exception(f"Connection failed: {reason}")
        await client.change_account("PRACTICE")
        return client
    except Exception as e:
        client = None
        raise e

# ============================================================
# BOT LOOP
# ============================================================
async def trading_loop(bot: Bot):
    global bot_running, trade_stats
    await bot.send_message(chat_id=CHAT_ID, text="🤖 Bot shuru ho gaya! Signals dhundh raha hoon...")

    while bot_running:
        try:
            q = await get_client()

            for asset in ASSETS:
                if not bot_running:
                    break
                try:
                    candles = await q.get_historical_candles(asset, TIMEFRAME)
                    result = get_signal(candles)

                    if result:
                        direction, rsi_val, price = result
                        success, trade_id = await q.buy(TRADE_AMOUNT, asset, direction, TIMEFRAME)

                        if success:
                            emoji = "🟢" if direction == "call" else "🔴"
                            msg = (
                                f"{emoji} TRADE PLACED!\n"
                                f"Asset: {asset}\n"
                                f"Direction: {direction.upper()}\n"
                                f"Amount: ${TRADE_AMOUNT}\n"
                                f"RSI: {rsi_val}\n"
                                f"Price: {price}\n"
                                f"Time: {datetime.now().strftime('%H:%M:%S')}"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=msg)

                            await asyncio.sleep(65)
                            profit = await q.check_win(trade_id)

                            if profit > 0:
                                trade_stats["wins"] += 1
                                await bot.send_message(chat_id=CHAT_ID, text=f"✅ WIN! +${profit:.2f}")
                            else:
                                trade_stats["losses"] += 1
                                await bot.send_message(chat_id=CHAT_ID, text=f"❌ LOSS! -${TRADE_AMOUNT}")

                            trade_stats["total"] += 1
                except Exception as asset_err:
                    logger.error(f"Asset {asset} error: {asset_err}")
                    continue

            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Loop error: {e}")
            await bot.send_message(chat_id=CHAT_ID, text=f"⚠️ Error: {str(e)[:100]}\nDobara try kar raha hoon...")
            await asyncio.sleep(15)

# ============================================================
# TELEGRAM COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 Quotex Demo Bot\n\n"
        "Commands:\n"
        "/run — Bot start karo\n"
        "/stop — Bot band karo\n"
        "/balance — Balance dekho\n"
        "/stats — Win/Loss stats\n"
        "/status — Bot ka status"
    )
    await update.message.reply_text(msg)

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    if update.effective_chat.id != CHAT_ID:
        return
    if bot_running:
        await update.message.reply_text("⚠️ Bot pehle se chal raha hai!")
        return
    bot_running = True
    await update.message.reply_text("✅ Bot start ho raha hai...")
    asyncio.create_task(trading_loop(context.bot))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    if update.effective_chat.id != CHAT_ID:
        return
    bot_running = False
    await update.message.reply_text("🛑 Bot band ho gaya!")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        q = await get_client()
        bal = await q.get_balance()
        await update.message.reply_text(f"💰 Demo Balance: ${bal:.2f}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    t = trade_stats
    if t["total"] == 0:
        await update.message.reply_text("📊 Abhi koi trade nahi hua.")
        return
    winrate = (t["wins"] / t["total"]) * 100
    msg = (
        f"📊 Trade Stats:\n"
        f"✅ Wins: {t['wins']}\n"
        f"❌ Losses: {t['losses']}\n"
        f"📈 Win Rate: {winrate:.1f}%\n"
        f"🔢 Total Trades: {t['total']}"
    )
    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    s = "🟢 Chal raha hai" if bot_running else "🔴 Band hai"
    await update.message.reply_text(f"Bot Status: {s}")

# ============================================================
# MAIN
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("status", status))

    logger.info("Bot chal raha hai...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
