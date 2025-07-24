import logging
import time
import threading
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler

user_data = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def validate_float(val):
    try:
        return float(val)
    except ValueError:
        return None

async def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("⏺️ شروع ربات", callback_data='start_bot')],
                [InlineKeyboardButton("⏹️ توقف ربات", callback_data='stop_bot')]]
    await update.message.reply_text("👋 خوش آمدید! لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'start_bot':
        user_data[user_id] = {"state": "waiting_api"}
        await query.edit_message_text("🔑 لطفاً API Key والکس خود را وارد کنید:")
    elif query.data == 'stop_bot':
        user_data[user_id]["running"] = False
        await query.edit_message_text("⏹️ ربات متوقف شد.")

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_data:
        await update.message.reply_text("لطفاً ابتدا /start را بزنید.")
        return

    user_state = user_data[user_id]

    if user_state.get("state") == "waiting_api":
        user_state["api_key"] = text
        user_state["state"] = "waiting_sell_percentage"
        await update.message.reply_text("📉 درصد افت برای خرید بعد از فروش را وارد کنید (مثلاً 2.5):")
    elif user_state.get("state") == "waiting_sell_percentage":
        val = validate_float(text)
        if val is not None:
            user_state["buy_drop_percent"] = val
            user_state["state"] = "waiting_profit_percentage"
            await update.message.reply_text("📈 درصد سود برای فروش بعد از خرید را وارد کنید (مثلاً 3):")
        else:
            await update.message.reply_text("❌ عدد نامعتبر. لطفاً دوباره وارد کنید.")
    elif user_state.get("state") == "waiting_profit_percentage":
        val = validate_float(text)
        if val is not None:
            user_state["sell_profit_percent"] = val
            user_state["state"] = "running"
            user_state["running"] = True
            await update.message.reply_text("✅ ربات فعال شد. بررسی معاملات هر ۵ دقیقه انجام می‌شود.")
            threading.Thread(target=trade_loop, args=(user_id, context)).start()
        else:
            await update.message.reply_text("❌ عدد نامعتبر. لطفاً دوباره وارد کنید.")
    else:
        await update.message.reply_text("⏳ ربات در حال اجراست...")

def trade_loop(user_id, context):
    while user_data.get(user_id, {}).get("running", False):
        try:
            api_key = user_data[user_id]["api_key"]
            headers = {"X-API-KEY": api_key}
            resp = requests.get("https://api.wallex.ir/v1/account/trades", headers=headers)
            data = resp.json()

            if not data.get("result"):
                context.bot.send_message(chat_id=user_id, text="❌ عدم دریافت اطلاعات معاملات.")
                time.sleep(300)
                continue

            last_trade = data["result"][0]
            symbol = last_trade["symbol"]
            side = last_trade["side"]
            price = float(last_trade["price"])
            amount = float(last_trade["amount"])

            if side == "BUY":
                sell_price = price * (1 + user_data[user_id]["sell_profit_percent"] / 100)
                order_payload = {
                    "symbol": symbol,
                    "price": round(sell_price, 4),
                    "side": "SELL",
                    "type": "LIMIT",
                    "amount": amount
                }
                res = requests.post("https://api.wallex.ir/v1/account/orders", headers=headers, json=order_payload)
                if res.status_code == 200:
                    context.bot.send_message(chat_id=user_id, text=f"📤 سفارش فروش ثبت شد:\n{amount} {symbol} با قیمت {sell_price:.2f}")
            elif side == "SELL":
                buy_price = price * (1 - user_data[user_id]["buy_drop_percent"] / 100)
                order_payload = {
                    "symbol": symbol,
                    "price": round(buy_price, 4),
                    "side": "BUY",
                    "type": "LIMIT",
                    "amount": amount
                }
                res = requests.post("https://api.wallex.ir/v1/account/orders", headers=headers, json=order_payload)
                if res.status_code == 200:
                    context.bot.send_message(chat_id=user_id, text=f"📥 سفارش خرید ثبت شد:\n{amount} {symbol} با قیمت {buy_price:.2f}")
        except Exception as e:
            context.bot.send_message(chat_id=user_id, text=f"⚠️ خطا: {e}")
        time.sleep(300)

if __name__ == '__main__':
    import asyncio
    from telegram.ext import Application

    async def run():
        app = ApplicationBuilder().token("7893694483:AAHp_dD0NYJd7S9Kk7yZRdQ-zRIXrh44fUE").build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        await app.run_polling()

    asyncio.run(run())
