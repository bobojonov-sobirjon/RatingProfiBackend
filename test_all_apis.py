"""
Barcha API'larni test qilish scripti
Access token bilan barcha endpoint'larni tekshiradi
"""
import requests
import json
from datetime import datetime

# Base URL
BASE_URL = "http://localhost:8000"

# Access Token
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY3Mzc1MzgwLCJpYXQiOjE3NjY3NzA1ODAsImp0aSI6IjljYjdmNWJmMjJkYTQwYmRhZDRmOTBlZDgxYjMzZDg0IiwidXNlcl9pZCI6IjMifQ.ElU8ANO1oDDfx2ctfDLD-tszV5tg3Ha1IAsEYJp_I4A"

# Headers
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# Test natijalari
results = {
    "success": [],
    "failed": [],
    "skipped": []
}

def test_api(method, url, data=None, description=""):
    """API'ni test qilish"""
    try:
        print(f"\n{'='*80}")
        print(f"Testing: {description}")
        print(f"Method: {method} | URL: {url}")
        
        if data:
            print(f"Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data if data else None,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        try:
            response_data = response.json()
            print(f"Response: {json.dumps(response_data, indent=2, ensure_ascii=False)[:500]}")
        except:
            print(f"Response (text): {response.text[:500]}")
        
        if response.status_code in [200, 201, 204]:
            results["success"].append({
                "method": method,
                "url": url,
                "status": response.status_code,
                "description": description
            })
            print(f"[OK] SUCCESS")
        else:
            results["failed"].append({
                "method": method,
                "url": url,
                "status": response.status_code,
                "description": description,
                "error": response.text[:200]
            })
            print(f"[FAIL] FAILED")
            
    except requests.exceptions.ConnectionError:
        results["skipped"].append({
            "method": method,
            "url": url,
            "description": description,
            "error": "Server ishlamayapti (ConnectionError)"
        })
        print(f"[SKIP] SKIPPED - Server ishlamayapti")
    except Exception as e:
        results["failed"].append({
            "method": method,
            "url": url,
            "description": description,
            "error": str(e)
        })
        print(f"[ERROR] ERROR: {str(e)}")

# ==================== ACCOUNTS API ====================

print("\n" + "="*80)
print("ACCOUNTS API TESTS")
print("="*80)

# 1. Profile
test_api("GET", f"{BASE_URL}/api/v1/accounts/profile/", description="Get User Profile")

# 2. Update Profile
test_api("PATCH", f"{BASE_URL}/api/v1/accounts/profile/", 
         data={"first_name": "Test", "last_name": "User"}, 
         description="Update User Profile")

# 3. User Roles
test_api("GET", f"{BASE_URL}/api/v1/accounts/roles/", description="Get User Roles")

# 4. All Questionnaires List
test_api("GET", f"{BASE_URL}/api/v1/accounts/questionnaires/all/", description="Get All Questionnaires")

# 5. Designer Questionnaires
test_api("GET", f"{BASE_URL}/api/v1/accounts/questionnaires/", description="Get Designer Questionnaires List")
test_api("GET", f"{BASE_URL}/api/v1/accounts/questionnaires/filter-choices/", description="Get Designer Filter Choices")

# 6. Create Designer Questionnaire
designer_data = {
    "full_name": "Test Designer API",
    "phone": "+79991234599",
    "email": "testdesigner@example.com",
    "city": "Moscow",
    "group": "design",
    "status": "draft"
}
test_api("POST", f"{BASE_URL}/api/v1/accounts/questionnaires/", 
         data=designer_data, 
         description="Create Designer Questionnaire")

# Get created questionnaire ID (we'll use a test ID)
test_api("GET", f"{BASE_URL}/api/v1/accounts/questionnaires/1/", description="Get Designer Questionnaire Detail")

# 7. Repair Questionnaires
test_api("GET", f"{BASE_URL}/api/v1/accounts/repair-questionnaires/", description="Get Repair Questionnaires List")
test_api("GET", f"{BASE_URL}/api/v1/accounts/repair-questionnaires/filter-choices/", description="Get Repair Filter Choices")

# Create Repair Questionnaire
repair_data = {
    "full_name": "Test Repair API",
    "phone": "+79991234598",
    "brand_name": "Test Repair Brand",
    "email": "testrepair@example.com",
    "responsible_person": "Test Person",
    "group": "repair",
    "status": "draft"
}
test_api("POST", f"{BASE_URL}/api/v1/accounts/repair-questionnaires/", 
         data=repair_data, 
         description="Create Repair Questionnaire")

# 8. Supplier Questionnaires
test_api("GET", f"{BASE_URL}/api/v1/accounts/supplier-questionnaires/", description="Get Supplier Questionnaires List")
test_api("GET", f"{BASE_URL}/api/v1/accounts/supplier-questionnaires/filter-choices/", description="Get Supplier Filter Choices")

# Create Supplier Questionnaire
supplier_data = {
    "full_name": "Test Supplier API",
    "phone": "+79991234597",
    "brand_name": "Test Supplier Brand",
    "email": "testsupplier@example.com",
    "responsible_person": "Test Person",
    "group": "supplier",
    "status": "draft"
}
test_api("POST", f"{BASE_URL}/api/v1/accounts/supplier-questionnaires/", 
         data=supplier_data, 
         description="Create Supplier Questionnaire")

# 9. Media Questionnaires
test_api("GET", f"{BASE_URL}/api/v1/accounts/media-questionnaires/", description="Get Media Questionnaires List")

# Create Media Questionnaire
media_data = {
    "full_name": "Test Media API",
    "phone": "+79991234596",
    "brand_name": "Test Media Brand",
    "email": "testmedia@example.com",
    "responsible_person": "Test Person",
    "group": "media",
    "status": "draft",
    "activity_description": "Test activity description",
    "welcome_message": "Test welcome message",
    "cooperation_terms": "Test cooperation terms",
    "segments": ["premium"]
}
test_api("POST", f"{BASE_URL}/api/v1/accounts/media-questionnaires/", 
         data=media_data, 
         description="Create Media Questionnaire")

# ==================== EVENTS API ====================

print("\n" + "="*80)
print("EVENTS API TESTS")
print("="*80)

# 1. Upcoming Events List
test_api("GET", f"{BASE_URL}/api/v1/events/upcoming-events/", description="Get Upcoming Events List")

# 2. Create Upcoming Event
from datetime import datetime, timedelta
event_data = {
    "organization_name": "Test Event Organization",
    "event_type": "training",
    "announcement": "Test announcement for API testing",
    "event_date": (datetime.now() + timedelta(days=7)).isoformat(),
    "event_location": "Test Location, Moscow",
    "city": "Moscow",
    "registration_phone": "+79991234567",
    "about_event": "This is a test event created via API",
    "status": "draft"
}
test_api("POST", f"{BASE_URL}/api/v1/events/upcoming-events/", 
         data=event_data, 
         description="Create Upcoming Event")

# 3. Get Event Detail
test_api("GET", f"{BASE_URL}/api/v1/events/upcoming-events/1/", description="Get Upcoming Event Detail")

# 4. Rating Page
test_api("GET", f"{BASE_URL}/api/v1/events/ratings/", description="Get Rating Page")

# 5. Reviews Page
test_api("GET", f"{BASE_URL}/api/v1/events/reviews/", description="Get Reviews Page")

# ==================== RATINGS API ====================

print("\n" + "="*80)
print("RATINGS API TESTS")
print("="*80)

# 1. All Questionnaire Ratings
test_api("GET", f"{BASE_URL}/api/v1/ratings/questionnaire-ratings/all/", description="Get All Questionnaire Ratings")

# 2. Create Questionnaire Rating
rating_data = {
    "role": "Дизайн",
    "id_questionnaire": 1,
    "is_positive": True,
    "is_constructive": False,
    "text": "Great designer! Test review via API"
}
test_api("POST", f"{BASE_URL}/api/v1/ratings/questionnaire-ratings/", 
         data=rating_data, 
         description="Create Questionnaire Rating")

# 3. Get Rating Detail (we'll use ID 1, but it might not exist)
test_api("GET", f"{BASE_URL}/api/v1/ratings/questionnaire-ratings/1/", description="Get Questionnaire Rating Detail")

# ==================== SUMMARY ====================

print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)
print(f"\n[OK] SUCCESS: {len(results['success'])}")
print(f"[FAIL] FAILED: {len(results['failed'])}")
print(f"[SKIP] SKIPPED: {len(results['skipped'])}")
print(f"\nTotal Tests: {len(results['success']) + len(results['failed']) + len(results['skipped'])}")

if results['failed']:
    print("\n" + "="*80)
    print("FAILED TESTS:")
    print("="*80)
    for fail in results['failed']:
        print(f"\n[FAIL] {fail['method']} {fail['url']}")
        print(f"   Status: {fail['status']}")
        print(f"   Description: {fail['description']}")
        print(f"   Error: {fail.get('error', 'N/A')[:200]}")

if results['skipped']:
    print("\n" + "="*80)
    print("SKIPPED TESTS:")
    print("="*80)
    for skip in results['skipped']:
        print(f"\n[SKIP] {skip['method']} {skip['url']}")
        print(f"   Description: {skip['description']}")
        print(f"   Reason: {skip.get('error', 'N/A')}")

print("\n" + "="*80)
print("Testing completed!")
print("="*80)
