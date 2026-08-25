import json
from email_sorter import get_gmail_service

# Standard Gmail system labels to ignore
SYSTEM_LABELS = {
    'INBOX', 'UNREAD', 'IMPORTANT', 'SENT', 'DRAFT', 
    'SPAM', 'TRASH', 'STARRED', 'CHAT'
}

def sync_user_labels():
    service = get_gmail_service()
    
    # Fetch all labels from Gmail
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])

    user_labels = {}

    for label in labels:
        label_id = label['id']
        label_name = label['name']

        # Skip Gmail system labels and category smart-labels
        if label_id in SYSTEM_LABELS or label_id.startswith('CATEGORY_'):
            continue

        user_labels[label_name] = label_id

    # Save to labels.json
    with open('labels.json', 'w') as f:
        json.dump(user_labels, f, indent=4)

    print(f"Successfully synced {len(user_labels)} custom labels to labels.json:")
    print(json.dumps(user_labels, indent=2))

if __name__ == '__main__':
    sync_user_labels()