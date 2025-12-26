# Rating Profi Platform

Professional hamjamiyat platformasi - dizaynerlar, yetkazib beruvchilar, pudratchilar va interyer dizayni jurnallari uchun.

## Loyiha strukturası

Platforma quyidagi alohida Django app'laridan iborat:

1. **accounts** - Foydalanuvchilar, avtorizatsiya (SMS orqali), profillar
2. **reviews** - Sharhlar tizimi
3. **ratings** - Reyting tizimi (yulduzcha tizimi)
4. **payments** - To'lovlar va tariflar
5. **events** - Tadbirlar taqvimi
6. **reports** - Hisobotlar
7. **media** - Media/Jurnallar yangiliklari

## O'rnatish

### 1. Virtual environment faollashtirish

```powershell
.\env\Scripts\Activate.ps1
```

### 2. .env fayl yaratish

`.env.example` faylini `.env` ga nusxalang va quyidagi ma'lumotlarni to'ldiring:

```env
# Database
DB_NAME=rating_profi
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# SMS Aero
SMSAERO_EMAIL=your_email@example.com
SMSAERO_API_KEY=your_api_key_here

# Media files
MEDIA_ROOT=/var/www/media

# Django
DEBUG=True
SECRET_KEY=your_secret_key_here
```

### 3. Migrations yaratish va qo'llash

```powershell
.\env\Scripts\python.exe manage.py makemigrations
.\env\Scripts\python.exe manage.py migrate
```

### 4. Superuser yaratish

```powershell
.\env\Scripts\python.exe manage.py createsuperuser
```

### 5. Server ishga tushirish

```powershell
.\env\Scripts\python.exe manage.py runserver
```

## API Endpoints

### Avtorizatsiya (Accounts)

- `POST /api/v1/accounts/send-sms/` - SMS kod yuborish
- `POST /api/v1/accounts/verify-sms/` - SMS kodni tekshirish va token olish
- `GET /api/v1/accounts/profile/` - O'z profilini ko'rish
- `PUT /api/v1/accounts/profile/` - Profilni yangilash
- `GET /api/v1/accounts/users/{id}/` - Boshqa foydalanuvchi profilini ko'rish

### Sharhlar (Reviews)

- `GET /api/v1/reviews/` - Sharhlar ro'yxati
- `POST /api/v1/reviews/create/` - Sharh yaratish
- `GET /api/v1/reviews/{id}/` - Sharh tafsilotlari
- `PUT /api/v1/reviews/{id}/` - Sharhni yangilash
- `DELETE /api/v1/reviews/{id}/` - Sharhni o'chirish
- `GET /api/v1/reviews/user/{user_id}/` - Foydalanuvchi sharhlari
- `PUT /api/v1/reviews/{id}/moderate/` - Sharhni moderatsiya qilish (admin)

### Reytinglar (Ratings)

- `GET /api/v1/ratings/me/` - O'z reytingini ko'rish
- `GET /api/v1/ratings/user/{user_id}/` - Foydalanuvchi reytingi
- `GET /api/v1/ratings/leaderboard/` - Reyting jadvali
- `POST /api/v1/ratings/recalculate/{user_id}/` - Reytingni qayta hisoblash (admin)

### To'lovlar (Payments)

- `GET /api/v1/payments/plans/` - To'lov rejalari
- `POST /api/v1/payments/create/` - To'lov yaratish
- `GET /api/v1/payments/` - To'lovlar ro'yxati
- `GET /api/v1/payments/{id}/` - To'lov tafsilotlari
- `GET /api/v1/payments/subscription/` - O'z obunasini ko'rish

### Tadbirlar (Events)

- `GET /api/v1/events/` - Tadbirlar ro'yxati
- `GET /api/v1/events/calendar/` - Tadbirlar taqvimi
- `GET /api/v1/events/{id}/` - Tadbir tafsilotlari
- `POST /api/v1/events/{event_id}/grant-access/` - Tadbirga kirish huquqi berish (admin)

### Hisobotlar (Reports)

- `GET /api/v1/reports/` - Hisobotlar ro'yxati
- `GET /api/v1/reports/{id}/` - Hisobot tafsilotlari
- `POST /api/v1/reports/generate/monthly-partners/` - Oylik hamkorlar hisoboti
- `POST /api/v1/reports/generate/rating/` - Reyting hisoboti

### Media (Yangiliklar)

- `GET /api/v1/media/news/` - Yangiliklar ro'yxati
- `POST /api/v1/media/news/create/` - Yangilik yaratish (media roli)
- `GET /api/v1/media/news/{id}/` - Yangilik tafsilotlari
- `PUT /api/v1/media/news/{id}/moderate/` - Yangilikni moderatsiya qilish (admin)

## API Dokumentatsiyasi

- Swagger UI: `http://localhost:8000/docs/`
- ReDoc: `http://localhost:8000/redoc/`
- Schema: `http://localhost:8000/schema/`

## SMS Integratsiyasi

SMS kodlar `smsaero.ru` orqali yuboriladi. `.env` faylida quyidagi ma'lumotlarni belgilang:

```env
SMSAERO_EMAIL=your_email@example.com
SMSAERO_API_KEY=your_api_key_here
```

## Foydalanuvchi rollari

1. **designer** - Dizayner/Me'mor
2. **repair** - Ta'mirlash guruhi/Pudratchi
3. **supplier** - Yetkazib beruvchi/Ko'rgazma zali/Fabrik
4. **media** - Interior Design Magazine / Media
5. **admin** - Administrator

## Reyting tizimi

Reyting tizimi noyob yondashuvga ega:
- Har bir yulduz = bitta tasdiqlangan o'zaro ta'sir
- ⭐ - Ijobiy sharh
- ☆ - Salbiy/Konstruktiv sharh
- Reyting sub'ektiv baho emas, balki tasdiqlangan aloqalar soniga asoslanadi

## To'lov rejalari

- **Dizaynerlar**: Yillik (yangi boshlovchilar x4)
- **Yetkazib beruvchilar va pudratchilar**: Choraklik
- **Jurnallar**: Bepul

## Qo'shimcha ma'lumotlar

- Barcha sharhlar va so'rovnomalar qo'lda moderatsiya qilinadi
- Foydalanuvchilar o'z ma'lumotlarini mustaqil tahrirlay olmaydi (faqat admin/moderator)
- Profillar moderator tomonidan tasdiqlanguncha ko'rinmaydi
