import requests
import random

def get_random_user_agent():
    """Generate a random user agent"""
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/{random.randint(530, 537)}.{random.randint(30, 37)} (KHTML, like Gecko) Chrome/{random.randint(80, 105)}.0.{random.randint(3000, 4500)}.{random.randint(60, 125)} Safari/{random.randint(530, 537)}.{random.randint(30, 36)}"

def get_session_token_requests():
    """
    Get session token via direct HTTP requests - no browser needed!
    """
    try:
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        print("Attempting to get session token via HTTP...")
        response = requests.get('https://api.spotidownloader.com/session', headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('token'):
                print(f"SUCCESS: Got token via HTTP: {data['token'][:20]}...")
                return data['token']
            else:
                print("No token in response")
        
        print(f"HTTP method failed: Status {response.status_code}")
        return None
        
    except Exception as e:
        print(f"HTTP method error: {e}")
        return None

def get_token():
    """Main token function for server use"""
    return get_session_token_requests()

if __name__ == "__main__":
    token = get_token()
    if token:
        print(f"Token: {token}")
    else:
        print("Failed to get token")