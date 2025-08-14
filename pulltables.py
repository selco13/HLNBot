import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')

if not CODA_API_TOKEN or not DOC_ID:
    print("Please ensure CODA_API_TOKEN and DOC_ID are set in your .env file.")
    exit(1)

headers = {
    'Authorization': f'Bearer {CODA_API_TOKEN}',
    'Content-Type': 'application/json'
}

url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables'

response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    print("Tables in your Coda document:")
    for table in data.get('items', []):
        print(f"Table Name: {table['name']}, Table ID: {table['id']}")
        # List views for each table
        views_url = table['href'] + '/views'
        views_response = requests.get(views_url, headers=headers)
        if views_response.status_code == 200:
            views_data = views_response.json()
            for view in views_data.get('items', []):
                print(f"  View Name: {view['name']}, View ID: {view['id']}")
        else:
            print(f"  Failed to retrieve views for table {table['name']}.")
else:
    print(f"Failed to retrieve tables. Status Code: {response.status_code}")
    print(f"Response: {response.text}")

