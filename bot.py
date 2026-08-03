import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from key_system import (
    init_db,
    criar_key,
    validar_key,
    listar_keys,
    deletar_key,
    listar_acessos,
    limpar_logs,
    exportar_logs_csv,
    exportar_logs_txt,
    VALIDADES,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [5539193237]  # ← COLOQUE SEU ID AQUI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_valid_ip(ip: str) -> bool:
    pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    return bool(re.match(pattern, ip))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Ativar Key", callback_data="ativar_key")],
        [InlineKeyboardButton("🌐 Validar IP", callback_data="validar_ip")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bem-vindo!\n\nEscolha uma opção abaixo ou envie sua key diretamente.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "ativar_key":
        await query.edit_message_text(
            "🔑 Envie agora a sua **key** de ativação.\n\nExemplo: `TG-XXXX-XXXX-XXXX-XXXX`",
            parse_mode="Markdown"
        )
        context.user_data["estado"] = "aguardando_key"
    elif query.data == "validar_ip":
        await query.edit_message_text(
            "🌐 **Validar IP**\n\nEnvie no formato:\n`KEY|IP`\n\nExemplo:\n`TG-XXXX-XXXX-XXXX-XXXX|192.168.1.10`",
            parse_mode="Markdown"
        )
        context.user_data["estado"] = "aguardando_validar_ip"

async def mensagem_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.effective_user.id
    estado = context.user_data.get("estado")

    if estado == "aguardando_validar_ip" or "|" in texto:
        if "|" not in texto:
            await update.message.reply_text("❌ Formato inválido. Use: `KEY|IP`", parse_mode="Markdown")
            return
        partes = texto.split("|")
        if len(partes) != 2:
            await update.message.reply_text("❌ Formato inválido. Use: `KEY|IP`", parse_mode="Markdown")
            return
        key = partes[0].strip().upper()
        ip = partes[1].strip()
        if not is_valid_ip(ip):
            await update.message.reply_text("❌ IP inválido.")
            return
        resultado = validar_key(key, user_id=user_id, ip=ip)
        if resultado["valida"]:
            await update.message.reply_text(
                f"{resultado['mensagem']}\n🌐 IP vinculado: `{resultado.get('ip_vinculado', ip)}`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(resultado["mensagem"])
        context.user_data.clear()
        return

    if texto.upper().startswith("TG-") or estado == "aguardando_key":
        key = texto.upper()
        resultado = validar_key(key, user_id=user_id)
        if resultado.get("precisa_ip"):
            await update.message.reply_text(
                f"{resultado['mensagem']}\n\nEnvie no formato:\n`KEY|SEU_IP`",
                parse_mode="Markdown"
            )
            context.user_data["estado"] = "aguardando_validar_ip"
            return
        if resultado["valida"]:
            await update.message.reply_text(f"{resultado['mensagem']}\n\n🎉 Acesso liberado!", parse_mode="Markdown")
        else:
            await update.message.reply_text(resultado["mensagem"])
        context.user_data.clear()

async def gerar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "📝 **Como usar:**\n`/gerar <validade> [quantidade] [usos] [ip]`\n\n"
            "Exemplos:\n`/gerar 7d`\n`/gerar 30d 5`\n`/gerar 1d 1 1 192.168.0.10`",
            parse_mode="Markdown"
        )
        return
    validade = args[0].lower()
    quantidade = int(args[1]) if len(args) > 1 else 1
    usos = int(args[2]) if len(args) > 2 else 1
    ip = args[3] if len(args) > 3 else None
    if validade not in VALIDADES:
        await update.message.reply_text(f"❌ Validade inválida. Use: {', '.join(VALIDADES.keys())}")
        return
    if ip and not is_valid_ip(ip):
        await update.message.reply_text("❌ IP inválido.")
        return
    keys_geradas = [criar_key(validade=validade, usos_maximos=usos, ip=ip) for _ in range(quantidade)]
    texto = f"✅ **{quantidade} key(s) gerada(s)**\nValidade: `{validade}` | Usos: `{usos}`\n"
    if ip:
        texto += f"IP vinculado: `{ip}`\n"
    texto += "\n"
    for k in keys_geradas:
        texto += f"`{k['key']}`\n└ Expira: {k['expira_em']}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    apenas_ativas = bool(context.args and context.args[0].lower() in ["ativas", "ativa"])
    keys = listar_keys(apenas_ativas=apenas_ativas)
    if not keys:
        await update.message.reply_text("📭 Nenhuma key encontrada.")
        return
    texto = f"🔑 **{'Keys Ativas' if apenas_ativas else 'Todas as Keys'}** ({len(keys)})\n\n"
    for k in keys[:15]:
        ip_info = f" | IP: `{k['ip_vinculado']}`" if k.get("ip_vinculado") else ""
        status = "✅" if not k["usada"] else "❌"
        texto += f"{status} `{k['key']}`\n├ {k['validade']} | Usos: {k['usos']}{ip_info}\n└ Expira: {k['expira_em']}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def deletar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    if not context.args:
        await update.message.reply_text("📝 Uso: `/deletar TG-XXXX-...`", parse_mode="Markdown")
        return
    key = context.args[0].upper()
    if deletar_key(key):
        await update.message.reply_text(f"🗑️ Key `{key}` deletada.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Key não encontrada.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    todas = listar_keys(False)
    ativas = listar_keys(True)
    usadas = len([k for k in todas if k["usada"]])
    com_ip = len([k for k in todas if k.get("ip_vinculado")])
    texto = (
        "📊 **Estatísticas**\n\n"
        f"• Total: `{len(todas)}`\n"
        f"• Ativas: `{len(ativas)}`\n"
        f"• Usadas: `{usadas}`\n"
        f"• Com IP vinculado: `{com_ip}`"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    args = context.args
    if args and args[0].lower() == "limpar":
        dias = int(args[1]) if len(args) > 1 else 30
        removidos = limpar_logs(dias)
        await update.message.reply_text(f"🧹 {removidos} logs removidos.")
        return
    if args and args[0].lower() == "exportar":
        formato = args[1].lower() if len(args) > 1 else "csv"
        key = user_id = ip = None
        if len(args) >= 4:
            if args[2].lower() == "key":
                key = args[3]
            elif args[2].lower() == "user":
                user_id = int(args[3])
            elif args[2].lower() == "ip":
                ip = args[3]
        await update.message.reply_text("⏳ Gerando arquivo...")
        try:
            if formato == "txt":
                caminho = exportar_logs_txt(key=key, user_id=user_id, ip=ip)
            else:
                caminho = exportar_logs_csv(key=key, user_id=user_id, ip=ip)
            with open(caminho, "rb") as f:
                await update.message.reply_document(document=f, filename=os.path.basename(caminho))
            os.remove(caminho)
        except Exception as e:
            await update.message.reply_text(f"❌ Erro: {e}")
        return
    key = user_id = ip = None
    if args:
        if args[0].lower() == "key" and len(args) > 1:
            key = args[1]
        elif args[0].lower() == "user" and len(args) > 1:
            user_id = int(args[1])
        elif args[0].lower() == "ip" and len(args) > 1:
            ip = args[1]
    acessos = listar_acessos(limite=20, key=key, user_id=user_id, ip=ip)
    if not acessos:
        await update.message.reply_text("📭 Nenhum log encontrado.")
        return
    texto = f"📋 **Logs de Acesso** ({len(acessos)})\n\n"
    for a in acessos:
        status = "✅" if a["sucesso"] else "❌"
        texto += (
            f"{status} `{a['key'] or '—'}`\n"
            f"├ User: `{a['user_id'] or '—'}` | IP: `{a['ip'] or '—'}`\n"
            f"├ {a['mensagem']}\n"
            f"└ {a['data_hora']}\n\n"
        )
    if len(texto) > 4000:
        texto = texto[:3900] + "\n\n... (truncado)"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Você não tem permissão.")
        return
    texto = (
        "🛠️ **Comandos Admin**\n\n"
        "`/gerar <validade> [qtd] [usos] [ip]`\n"
        "`/listar` / `/listar ativas`\n"
        "`/deletar <key>`\n"
        "`/stats`\n"
        "`/logs`\n"
        "`/logs exportar csv`\n"
        "`/logs exportar txt`\n"
        "`/admin`"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_texto))
    app.add_handler(CommandHandler("gerar", gerar))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("deletar", deletar))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("admin", admin_help))
    print("🤖 Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
