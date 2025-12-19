import json
import requests
import time
from urllib.parse import urlparse, parse_qs

# Load credentials
with open('credentials.json', 'r') as f:
    creds = json.load(f)['installed']

# Get authorization URL
auth_url = (f"https://accounts.google.com/o/oauth2/auth?"
            f"client_id={creds['client_id']}&"
            f"redirect_uri={creds['redirect_uris'][0]}&"
            f"scope=https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive.metadata&"
            f"response_type=code&"
            f"access_type=offline&"
            f"prompt=consent")

print("1. Go to this URL:\n", auth_url)
print("2. Authorize the application and paste the code from the redirected URL")

code = input("3. Paste the authorization code here: ")

# Exchange code for token
token_data = {
    'client_id': creds['client_id'],
    'client_secret': creds['client_secret'],
    'code': code,
    'grant_type': 'authorization_code',
    'redirect_uri': creds['redirect_uris'][0]
}

response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
tokens = response.json()

if 'access_token' in tokens:
    final = {
        'access_token': tokens['access_token'],
        'refresh_token': tokens.get('refresh_token'),
        'expiry': time.time() + tokens.get('expires_in', 3600)
    }
    with open('google_drive_token.json', 'w') as f:
        json.dump(final, f, indent=2)
    print("✅ Token saved to google_drive_token.json")
else:
    print("❌ Failed to get token:", tokens)

