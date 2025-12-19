#!/usr/bin/env python3
"""
Google Drive Token Generator
Run this script once to generate the google_drive_token.json file
"""

import json
import time
import requests

def generate_token():
    # Load your credentials
    try:
        with open('credentials.json', 'r') as f:
            creds = json.load(f)['installed']
    except FileNotFoundError:
        print("ERROR: credentials.json not found!")
        print("Please download it from Google Cloud Console and place it in this directory")
        return False
    except KeyError:
        print("ERROR: Invalid credentials.json format")
        return False
    
    # Get authorization URL
    auth_url = (f"https://accounts.google.com/o/oauth2/auth?"
               f"client_id={creds['client_id']}&"
               f"redirect_uri={creds['redirect_uris'][0]}&"
               f"scope=https://www.googleapis.com/auth/drive.file&"
               f"response_type=code&"
               f"access_type=offline&"
               f"prompt=consent")
    
    print("\n" + "="*60)
    print("GOOGLE DRIVE TOKEN SETUP")
    print("="*60)
    print("\n1. Open this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("2. Sign in with your Google account")
    print("3. Grant permissions to the application")
    print("4. You'll be redirected to a URL like:")
    print("   http://localhost:8080/?code=XXXXXXXX&scope=...")
    print("5. Copy the 'code' parameter value from the URL")
    print("\n" + "-"*60)
    
    auth_code = input("\nEnter the authorization code: ").strip()
    
    if not auth_code:
        print("No code entered. Exiting.")
        return False
    
    print("\nExchanging code for tokens...")
    
    # Exchange code for tokens
    token_data = {
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': creds['redirect_uris'][0]
    }
    
    try:
        response = requests.post('https://oauth2.googleapis.com/token', data=token_data, timeout=10)
        response.raise_for_status()
        tokens = response.json()
        
        if 'error' in tokens:
            print(f"ERROR: {tokens['error']} - {tokens.get('error_description', '')}")
            return False
        
        # Save tokens
        token_file = {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token'),
            'expiry': time.time() + tokens.get('expires_in', 3600)
        }
        
        with open('google_drive_token.json', 'w') as f:
            json.dump(token_file, f, indent=2)
        
        print("\n" + "="*60)
        print("SUCCESS! Token saved to google_drive_token.json")
        print("="*60)
        print("\nYour camera will now be able to upload videos to Google Drive!")
        print("You can now run your app.py")
        
        return True
        
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    generate_token()
