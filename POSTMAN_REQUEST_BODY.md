# Postman Request Body - RepairQuestionnaire PUT

## Request Settings

**Method:** `PUT`  
**URL:** `http://127.0.0.1:8000/api/v1/accounts/repair-questionnaires/38/`

## Headers

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY5MjU4MDMyLCJpYXQiOjE3Njg2NTMyMzIsImp0aSI6IjE5ZTc5MGJhMzRjYjQzZTFiYzFhOTRlYjdjM2JhZTJmIiwidXNlcl9pZCI6IjIifQ.IjiwINZUMWbQXL1aeDinyKAFa_k5HvkNTJ2re4hvRUY
Accept: application/json
```

**Note:** `Content-Type: multipart/form-data` - Postman avtomatik qo'shadi, qo'lda qo'shmaslik kerak!

## Body (form-data)

Postman'da **Body** tab'ni oching va **form-data** ni tanlang. Keyin quyidagi fieldlarni qo'shing:

| Key | Type | Value |
|-----|------|-------|
| segments | Text | `business,premium` |
| other_contacts | Text | `sadasdasdas` |
| brand_name | Text | `string` |
| data_processing_consent | Text | `true` |
| business_form | Text | `own_business` |
| cooperation_terms | Text | `string` |
| work_format | Text | `string` |
| telegram_channel | Text | `string` |
| additional_info | Text | `string` |
| designer_supplier_terms | Text | `string` |
| welcome_message | Text | `string` |
| representative_cities | Text | `string` |
| guarantees | Text | `string` |
| work_list | Text | `string` |
| project_timelines | Text | `string` |
| company_logo | File | (bo'sh qoldirish yoki fayl tanlash) |
| phone | Text | `string` |
| vat_payment | Text | `yes` |
| instagram | Text | `string` |
| vk | Text | `string` |
| magazine_cards | Text | `hi_home,in_home` |
| pinterest | Text | `string` |
| website | Text | `https://chatgpt.com/c/6969d8a5-7c88-8331-a749-07872afb6602` |
| full_name | Text | `string` |
| email | Text | `user@example.com` |
| responsible_person | Text | `string` |
| group | Text | `supplier` |

## Qo'shimcha Ma'lumotlar

### Multiple Choice Fields (vergul bilan ajratilgan)

Quyidagi fieldlar vergul bilan ajratilgan qiymatlarni qabul qiladi:
- **segments**: `business,premium` → `["business", "premium"]`
- **magazine_cards**: `hi_home,in_home` → `["hi_home", "in_home"]`

### Valid Choices

**segments** uchun:
- `horeca`
- `business`
- `comfort`
- `premium`
- `medium`
- `economy`

**magazine_cards** uchun:
- `hi_home`
- `in_home`
- `no`
- `other`

**business_form** uchun:
- `own_business`
- `franchise`

**vat_payment** uchun:
- `yes`
- `no`

**group** uchun:
- `repair_team`
- `supplier`
- `media`
- `designer`

## JSON Format (Alternative)

Agar JSON formatida yubormoqchi bo'lsangiz, quyidagi formatni ishlatishingiz mumkin:

```json
{
  "segments": ["business", "premium"],
  "magazine_cards": ["hi_home", "in_home"],
  "other_contacts": [],
  "representative_cities": [],
  "brand_name": "string",
  "data_processing_consent": true,
  "business_form": "own_business",
  "cooperation_terms": "string",
  "work_format": "string",
  "telegram_channel": "string",
  "additional_info": "string",
  "designer_supplier_terms": "string",
  "welcome_message": "string",
  "guarantees": "string",
  "work_list": "string",
  "project_timelines": "string",
  "phone": "string",
  "vat_payment": "yes",
  "instagram": "string",
  "vk": "string",
  "pinterest": "string",
  "website": "https://chatgpt.com/c/6969d8a5-7c88-8331-a749-07872afb6602",
  "full_name": "string",
  "email": "user@example.com",
  "responsible_person": "string",
  "group": "supplier"
}
```

**Note:** JSON formatida yuborish uchun `Content-Type: application/json` header'ni qo'shing va `company_logo` faylini alohida yuborish kerak bo'ladi.
