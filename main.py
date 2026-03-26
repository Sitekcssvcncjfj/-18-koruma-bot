import os
import re
import logging
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ========== LOG AYARLARI ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ÇEVRE DEĞİŞKENLERİ (Railway'de ayarlayacağız) ==========
TOKEN = os.environ.get("TOKEN")
SE_USER = os.environ.get("SE_USER")      # Sightengine API User
SE_SECRET = os.environ.get("SE_SECRET")  # Sightengine API Secret

if not TOKEN:
    raise ValueError("TOKEN çevre değişkeni bulunamadı!")

# ========== REGEX PATTERNLER ==========
# Telefon numarası (Türkiye formatları: +905321234567, 05321234567, 532 123 45 67)
PHONE_PATTERN = re.compile(
    r'(\+?90[-\s]?)?0?\s?5\d{2}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}\b'
)

# TCKN (11 haneli, ilk rakam 0 olamaz)
TC_PATTERN = re.compile(r'\b[1-9]\d{10}\b')

# ========== TCKN DOĞRULAMA ALGORİTMASI ==========
def tc_dogrula(tc_numara: str) -> bool:
    """
    TCKN algoritması:
    1. 11 haneli olmalı
    2. İlk hane 0 olamaz
    3. 10. hane = (1+3+5+7+9. haneler * 7 - 2+4+6+8. haneler) % 10
    4. 11. hane = (1+2+3+...+9+10. haneler) % 10
    """
    if not tc_numara or len(tc_numara) != 11:
        return False
    
    if not tc_numara.isdigit():
        return False
    
    if tc_numara[0] == '0':
        return False
    
    digits = [int(d) for d in tc_numara]
    
    # 1. 3. 5. 7. 9. hanelerin toplamı
    tek_toplam = sum(digits[i] for i in range(0, 9, 2))
    # 2. 4. 6. 8. hanelerin toplamı
    cift_toplam = sum(digits[i] for i in range(1, 9, 2))
    
    # 10. hane kontrolü
    hane10 = (tek_toplam * 7 - cift_toplam) % 10
    if digits[9] != hane10:
        return False
    
    # 11. hane kontrolü
    hane11 = sum(digits[:10]) % 10
    if digits[10] != hane11:
        return False
    
    return True

# ========== NSFW KONTROLÜ (Sightengine) ==========
async def nsfw_kontrol(file_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Fotoğraf/GIF/Sticker'ı kontrol et (Sightengine API - Ücretsiz 5000 istek/ay)
    """
    if not SE_USER or not SE_SECRET:
        return False  # API yoksa kontrol yapma
    
    try:
        # Dosyayı Telegram'dan al
        file = await context.bot.get_file(file_id)
        file_url = file.file_path
        
        # Sightengine API'ye istek at
        url = "https://api.sightengine.com/1.0/check.json"
        params = {
            'models': 'nudity-2.0',
            'api_user': SE_USER,
            'api_secret': SE_SECRET,
            'url': file_url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Nudity skorlarını kontrol et
                    nudity = data.get('nudity', {})
                    
                    # Yüksek ihtimalle +18 içerik
                    if nudity.get('sexual_activity', 0) > 0.75:
                        return True
                    if nudity.get('sexual_display', 0) > 0.75:
                        return True
                    if nudity.get('erotica', 0) > 0.75:
                        return True
                        
    except Exception as e:
        logger.error(f"NSFW kontrol hatası: {e}")
    
    return False

# ========== ANA KONTROL FONKSİYONU ==========
async def mesaj_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gelen her mesajı kontrol et"""
    
    if not update.message:
        return
    
    msg = update.message
    chat = msg.chat
    user = msg.from_user
    
    # Sadece gruplarda çalış
    if chat.type not in ['group', 'supergroup']:
        return
    
    try:
        # Admin kontrolü - Adminleri atla
        member = await chat.get_member(user.id)
        if member.status in ['administrator', 'creator']:
            return
        
        silindi = False
        sebep = ""
        
        # 1. METİN KONTROLÜ (Telefon & TCKN)
        metin = ""
        if msg.text:
            metin = msg.text
        elif msg.caption:
            metin = msg.caption
        
        if metin:
            # Telefon numarası kontrolü
            if PHONE_PATTERN.search(metin):
                silindi = True
                sebep = "Telefon numarası"
            
            # TCKN kontrolü
            if not silindi:
                for tc in TC_PATTERN.findall(metin):
                    if tc_dogrula(tc):
                        silindi = True
                        sebep = "TCKN"
                        break
        
        # 2. MEDYA KONTROLÜ (+18 Fotoğraf/GIF/Sticker)
        if not silindi:
            file_id = None
            
            if msg.photo:
                # En yüksek çözünürlüklü fotoğrafı al
                file_id = msg.photo[-1].file_id
            elif msg.animation:  # GIF
                file_id = msg.animation.file_id
            elif msg.sticker:    # Sticker
                file_id = msg.sticker.file_id
            
            if file_id:
                if await nsfw_kontrol(file_id, context):
                    silindi = True
                    sebep = "Uygunsuz içerik (+18)"
        
        # 3. SİLME İŞLEMİ
        if silindi:
            await msg.delete()
            logger.info(f"Silindi: {sebep} - Kullanıcı: {user.username or user.id} - Grup: {chat.title}")
            
            # Opsiyonel: Kullanıcıya bildirim (5 saniye sonra silinebilir)
            # await msg.chat.send_message(f"@{user.username} {sebep} paylaşımı yasaktır!", delete_after=5)
            
    except Exception as e:
        logger.error(f"Mesaj kontrol hatası: {e}")

# ========== BOTU BAŞLAT ==========
def main():
    # Application oluştur
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Tüm mesajları dinle (foto, video, text, sticker vb.)
    application.add_handler(MessageHandler(filters.ALL, mesaj_kontrol))
    
    logger.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == "__main__":
    main()
