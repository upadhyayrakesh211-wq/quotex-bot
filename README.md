# Quotex Demo Trading Bot — Railway Setup

## Environment Variables (Railway pe set karo):
- QUOTEX_EMAIL = aapka Quotex email
- QUOTEX_PASSWORD = aapka Quotex password  
- TELEGRAM_TOKEN = BotFather ka token
- CHAT_ID = aapka Telegram chat ID

## Telegram Commands:
- /start — Bot info
- /run — Trading start karo
- /stop — Trading band karo
- /balance — Demo balance dekho
- /stats — Win/Loss stats
- /status — Bot status

## Strategy:
RSI + Bollinger Bands
- CALL: RSI < 35 + Price near lower band
- PUT: RSI > 65 + Price near upper band
