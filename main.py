import re
import os
import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TOKEN")
SE_USER = os.getenv("SE_USER")
SE_SECRET = os.getenv("SE_SECRET")

PHONE_REGEX = re.compile(r'(\+90|0)?\s*5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}')
TC_REGEX = re.compile(r'\b[1-9]\d{10}\b')

def tckn_dogrula(tckn: str) -> bool:
    if len(tckn) != 11 or tckn[0] == '0':
        return False
    a = list(map(int, tckn))
    if sum(a[:10]) % 10 != a[10]:
        return False
    if ((sum(a[0:10:2]) * 7) - sum(a[1:9:2])) % 10 != a[9]:
        return False
    return True

async def nsfw_kontrol(file_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        file = await context.bot.get_file(file_id)
        file_url = file.file_path
        if not file_url.startswith("http"):
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_url}"

        params = {
            "models": "nudity-2.0",
            "api_user": SE_USER,
            "api_secret": SE_SECRET,
            "url": file_url
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get("https://api.sightengine.com/1.0/check.json", params=params)
            data = r.json()

        if data.get("status") == "success":
            n = data.get("nudity", {})
            return (n.get("sexual_activity", 0) > 0.7 or 
                    n.get("sexual_display", 0) > 0.7 or 
                    n.get("erotica", 0) > 0.7)
        return False
    except Exception as e:
        print(f"Sightengine kontrol hatası: {e}")
        return False

async def komut_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Bu bot, grupta +18 içerik, TCKN ve telefon numaralarını otomatik siler. "
        "Yöneticiler kontrol edilmez."
    )

async def filtrele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type not in ["group", "supergroup"]:
        return

    # Yönetici veya kurucuysa dokunma
    try:
        member = await msg.chat.get_member(msg.from_user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception as e:
        print(f"Üye durumu alınamadı: {e}")
        return

    # Metin kontrolü
    text = (msg.text or "") + (msg.caption or "")
    if PHONE_REGEX.search(text):
        await msg.delete()
        return
    for tc in TC_REGEX.findall(text):
        if tckn_dogrula(tc):
            await msg.delete()
            return

    # Medya kontrolü
    try:
        print(f"Medya türü: {type(msg.effective_attachment)}")  # Debug satırı

        if msg.photo:
            if await nsfw_kontrol(msg.photo[-1].file_id, context):
                await msg.delete()
        elif msg.animation:  # GIF
            if await nsfw_kontrol(msg.animation.file_id, context):
                await msg.delete()
        elif msg.video:  # VİDEO (EKLENDİ!)
            if await nsfw_kontrol(msg.video.file_id, context):
                await msg.delete()
        elif msg.sticker:
            if msg.sticker.is_video or msg.sticker.is_animated:
                await msg.delete()
            elif await nsfw_kontrol(msg.sticker.file_id, context):
                await msg.delete()
    except Exception as e:
        print(f"Silme/analiz hatası: {e}")

def main():
    if not TOKEN:
        raise ValueError("TOKEN bulunamadı!")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", komut_start))
    app.add_handler(MessageHandler(filters.ALL, filtrele))
    print("Bot Başlatıldı... Grupları düzenleyerek korumaya hazır.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
