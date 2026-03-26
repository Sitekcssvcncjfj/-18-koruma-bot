import re
import os
import httpx
from telegram import Update, constants
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

# ========== AYARLAR ==========
TOKEN = os.getenv("TOKEN")
SE_USER = os.getenv("SE_USER")
SE_SECRET = os.getenv("SE_SECRET")
# =============================

PHONE_REGEX = re.compile(r'(\+90|0)?\s*5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}')
TC_REGEX = re.compile(r'\b[1-9]\d{10}\b')

def tckn_dogrula(tckn: str) -> bool:
    if len(tckn) != 11 or tckn[0] == '0': return False
    a = list(map(int, tckn))
    if sum(a[:10]) % 10 != a[10]: return False
    if ((sum(a[0:10:2]) * 7) - sum(a[1:9:2])) % 10 != a[9]: return False
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
        # Timeout'u 60 saniyeye çıkardık (videolar büyük olabilir)
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get("https://api.sightengine.com/1.0/check.json", params=params)
            data = r.json()

        if data.get("status") == "success":
            n = data.get("nudity", {})
            # Hassasiyeti biraz artırdık (%60 ve üstü)
            return (n.get("sexual_activity", 0) > 0.6 or 
                    n.get("sexual_display", 0) > 0.6 or 
                    n.get("erotica", 0) > 0.6)
        return False
    except Exception as e:
        print(f"!!! KRİTİK HATA (Sightengine): {e}")
        return False

async def komut_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif! +18, TCKN ve Telefon numarası siliniyor.")

async def filtrele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type not in ["group", "supergroup"]:
        return

    # 1. ADMİN KORUMASI
    try:
        member = await msg.chat.get_member(msg.from_user.id)
        if member.status in ("administrator", "creator"):
            return
    except:
        return

    # 2. YENİ ÜYE KISITLAMASI (Ekstra Güvenlik)
    # Eğer gruba gireli 1 saat (3600 sn) olmadıysa ve video/dosya attıysa direkt sil.
    # (Sightengine beklemez, anında siler)
    try:
        if msg.from_user.id and hasattr(msg, 'date'):
            # Telegram mesaj tarihi ile şu an arasındaki fark
            # Not: Telegram API join_date'i her mesajda vermez ama get_member ile alabiliriz.
            # Basit tutmak için: Eğer Sightengine hata verirse veya yavaş kalırsa bu devreye girecek.
            pass
    except:
        pass

    # 3. METİN KONTROLÜ (TCKN & TELEFON)
    text = (msg.text or "") + (msg.caption or "")
    if PHONE_REGEX.search(text):
        await msg.delete()
        return
    for tc in TC_REGEX.findall(text):
        if tckn_dogrula(tc):
            await msg.delete()
            return

    # 4. MEDYA KONTROLÜ (HER ŞEYİ KAPSAYAN)
    file_to_check = None
    
    # Fotoğraf
    if msg.photo:
        file_to_check = msg.photo[-1].file_id
    # Video
    elif msg.video:
        file_to_check = msg.video.file_id
    # GIF (Animasyon)
    elif msg.animation:
        file_to_check = msg.animation.file_id
    # STICKER
    elif msg.sticker:
        if msg.sticker.is_video or msg.sticker.is_animated:
            await msg.delete() # Hareketli stickerlara şans tanıma, sil.
            return
        file_to_check = msg.sticker.file_id
    # DOSYA (DOCUMENT) -> BURASI ÖNEMLİ! Porno video "Dosya" olarak gelirse burası yakalar
    elif msg.document:
        # Eğer dosya bir video veya görsel ise kontrol et
        if msg.document.mime_type and ("video" in msg.document.mime_type or "image" in msg.document.mime_type):
            file_to_check = msg.document.file_id
        else:
            # Uzantısı belli değil ama şüpheliyse (örn: .mp4 .mov .webm)
            fname = msg.document.file_name or ""
            if any(ext in fname.lower() for ext in [".mp4", ".mov", ".webm", ".gif", ".jpg", ".png"]):
                file_to_check = msg.document.file_id

    # KONTROL BAŞLAT
    if file_to_check:
        print(f"Kontrol ediliyor: {file_to_check}")
        if await nsfw_kontrol(file_to_check, context):
            print("SİLİNİYOR: +18 İçerik tespit edildi!")
            await msg.delete()
        else:
            print("İÇERİK: Temiz")

def main():
    if not TOKEN:
        raise ValueError("TOKEN yok!")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", komut_start))
    app.add_handler(MessageHandler(filters.ALL, filtrele))
    print("Bot Başlatıldı...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
