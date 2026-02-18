import requests
import os
from django.conf import settings


def send_sms_via_smsaero(phone_number: str, code: str) -> dict:
    """
    SMS kodini smsaero.ru orqali yuborish
    
    Args:
        phone_number: Telefon raqami (masalan: +79991234567 yoki 998914180518)
        code: SMS kod (masalan: 1234)
    
    Returns:
        dict: API javobi
    """
    smsaero_email = os.getenv('SMSAERO_EMAIL', '')
    smsaero_api_key = os.getenv('SMSAERO_API_KEY', '')
    
    if not smsaero_email or not smsaero_api_key:
        raise ValueError("SMSAERO_EMAIL и SMSAERO_API_KEY должны быть указаны в .env файле")
    
    url = "https://gate.smsaero.ru/v2/sms/send"
    
    # SMSAero API formatiga moslashtirish
    # Telefon raqamini faqat raqamlarda qoldirish
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    
    # Telefon raqamini to'g'ri formatga o'zgartirish
    
    # Agar 8 bilan boshlansa (Rossiya), 7 ga o'zgartirish
    if clean_phone.startswith('8') and len(clean_phone) == 11:
        clean_phone = '7' + clean_phone[1:]
    # Agar 998 bilan boshlansa (O'zbekiston)
    elif clean_phone.startswith('998'):
        # SMS Aero asosan Rossiya raqamlari uchun
        # O'zbekiston raqamlari uchun alohida sozlash kerak bo'lishi mumkin
        # Hozircha raqamni o'zgartirmaymiz
        pass
    # Agar 7 bilan boshlanmasa va 998 ham emas, 7 qo'shish
    elif not clean_phone.startswith('7') and not clean_phone.startswith('998'):
        if len(clean_phone) == 10:
            clean_phone = '7' + clean_phone
    
    # Telefon raqami uzunligini tekshirish
    # Rossiya: 11 raqam (7 + 10)
    # O'zbekiston: 12 raqam (998 + 9)
    
    # O'zbekiston raqamlari uchun SMS service'ga so'rov yuborilmaydi
    # Bu funksiya faqat Rossiya va boshqa qo'llab-quvvatlanadigan raqamlar uchun chaqiriladi
    is_uzbekistan = clean_phone.startswith('998')
    
    # SMS Aero shablonidan foydalanish
    # Shablon nomi: "Код авторизации Rating Profi"
    message = f"Ваш код для входа в Рейтинг Профи: {code}. Код действителен 5 минут."
    
    # SMS Aero API v2 formatida sign (imzo) kabinetda tasdiqlangan bo'lishi kerak
    # Sign kabinetda sozlanadi: https://smsaero.ru/cabinet/settings/sign/
    # MUHIM: Sign maksimal 11 belgidan iborat bo'lishi kerak (bo'shliq ham hisoblanadi)
    sign = os.getenv('SMSAERO_SIGN', '')  # Sign .env dan olinadi
    
    # Sign uzunligini tekshirish va qisqartirish
    if sign and len(sign) > 11:
        sign = sign[:11].strip()
    
    # URL encoding
    from urllib.parse import urlencode
    
    # SMS Aero API v2 formatida sign MAJBURIY (required)
    # Sign bo'lmasa, API 400 xatolik qaytaradi
    params = {
        'number': clean_phone,
        'text': message,
    }
    
    # Sign majburiy, shuning uchun har doim qo'shamiz
    if sign:
        params['sign'] = sign
    
    # URL yaratish
    full_url = f"{url}?{urlencode(params, safe='')}"
    
    # Basic Auth
    auth = (smsaero_email, smsaero_api_key)
    
    # SMS yuborishni sinab ko'ramiz (O'zbekiston raqamlari ham)
    try:
        response = requests.get(full_url, auth=auth, timeout=10)
        
        # Xatolik bo'lsa, tafsilotlarni ko'rsatish
        if response.status_code != 200:
            error_detail = response.text
            try:
                error_json = response.json()
                error_msg = error_json.get('message', error_detail)
                error_data = error_json
            except:
                error_msg = error_detail
                error_data = {'raw_response': error_detail}
            
            # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shamiz
            if is_uzbekistan:
                return {
                    'success': True,
                    'message': f'SMS не отправлен (ошибка API: {error_msg}). Для узбекских номеров код отправлен в ответе.',
                    'data': {'code': code},
                    'error': error_data
                }
            
            # Development rejimida xatolikni ko'rsatmasdan qaytamiz
            if settings.DEBUG:
                return {
                    'success': True,
                    'message': f'SMS не отправлен (ошибка API: {error_msg}), но код отображается в консоли (DEBUG mode)',
                    'data': {'code': code},
                    'error': error_data
                }
            
            raise Exception(f"Ошибка отправки SMS: {error_msg}")
        
        result = response.json()
        
        # SMS Aero API javobini tekshirish
        if not result.get('success', False):
            error_msg = result.get('message', 'Неизвестная ошибка')
            # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shamiz
            if is_uzbekistan:
                return {
                    'success': True,
                    'message': f'SMS не отправлен (ошибка API: {error_msg}). Для узбекских номеров код отправлен в ответе.',
                    'data': {'code': code}
                }
            if settings.DEBUG:
                return {
                    'success': True,
                    'message': f'SMS не отправлен (ошибка API: {error_msg}), но код отображается в консоли (DEBUG mode)',
                    'data': {'code': code}
                }
            raise Exception(f"Ошибка отправки SMS: {error_msg}")
        
        # SMS ma'lumotlarini olish
        sms_data = result.get('data', {})
        sms_status = sms_data.get('status')
        extend_status = sms_data.get('extendStatus', '')
        sms_id = sms_data.get('id')
        
        # Agar SMS moderatsiyada bo'lsa
        if extend_status == 'moderation' or sms_status == 8:
            # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shamiz
            response_data = {
                'success': True,
                'message': 'SMS принят в обработку, но находится на модерации. После модерации SMS будет отправлен автоматически.',
                'data': {
                    'sms_id': sms_id,
                    'status': 'moderation',
                    'note': 'SMS будет отправлен после модерации (обычно 5-30 минут)'
                },
                'sms_data': sms_data
            }
            # O'zbekiston raqamlari uchun SMS kodini qo'shamiz
            if is_uzbekistan:
                response_data['data']['code'] = code
            return response_data
        
        # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shamiz
        if is_uzbekistan:
            result['data'] = result.get('data', {})
            result['data']['code'] = code
            result['message'] = 'SMS отправлен. Для узбекских номеров код также отправлен в ответе.'
        
        return result
        
    except requests.exceptions.RequestException as e:
        # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shamiz
        if is_uzbekistan:
            return {
                'success': True,
                'message': f'SMS не отправлен (ошибка сети: {str(e)}). Для узбекских номеров код отправлен в ответе.',
                'data': {'code': code}
            }
        if settings.DEBUG:
            return {
                'success': True,
                'message': f'SMS не отправлен (ошибка сети: {str(e)}), но код отображается в консоли (DEBUG mode)',
                'data': {'code': code}
            }
        raise Exception(f"Ошибка отправки SMS: {str(e)}")


def generate_sms_code() -> str:
    """
    4 xonali tasodifiy SMS kod yaratish
    """
    import random
    return str(random.randint(1000, 9999))
