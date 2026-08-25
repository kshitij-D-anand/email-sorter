import base64
import json
import os.path
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_SECRET_FILE = 'credentials.json'

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def extract_body(payload):
    body_text = ""

    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                body_text += extract_body(part)
    else:
        data = payload.get('body', {}).get('data', '')
        if data:
            body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    return body_text.strip()

def sanitize_filename(name):
    """Replaces spaces and invalid filename characters with underscores."""
    return re.sub(r'[\\/*?:"<>| ]+', '_', name).strip('_')

def get_emails_for_label_id(service, label_id, label_name):
    messages = []
    page_token = None
    
    # Paginate to fetch ALL message references under this label
    while True:
        response = service.users().messages().list(
            userId='me',
            labelIds=[label_id],
            pageToken=page_token
        ).execute()

        messages.extend(response.get('messages', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    print(f"--> Found {len(messages)} email(s) for label '{label_name}'. Extracting...")

    extracted_emails = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId='me',
            id=msg_ref['id'],
            format='full'
        ).execute()

        headers = msg['payload'].get('headers', [])
        
        subject = "No Subject"
        sender = "Unknown"
        date = "Unknown Date"

        for h in headers:
            name = h['name'].lower()
            if name == 'subject':
                subject = h['value']
            elif name == 'from':
                sender = h['value']
            elif name == 'date':
                date = h['value']

        body = extract_body(msg['payload'])

        extracted_emails.append({
            'id': msg['id'],
            'sender': sender,
            'date': date,
            'subject': subject,
            'body': body
        })

    return extracted_emails

def export_all_custom_labels():
    service = get_gmail_service()
    
    # 1. Get all labels in the account
    labels_response = service.users().labels().list(userId='me').execute()
    all_labels = labels_response.get('labels', [])

    # 2. Filter for custom user labels only
    user_labels = [l for l in all_labels if l.get('type') == 'user']

    print(f"Found {len(user_labels)} custom user labels.\n")

    # 3. Loop through each user label and export to a separate JSON file
    for label in user_labels:
        label_name = label['name']
        label_id = label['id']

        # Generate a safe filename (e.g., "Lost_and_Found.json")
        filename = f"{sanitize_filename(label_name)}.json"
        
        print(f"Processing label: '{label_name}'")
        emails = get_emails_for_label_id(service, label_id, label_name)

        data_structure = {
            "target_label": label_name,
            "total_count": len(emails),
            "emails": emails
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data_structure, f, indent=4, ensure_ascii=False)

        print(f"Saved to '{filename}'!\n" + "-" * 40)

if __name__ == '__main__':
    export_all_custom_labels()
