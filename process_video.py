import os
import json
import subprocess
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# --- 1. Authenticate ---
creds_json = os.environ.get('GCP_CREDENTIALS')
input_folder_id = os.environ.get('DRIVE_FOLDER_ID')
processed_folder_id = os.environ.get('PROCESSED_FOLDER_ID')

creds_dict = json.loads(creds_json)
creds = service_account.Credentials.from_service_account_info(
    creds_dict, scopes=['https://www.googleapis.com/auth/drive'] # Requires full drive scope to delete files
)
drive_service = build('drive', 'v3', credentials=creds)

# --- 2. Helper Functions ---
def get_duration(file_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try: return float(result.stdout.strip())
    except ValueError: return 0.0

def download_file(file_id, file_name):
    print(f"Downloading {file_name}...")
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: status, done = downloader.next_chunk()

def upload_file(file_path, parent_folder_id):
    print(f"Uploading {file_path} to organized folder...")
    file_metadata = {'name': os.path.basename(file_path), 'parents': [parent_folder_id]}
    media = MediaFileUpload(file_path, resumable=True)
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

# --- 3. Main Logic ---
results = drive_service.files().list(
    q=f"'{input_folder_id}' in parents and trashed=false",
    fields="files(id, name)"
).execute()
files = results.get('files', [])

if not files:
    print("No new videos to process today.")
    exit()

for f in files:
    file_id = f['id']
    original_name = f['name'].replace(" ", "_")
    
    download_file(file_id, original_name)
    duration = get_duration(original_name)
    files_to_compress = []
    
    # Rule 1: Split if > 2 hours
    if duration > 7200:
        print(f"Video > 2 hours. Splitting...")
        subprocess.run([
            'ffmpeg', '-i', original_name, '-c', 'copy', '-map', '0', 
            '-segment_time', '02:00:00', '-f', 'segment', 
            '-reset_timestamps', '1', f"split_%03d_{original_name}"
        ], check=True)
        for item in os.listdir('.'):
            if item.startswith("split_") and item.endswith(original_name):
                files_to_compress.append(item)
    else:
        files_to_compress.append(original_name)
        
    # Rule 2: Compress EVERYTHING to save space
    for target_file in files_to_compress:
        print(f"Compressing {target_file} to save space...")
        compressed_name = f"compressed_{target_file}"
        subprocess.run([
            'ffmpeg', '-i', target_file, '-vcodec', 'libx265', 
            '-preset', 'veryfast', '-crf', '28', compressed_name
        ], check=True)
        
        # Upload to the new "Processed Videos" folder
        upload_file(compressed_name, processed_folder_id)
        
    # Rule 3: PERMANENTLY DELETE original file
    print(f"Permanently deleting original {original_name} to free up space...")
    try:
        drive_service.files().delete(fileId=file_id).execute()
        print(f"Successfully deleted {original_name}.")
    except Exception as e:
        print(f"Failed to delete {original_name}. Error: {e}")

print("Daily 6:00 PM processing complete!")
