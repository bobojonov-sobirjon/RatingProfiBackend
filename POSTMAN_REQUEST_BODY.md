# Postman Request Body - RepairQuestionnaire POST/PUT

## Request Settings

**Method:** `POST` yoki `PUT`  
**URL:** 
- POST: `http://127.0.0.1:8000/api/v1/accounts/repair-questionnaires/`
- PUT: `http://127.0.0.1:8000/api/v1/accounts/repair-questionnaires/{id}/`

## Headers

```
Authorization: Bearer YOUR_TOKEN_HERE
Content-Type: application/json
Accept: application/json
```

## JSON Request Body (To'g'ri Format)

```json
{
    "group": "repair_team",
    "brand_name": "Test Brand",
    "phone": "+79991234567",
    "email": "test@example.com",
    "responsible_person": "John Doe",
    "representative_cities": ["Moscow", "Saint Petersburg"],
    "business_form": "own_business",
    "work_list": "Remont ishlari",
    "welcome_message": "Xush kelibsiz",
    "cooperation_terms": "Shartlar",
    "project_timelines": "1 oy",
    "segments": ["horeca", "premium"],
    "vk": "https://vk.com/test",
    "telegram_channel": "@test",
    "pinterest": "https://pinterest.com/test",
    "instagram": "https://instagram.com/test",
    "website": "https://example.com",
    "other_contacts": ["email@test.com"],
    "work_format": "Online va offline",
    "vat_payment": "yes",
    "guarantees": "1 yil",
    "designer_supplier_terms": "Shartlar",
    "magazine_cards": ["hi_home", "in_home"],
    "additional_info": "Qo'shimcha ma'lumot",
    "data_processing_consent": true,
    "company_logo": null,
    "legal_entity_card": null
}
```

## Valid Choices

### segments (array)
- `"horeca"`
- `"business"`
- `"comfort"`
- `"premium"`
- `"medium"`
- `"economy"`

### magazine_cards (array)
- `"hi_home"`
- `"in_home"`
- `"no"`
- `"other"`

### business_form
- `"own_business"`
- `"franchise"`

### vat_payment
- `"yes"`
- `"no"`

### group
- `"repair_team"` - Ремонтная бригада
- `"contractor"` - Подрядчик
- `"supplier"` - Поставщик
- `"designer"` - Дизайнер
- va boshqalar...

## Form-Data Format (Alternative)

Agar `multipart/form-data` formatida yubormoqchi bo'lsangiz:

| Key | Type | Value |
|-----|------|-------|
| group | Text | `repair_team` |
| segments | Text | `horeca,premium` |
| magazine_cards | Text | `hi_home,in_home` |
| brand_name | Text | `Test Brand` |
| email | Text | `test@example.com` |
| data_processing_consent | Text | `true` |
| company_logo | File | (fayl tanlash) |

**Note:** Form-data formatida `segments` va `magazine_cards` vergul bilan ajratilgan string sifatida yuboriladi: `"horeca,premium"`

## Minimal Required Fields (POST)

```json
{
    "group": "repair_team",
    "full_name": "Test User",
    "brand_name": "Test Brand",
    "email": "test@example.com",
    "responsible_person": "John Doe",
    "data_processing_consent": true
}
```

## Example Response (Success)

```json
{
    "id": 1,
    "group": "repair_team",
    "group_display": "Ремонтная бригада",
    "status": "pending",
    "status_display": "Ожидает модерации",
    "full_name": "Test User",
    "brand_name": "Test Brand",
    "email": "test@example.com",
    "segments": ["horeca", "premium"],
    "magazine_cards": ["hi_home", "in_home"],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```
