import os
import asyncio
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SYNCPAY_CLIENT_ID = os.environ.get("SYNCPAY_CLIENT_ID", "")
SYNCPAY_CLIENT_SECRET = os.environ.get("SYNCPAY_CLIENT_SECRET", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
SYNCPAY_URL = "https://api.syncpay.pro"

PLANS = {
    "mensal": {"label": "📅 PLANO MENSAL — R$ 29,90", "price": 29.90, "days": 30},
    "bimestral": {"label": "🔒 2 MESES — R$ 39,90", "price": 39.90, "days": 60},
    "trimestral": {"label": "❤️ 3 MESES — R$ 49,90", "price": 49.90, "days": 90},
}

pending = {}
bearer_token = {"token": None, "expires_at": None}


async def get_token():
    now = datetime.now()
    if bearer_token["token"] and bearer_token["expires_at"] and now < bearer_token["expires_at"]:
        return bearer_token["token"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SYNCPAY_URL}/api/partner/v1/auth-token",
            headers={"Content-Type": "application/json"},
            json={"client_id": SYNCPAY_CLIENT_ID, "client_secret": SYNCPAY_CLIENT_SECRET},
        )
        data = r.json()
        token = data.get("access_token")
        bearer_token["token"] = token
        bearer_token["expires_at"] = now + timedelta(minutes=55)
        return token


async def criar_cobranca(amount, descricao):
    token = await get_token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SYNCPAY_URL}/api/partner/v1/cash-in",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"amount": amount, "description": descricao},
        )
        return r.json()


async def verificar_pagamento(identifier):
    token = await get_token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{SYNCPAY_URL}/api/partner/v1/cash-in/{identifier}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        return r.json()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(PLANS["mensal"]["label"], callback_data="plan_mensal")],
        [InlineKeyboardButton(PLANS["bimestral"]["label"], callback_data="plan_bimestral")],
        [InlineKeyboardButton(PLANS["trimestral"]["label"], callback_data="plan_trimestral")],
    ]
    await update.message.reply_text("💎 Escolha seu plano:", reply_markup=InlineKeyboardMarkup(keyboard))


async def selecionar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.replace("plan_", "")
    plan = PLANS[plan_key]
    user_id = query.from_user.id
    nome = query.from_user.first_name
    await query.edit_message_text("⏳ Aguarde, estamos processando seu pedido...")
    try:
        charge = await criar_cobranca(plan["price"], f"VIP Picks - {plan_key}")
        pix_code = charge.get("pix_code")
        identifier = charge.get("identifier")
        if not pix_code or not identifier:
            await context.bot.send_message(chat_id=user_id, text=f"❌ Resposta da API: {charge}")
            return
        pending[user_id] = {"identifier": identifier, "days": plan["days"], "nome": nome}
        btn = [[InlineKeyboardButton("✅ Clique para ver o status do pagamento", callback_data="verificar")]]
        await context.bot.send_message(chat_id=user_id, text="Para pagar via Pix Copia e Cola: toque no código abaixo para copiá-lo, abra seu app do banco, escolha 'Pix Copia e Cola' e cole o conteúdo.")
        await context.bot.send_message(chat_id=user_id, text=pix_code)
        await context.bot.send_message(chat_id=user_id, text="✅ Depois de efetuar o pagamento, toque no botão abaixo para verificar o status do seu pedido.", reply_markup=InlineKeyboardMarkup(btn))
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"❌ Erro: {e}. Digite /start para recomeçar.")


async def verificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    pay = pending.get(user_id)
    if not pay:
        await query.edit_message_text("❌ Nenhum pagamento encontrado. Use /start para recomeçar.")
        return
    try:
        data = await verificar_pagamento(pay["identifier"])
        status = str(data.get("status", "")).upper()
        if status in ("PAID", "APPROVED", "COMPLETED", "CONFIRMED", "SUCCESS"):
            expire = datetime.now() + timedelta(days=pay["days"])
            invite = await context.bot.create_chat_invite_link(chat_id=CHANNEL_ID, expire_date=expire, member_limit=1)
            await context.bot.send_message(chat_id=user_id, text=f"Seu pedido foi pago com sucesso! {pay['nome']}")
            await context.bot.send_message(chat_id=user_id, text="Aguarde, estamos preparando seu acesso...")
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=user_id, text="Aqui está o link de acesso para o canal VIP")
            await context.bot.send_message(chat_id=user_id, text=invite.invite_link)
            await context.bot.send_message(chat_id=user_id, text="Seu acesso foi liberado! Aproveite :)")
            del pending[user_id]
        else:
            btn = [[InlineKeyboardButton("✅ Clique para ver o status do pagamento", callback_data="verificar")]]
            await query.edit_message_text(
                f"{pay['nome']}, não identificamos o pagamento. Verifique se o Pix foi realizado e tente novamente.",
                reply_markup=InlineKeyboardMarkup(btn),
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Erro ao verificar: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(selecionar_plano, pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(verificar, pattern="^verificar$"))
    print("Bot rodando!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

