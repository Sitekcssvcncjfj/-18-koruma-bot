import re
import aiohttp
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ========== AYARLAR (Railway Variables kısmından okunur) ==========
TOKEN = os.getenv("TOKEN")
SE_USER = os.getenv("SE_USER")
SE_SECRET = os.getenv("SE_SECRET")
# ================================================================

# Telefon Numarası Regex (Türkiye formatları: 05xx, 5xx, +905xx)
PHONE_REGEX = re.compile(r'(\+90|0)?\s*5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}')

# TCKN Regex (11 haneli ve 0 ile başlamayan)
TC_REGEX = re.compile(r'\b[1-9]\d{10}\b')

def tckn_dogrula(tckn):
    """TC Kimlik Numarasını matematiksel algoritmaya göre doğrular."""
    if len(tckn) != 11: return False
    a = list(map(int, tckn))
    if a[0] == 0: return False
    
    # Algoritma kontrolü
    onuncu_basamak = ((sum(a[0:10:2]) * 7) - sum(a[1:9:2])) % 10
    onbirinci_basamak = sum(a[:10]) % 10
    
    if a[9] == onuncu_basamak and a[10] == onbirinci_basamak:
        return True
    return False

async def nsfw_kontrol(file_id, context):
    """Sightengine API kullanarak görselin içeriğini analiz eder."""
    try:
        file = await context.bot.get_file(file_id)
        # Telegram dosya yolunu oluştur
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        
        params = {
            "models": "nudity-2.0",
            "api_user": SE_USER,
            "api_secret": SE_SECRET,
            "url": file_url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.sightengine.com/1.0/check.json", params=params) as r:
                data = await r.json()
        
        if data.get("status") == "success":
            n = data.get("nudity", {})
            # Cinsel aktivite veya erotizm oranı %70 üzerindeyse True döner
            if n.get("sexual_activity", 0) > 0.7 or n.get("sexual_display", 0) > 0.7 or n.get("erotica", 0) > 0.7:
                return True
        return False
    except Exception as e:
        print(f"Hata: {e}")
        return False

async def filtrele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.chat: return

    # Sadece gruplarda çalış
    if msg.chat.type not in ["group", "supergroup"]:
        return

    # Gönderen yönetici ise dokunma
    try:
        member = await msg.chat.get_member(msg.from_user.id)
        if member.status in ["administrator", "creator"]:
            return
    except:
        pass

    # --- METİN KONTROLÜ (TCKN & TELEFON) ---
    text_to_check = (msg.text or "") + (msg.caption or "")
    
    # Telefon kontrolü
    if PHONE_REGEX.search(text_to_check):
        await msg.delete()
        return

    # TCKN kontrolü
    tckn_list = TC_REGEX.findall(text_to_check)
    for tc in tckn_list:
        if tckn_dogrula(tc):
            await msg.delete()
            return

    # --- MEDYA KONTROLÜ (+18 GÖRSEL/GIF/STICKER) ---
    try:
        if msg.photo: # Fotoğraflar
            if await nsfw_kontrol(msg.photo[-1].file_id, context):
                await msg.delete()
        
        elif msg.animation: # GIF'ler
            if await nsfw_kontrol(msg.animation.file_id, context):
                await msg.delete()
                
        elif msg.sticker: # Sticker'lar
            # Hareketli stickerlar analiz edilemeyebilir, risk varsa silebilirsiniz
            if await nsfw_kontrol(msg.sticker.file_id, context):
                await msg.delete()
    except:
        pass

if __name__ == "__main__":
    if not TOKEN:
        print("HATA: TOKEN bulunamadı!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.ALL, filtrele))
        print("Bot Başlatıldı... Grupları korumaya hazır.")
        app.run_polling()
