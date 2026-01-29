# Questionnaire GET filters → Model fields (FilterChoicesView va ListView)

Har bir questionnaire modeli uchun: **query parametr (filter)** → **qaysi model field** bo‘yicha tekshiriladi.

---

## 1. DesignerQuestionnaire

**FilterChoicesView:** `GET /api/v1/accounts/questionnaires/filter-choices/`  
Qaytaradi: `categories`, `cities`, `segments`, `property_purposes`, `object_areas`, `cost_per_sqm_options`, `experience_options`.

**ListView GET:** `GET /api/v1/accounts/questionnaires/`

| Query parametr | Model field | Izoh |
|----------------|-------------|------|
| `group` | `group` | CharField, aniq moslik |
| `categories` yoki `category` | `categories` | JSONField, `__contains` (ro‘yxat) |
| `city` | `city`, `work_cities`, `cooperation_terms` | Maxsus: "По всей России", "ЮФО", "Любые города онлайн" |
| `segment` | `segments` | JSONField, `__contains` |
| `property_purpose` | `purpose_of_property` | JSONField, `__contains` |
| `object_area` | `area_of_object` (IntegerField), `service_packages_description` | up_to_10m2→area_of_object≤10; houses→text qidiruv |
| `cost_per_sqm` | `cost_per_m2` (IntegerField), `service_packages_description` | up_to_1500→cost_per_m2≤1500; over_4000→cost_per_m2≥4000 |
| `experience` | `experience` (IntegerField), `welcome_message`, `additional_info` | beginner=0, up_to_2_years=1, 2_5_years=2, 5_10_years=3, over_10_years=4 |
| `search` | `full_name` | icontains |
| `ordering` | — | Sortirovka |
| `limit`, `offset` | — | Paginatsiya |

---

## 2. RepairQuestionnaire

**FilterChoicesView:** `GET /api/v1/accounts/repair-questionnaires/filter-choices/`  
Qaytaradi: `categories`, `cities`, `segments`, `vat_payments`, `magazine_cards`, `execution_speeds`, `cooperation_terms_options`.

**ListView GET:** `GET /api/v1/accounts/repair-questionnaires/`

| Query parametr | Model field | Izoh |
|----------------|-------------|------|
| `group` | `work_list` (matn qidiruv) | turnkey, rough_works, finishing_works, plumbing_tiles, floor, walls, rooms_turnkey, electrical → work_list ichida qidiruv |
| `categories` yoki `category` | `categories` | JSONField, `__contains` |
| `city` | `representative_cities`, `cooperation_terms` | Maxsus variantlar ham bor |
| `segment` | `segments` | JSONField, `__contains` |
| `vat_payment` | `vat_payment` | CharField, aniq moslik |
| `magazine_cards` | `magazine_cards` | JSONField, `__contains` (har bir card uchun Q) |
| `execution_speed` | `speed_of_execution` | CharField, aniq moslik (advance_booking, quick_start, not_important) |
| `cooperation_terms` | `cooperation_terms` | TextField, icontains (5%, 10% va hokazo) |
| `property_purpose` | `work_list` | icontains |
| `object_area` | `project_timelines` | icontains |
| `cost_per_sqm` | `work_format`, `guarantees` | icontains |
| `experience` | `welcome_message`, `additional_info` | icontains |
| `business_form` | `business_form` | CharField, aniq moslik |
| `search` | `full_name`, `brand_name` | icontains |
| `ordering`, `limit`, `offset` | — | Sortirovka va paginatsiya |

---

## 3. SupplierQuestionnaire

**FilterChoicesView:** `GET /api/v1/accounts/supplier-questionnaires/filter-choices/`  
Qaytaradi: `categories`, `cities`, `segments`, `vat_payments`, `magazine_cards`, `execution_speeds`, `cooperation_terms_options`.

**ListView GET:** `GET /api/v1/accounts/supplier-questionnaires/`

| Query parametr | Model field | Izoh |
|----------------|-------------|------|
| `group` | `product_assortment` (matn qidiruv) | rough_materials, finishing_materials, soft_furniture, cabinet_furniture, appliances, decor → product_assortment ichida qidiruv |
| `categories` yoki `category` | `categories` | JSONField, `__contains` |
| `city` | `representative_cities`, `cooperation_terms` | Maxsus variantlar ham bor |
| `segment` | `segments` | JSONField, `__contains` |
| `vat_payment` | `vat_payment` | CharField, aniq moslik |
| `magazine_cards` | `magazine_cards` | JSONField, `__contains` |
| `execution_speed` | `speed_of_execution` | CharField, aniq moslik (in_stock, up_to_2_weeks, up_to_1_month, up_to_3_months, not_important) |
| `cooperation_terms` | `cooperation_terms` | TextField, icontains (10%, 20%, 30%) |
| `business_form` | `business_form` | CharField, aniq moslik |
| `search` | `full_name`, `brand_name` | icontains |
| `ordering`, `limit`, `offset` | — | Sortirovka va paginatsiya |

---

## Qisqacha

- **DesignerQuestionnaire:** `categories` → `categories` (JSONField); `property_purpose` → `purpose_of_property`; `object_area` → `area_of_object` (yoki text); `cost_per_sqm` → `cost_per_m2`; `experience` → `experience` (IntegerField yoki text).
- **RepairQuestionnaire:** `categories` → `categories` (JSONField); `execution_speed` → `speed_of_execution` (CharField).
- **SupplierQuestionnaire:** `categories` → `categories` (JSONField); `execution_speed` → `speed_of_execution` (CharField).

FilterChoicesView har bir model uchun filter variantlarini qaytaradi; ListView GET shu parametrlar orqali yuqoridagi modell fieldlariga filter qo‘llaydi.
