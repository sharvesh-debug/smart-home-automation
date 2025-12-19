#from google_auth_oauthlib.flow import InstalledAppFlow

# Google Drive API scopes
'''
SCOPES = ['https://www.googleapis.com/auth/drive.file']

#def get_drive_token():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json',
        SCOPES
    )
    credentials = flow.run_local_server(port=5000)
    
    # Save token information
    token_data = {
        'access_token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
        'expiry': credentials.expiry.timestamp() if credentials.expiry else None
    }
    print("here is the problem ")
    with open('google_drive_token.json', 'w') as token_file:
        json.dump(token_data, token_file)
    
    print("Google Drive token saved to google_drive_token.json")

if __name__ == '__main__':
    get_drive_token()
    
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import json

def upload_to_drive():
    # Load saved credentials
    with open('google_drive_token.json', 'r') as token_file:
        token_data = json.load(token_file)

    credentials = Credentials(
        token=token_data['access_token'],
        refresh_token=token_data['refresh_token'],
        token_uri=token_data['token_uri'],
        client_id=token_data['client_id'],
        client_secret=token_data['client_secret'],
        scopes=token_data['scopes']
    )

    # Build the Google Drive service
    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': 'example.txt'
    }
    media = MediaFileUpload('example.txt', mimetype='text/plain')

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    print(f"File uploaded to Google Drive with ID: {file.get('id')}")

'''
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_token():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json',
        SCOPES
    )
    credentials = flow.run_local_server(port=5000)  # opens a browser
    token_data = {
        'access_token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
        'expiry': credentials.expiry.timestamp() if credentials.expiry else None
    }
    with open('google_drive_token.json', 'w') as token_file:
        json.dump(token_data, token_file)

    print("Google Drive token saved to google_drive_token.json")

if __name__ == '__main__':
    get_drive_token()

