"""
User List API test script
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_user_list_api():
    """Test User List API"""
    print("\n" + "="*80)
    print("USER LIST API TESTS")
    print("="*80)
    
    # 1. Get all users
    print("\n1. Get all users")
    response = requests.get(f"{BASE_URL}/api/v1/accounts/users/")
    print(f"Status: {response.status_code}")
    data = response.json()
    if isinstance(data, dict) and 'results' in data:
        print(f"Total users: {data.get('count', len(data.get('results', [])))}")
        print(f"Users in results: {len(data.get('results', []))}")
    else:
        print(f"Users: {len(data)}")
    
    # 2. Filter by role=designer
    print("\n2. Filter by role=designer")
    response = requests.get(f"{BASE_URL}/api/v1/accounts/users/?role=designer")
    print(f"Status: {response.status_code}")
    data = response.json()
    if isinstance(data, dict) and 'results' in data:
        users = data.get('results', [])
        print(f"Designer users: {len(users)}")
        for user in users[:3]:
            print(f"  - {user.get('full_name')} ({user.get('role')})")
    else:
        print(f"Designer users: {len(data)}")
    
    # 3. Filter by city
    print("\n3. Filter by city=Moscow")
    response = requests.get(f"{BASE_URL}/api/v1/accounts/users/?city=Moscow")
    print(f"Status: {response.status_code}")
    data = response.json()
    if isinstance(data, dict) and 'results' in data:
        users = data.get('results', [])
        print(f"Moscow users: {len(users)}")
        for user in users[:3]:
            print(f"  - {user.get('full_name')} ({user.get('city')})")
    else:
        print(f"Moscow users: {len(data)}")
    
    # 4. Search
    print("\n4. Search 'Test'")
    response = requests.get(f"{BASE_URL}/api/v1/accounts/users/?search=Test")
    print(f"Status: {response.status_code}")
    data = response.json()
    if isinstance(data, dict) and 'results' in data:
        users = data.get('results', [])
        print(f"Found users: {len(users)}")
        for user in users[:3]:
            print(f"  - {user.get('full_name')}")
    else:
        print(f"Found users: {len(data)}")
    
    # 5. Test all roles
    print("\n5. Test all roles")
    for role in ['designer', 'repair', 'supplier', 'media']:
        response = requests.get(f"{BASE_URL}/api/v1/accounts/users/?role={role}")
        data = response.json()
        if isinstance(data, dict) and 'results' in data:
            count = len(data.get('results', []))
        else:
            count = len(data)
        print(f"  {role}: {count} users")
    
    # 6. Test is_active_profile filter
    print("\n6. Test is_active_profile filter")
    response = requests.get(f"{BASE_URL}/api/v1/accounts/users/?is_active_profile=true")
    data = response.json()
    if isinstance(data, dict) and 'results' in data:
        count = len(data.get('results', []))
    else:
        count = len(data)
    print(f"Active profiles: {count}")
    
    print("\n" + "="*80)
    print("Testing completed!")
    print("="*80)

if __name__ == "__main__":
    test_user_list_api()
