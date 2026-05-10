import os
import base64
import asyncio
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "SEU_TOKEN_DO_BOTFATHER")
SYNCPAY_KEY  = os.environ.get("SYNCPAY_KEY", "SUA_API_KEY_SYNCPAY")
CHANNEL_ID   = int(os.environ.get("CHANNEL_ID", "-1001234567890"))
SYNCPAY_URL  = "https://api.syncpayments.com.br"


PLANS = {
    "mensal": {"label": "📅 PLANO MENSAL — R$ 29,90", "price": 29.90, "days": 30},
    "bimestral": {"label": "🔒 2 MESES — R$ 39,90", "price": 39.90, "days": 60},
    "trimestral": {"label": "❤️ 3 MESES — R$ 49,90", "price": 49.90, "days": 90},
}

pending = {}

def _headers():
    encoded = base64.b64encode(SYNCPAY_KEY.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}

async def criar_cobranca(amount, descricao, ref):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{SYNCPAY_URL}/charge/", headers=_headers(), json={"amount": amount, "description": descricao, "externalreference": ref})
        return r.json()

async def verificar_pagamento(transaction_id):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{SYNCPAY_URL}/charge/{transaction_id}/", headers=_headers())
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
    ref = f"{user_id}_{plan_key}_{int(datetime.now().timestamp())}"
    await query.edit_message_text("⏳ Aguarde, estamos processando seu pedido...")
    try:
        charge = await criar_cobranca(plan["price"], f"VIP Picks - {plan_key}", ref)
        pix_code = charge.get("paymentCode")
        tx_id = charge.get("idTransaction")
        if not pix_code or not tx_id:
            await context.bot.send_message(chat_id=user_id, text="❌ Erro ao gerar cobrança. Digite /start e tente novamente.")
            return
        pending[user_id] = {"tx_id": tx_id, "days": plan["days"], "nome": nome}
        btn = [[InlineKeyboardButton("✅ Clique para ver o status do pagamento", callback_data="verificar")]]
        await context.bot.send_message(chat_id=user_id, text="Para pagar via Pix Copia e Cola: toque no código abaixo para copiá-lo, abra seu app do banco, escolha 'Pix Copia e Cola' e cole o conteúdo.")
        await context.bot.send_message(chat_id=user_id, text=f"`{pix_code}`", parse_mode="Markdown")
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
    try​​​​​​​​​​​​​​​​
