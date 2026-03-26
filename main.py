import re
import os
import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

# ========== AYARLAR (Railway Variables) ==========
TOKEN = os.getenv("TOKEN")
SE_USER = os.getenv("SE_USER")
SE_SECRET = os.getenv("SE_SECRET")
# =================================================

# Telefon: +90 veya 05 ile başlayan
PHONE_REGEX = re.compile(r'(\+90|0)?\s*5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}')

# TCKN: 11 hane, başı 1-9
TC_REGEX = re.compile(r'\b[1-9]\d{10}\b')

def tckn_dogrula(tckn: str) -> bool:
    if len(tckn) != 11 or tckn[0] == '0':
        return False
    a = list(map(int, tckn))
    onuncu = ((sum(a[0:10:2]) * 7) - sum(a[1:9:2])) % 10
    onbir = sum(a[:10]) % 10
    return a[9] == onuncu and a[10] == onbir

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
        print(f"Sightengine hata: {e}")
        return False

async def komut_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot aktif. +18 foto/GIF/video, TCKN, telefon numarası siler. Sticker serbest. Yöneticilere dokunulmaz."
    )

async def filtrele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type not in ["group", "supergroup"]:
        return

    # Yönetici kontrolü
    try:
        member = await msg.chat.get_member(msg.from_user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception as e:
        print(f"Üye kontrol hatası: {e}")
        return

    # Metin kontrolü
    text = (msg.text or "") + (msg.caption or "")
    
    if PHONE_REGEX.search(text):
        await msg.delete()
        print(f"Telefon silindi: {text}")
        return

    for tc in TC_REGEX.findall(text):
        if tckn_dogrula(tc):
            await msg.delete()
            print(f"TCKN silindi: {tc}")
            return

    # Medya kontrolü
    try:
        if msg.photo:
            if await nsfw_kontrol(msg.photo[-1].file_id, context):
                await msg.delete()
                print("Fotoğraf silindi (NSFW)")
        elif msg.animation:  # GIF
            if await nsfw_kontrol(msg.animation.file_id, context):
                await msg.delete()
                print("GIF silindi (NSFW)")
        elif msg.video:
            # Video her zaman silinir (Sightengine video’da güvenilir değil)
            await msg.delete()
            print("Video silindi")
        # STICKER KONTROLÜ KALDIRILDI -> SERBEST
    except Exception as e:
        print(f"Medya hatası: {e}")

def main():
    if not TOKEN:
        raise ValueError("TOKEN yok!")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", komut_start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, filtrele))
    
    print("Bot başlatıldı. Sticker serbest.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
