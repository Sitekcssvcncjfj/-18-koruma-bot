import re
import os
import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

# ========== AYARLAR (Railway Variables'dan okunur) ==========
TOKEN = os.getenv("TOKEN")
SE_USER = os.getenv("SE_USER")
SE_SECRET = os.getenv("SE_SECRET")
# ============================================================

# Telefon Regex: +90 veya 05x biçimlerini kapsar (Türkiye)
PHONE_REGEX = re.compile(r'(\+90|0)?\s*5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}')

# TCKN Regex: Tam 11 haneli, baş rakam 1–9
TC_REGEX = re.compile(r'\b[1-9]\d{10}\b')

def tckn_dogrula(tckn: str) -> bool:
    """TC Kimlik Numarasını matematiksel olarak doğrular (baş 1–9 zorunlu)."""
    if len(tckn) != 11:
        return False
    if tckn[0] == '0':
        return False  # İlk rakam 0 olamaz
    
    a = list(map(int, tckn))
    
    # Onuncu kontrol (7*A - B)
    onuncu_basamak = ((sum(a[0:10:2]) * 7) - sum(a[1:9:2])) % 10
    
    # Onbirinci kontrol (Tüm rakamların toplamının 10'a bölümünden kalanı)
    onbirinci_basamak = sum(a[:10]) % 10
    
    if a[9] == onuncu_basamak and a[10] == onbirinci_basamak:
        return True
    return False

async def nsfw_kontrol(file_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Sightengine API ile fotoğraf/video/gif/sticker analiz ederek çıplaklık/NSFW algılar.
    """
    try:
        file = await context.bot.get_file(file_id)
        file_url = file.file_path  # Telegram direkt dosya yolunu sağlar
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
            # Yüksek hassasiyetli NSFW ölçütleri
            return (
                n.get("sexual_activity", 0) > 0.7 or 
                n.get("sexual_display", 0) > 0.7 or 
                n.get("erotica", 0) > 0.7
            )
        return False
    except Exception as e:
        print(f"Sightengine kontrol hatası: {e}")
        return False

async def komut_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Bu bot, grupta +18 içerik (foto/video/GIF/sticker), TCKN ve telefon numaralarını otomatik siler. "
        "Yöneticiler kontrol edilmez."
    )

async def filtrele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type not in ["group", "supergroup"]:
        return

    # Yönetici/Creator kontrolü
    try:
        member = await msg.chat.get_member(msg.from_user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception as e:
        print(f"Üye durumu alınamadı (skip): {e}")
        return

    # --- METİN KONTROLÜ: TCKN & TELEFON ---
    text = (msg.text or "") + (msg.caption or "")
    
    if PHONE_REGEX.search(text):
        await msg.delete()
        print(f"Telefon silindi: {text} | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
        return

    tckn_list = TC_REGEX.findall(text)
    for tc in tckn_list:
        if tckn_dogrula(tc):
            await msg.delete()
            print(f"TCKN silindi: {tc} | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
            return

    # --- MEDYA KONTROLÜ: +18 (FOTO / GIF / VIDEO / STICKER) ---
    try:
        print(f"Medya türü tespit edildi: {msg.effective_attachment}")

        if msg.photo:
            if await nsfw_kontrol(msg.photo[-1].file_id, context):
                await msg.delete()
                print(f"Fotoğraf silindi (NSFW) | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
        elif msg.animation:  # GIF
            if await nsfw_kontrol(msg.animation.file_id, context):
                await msg.delete()
                print(f"GIF silindi (NSFW) | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
        elif msg.video:
            if await nsfw_kontrol(msg.video.file_id, context):
                await msg.delete()
                print(f"Video silindi (NSFW) | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
        elif msg.sticker:
            if msg.sticker.is_video or msg.sticker.is_animated:
                await msg.delete()
                print(f"Sticker (video/animasyon) silindi | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
            elif await nsfw_kontrol(msg.sticker.file_id, context):
                await msg.delete()
                print(f"Sticker silindi (NSFW) | Kullanıcı: {msg.from_user.username or msg.from_user.id}")
    except Exception as e:
        print(f"Medya silme/analiz hatası: {e}")

def main():
    if not TOKEN:
        raise ValueError("TOKEN bulunamadı! Railway Variables'a ekle.")
    app = Application.builder().token(TOKEN).build()
    
    # Komut handler
    app.add_handler(CommandHandler("start", komut_start))
    
    # Genel mesaj handler
    app.add_handler(MessageHandler(filters.ALL, filtrele))
    
    print("Bot Başlatıldı... Loglar aktif (TCKN/Telefon/+18 medya için silme hazır).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
