import asyncio
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

QUOTEX_EMAIL = os.environ.get("QUOTEX_EMAIL", "")
QUOTEX_PASSWORD = os.environ.get("QUOTEX_PASSWORD", "")

bot_running = False
trade_stats = {"wins": 0, "losses": 0, "total": 0}

async def connect_quotex():
    import httpx
    _orig = httpx.AsyncClient.__init__
    def _patch(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        _orig(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = _patch
    sys.path.insert(0, '/app/pyquotex')
    from pyquotex.stable_api import Quotex
    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)
    check, reason = await client.connect()
    if not check:
        raise Exception(f"Connection failed: {reason}")
    await client.change_account("PRACTICE")
    return client

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Quotex Demo Bot\n\n"
        "/run — Trading shuru karo\n"
        "/stop — Trading band karo\n"
        "/balance — Balance dekho\n"
        "/stats — Win/Loss stats\n"
        "/status — Bot status"
    )

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    if bot_running:
        await update.message.reply_text("⚠️ Bot pehle se chal raha hai!")
        return
    bot_running = True
    await update.message.reply_text("✅ Bot start ho raha hai...")
    asyncio.create_task(trading_loop(context.bot))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = False
    await update.message.reply_text("🛑 Bot band ho gaya!")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Balance check kar raha hoon...")
    try:
        client = await connect_quotex()
        bal = await client.get_balance()
        await update.message.reply_text(f"💰 Demo Balance: ${bal:.2f}")
        await client.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = trade_stats
    if t["total"] == 0:
        await update.message.reply_text("📊 Abhi koi trade nahi hua.")
        return
    winrate = (t["wins"] / t["total"]) * 100
    await update.message.reply_text(
        f"📊 Trade Stats:\n"
        f"✅ Wins: {t['wins']}\n"
        f"❌ Losses: {t['losses']}\n"
        f"📈 Win Rate: {winrate:.1f}%\n"
        f"🔢 Total: {t['total']}"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = "🟢 Chal raha hai" if bot_running else "🔴 Band hai"
    await update.message.reply_text(f"Bot Status: {s}")

async def trading_loop(bot):
    global bot_running, trade_stats
    try:
        client = await connect_quotex()
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"❌ Quotex connect nahi hua: {str(e)[:200]}")
        bot_running = False
        return

    await bot.send_message(chat_id=CHAT_ID, text="🤖 Trading shuru! Signals dhundh raha hoon...")

    import pandas as pd

    def calc_rsi(prices, period=14):
        import pandas as pd
        delta = pd.Series(prices).diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = -delta.where(delta < 0, 0).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calc_bb(prices, period=20):
        import pandas as pd
        s = pd.Series(prices)
        mid = s.rolling(period).mean()
        std = s.rolling(period).std()
        return (mid + 2*std).iloc[-1], mid.iloc[-1], (mid - 2*std).iloc[-1]

    ASSETS = ["EURUSD_otc", "GBPUSD_otc", "AUDCAD_otc"]

    while bot_running:
        try:
            for asset in ASSETS:
                if not bot_running:
                    break
                try:
                    candles = await client.get_historical_candles(asset, 60)
                    if len(candles) < 25:
                        continue
                    closes = [c['close'] for c in candles]
                    rsi_val = calc_rsi(closes).iloc[-1]
                    upper, mid, lower = calc_bb(closes)
                    price = closes[-1]

                    direction = None
                    if rsi_val < 35 and price <= lower * 1.001:
                        direction = "call"
                    elif rsi_val > 65 and price >= upper * 0.999:
                        direction = "put"

                    if direction:
                        success, trade_id = await client.buy(1, asset, direction, 60)
                        if success:
                            emoji = "🟢" if direction == "call" else "🔴"
                            await bot.send_message(chat_id=CHAT_ID, text=(
                                f"{emoji} TRADE!\n"
                                f"Asset: {asset}\n"
                                f"Direction: {direction.upper()}\n"
                                f"RSI: {round(rsi_val,1)}\n"
                                f"Time: {datetime.now().strftime('%H:%M:%S')}"
                            ))
                            await asyncio.sleep(65)
                            profit = await client.check_win(trade_id)
                            if profit > 0:
                                trade_stats["wins"] += 1
                                await bot.send_message(chat_id=CHAT_ID, text=f"✅ WIN! +${profit:.2f}")
                            else:
                                trade_stats["losses"] += 1
                                await bot.send_message(chat_id=CHAT_ID, text=f"❌ LOSS! -$1")
                            trade_stats["total"] += 1
                except Exception as ae:
                    logger.error(f"{asset}: {ae}")
                    continue

            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Loop error: {e}")
            await bot.send_message(chat_id=CHAT_ID, text=f"⚠️ Error: {str(e)[:100]}")
            await asyncio.sleep(15)

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
