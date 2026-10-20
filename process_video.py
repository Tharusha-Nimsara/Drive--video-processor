import os
import subprocess
import math
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# --- CONFIGURATION ---
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
CHUNK_DURATION_SEC = 7200  # 2 hours

def get_gdrive_service():
    """Authenticates using the OAuth Refresh Token."""
    print("Authenticating with Google Drive via OAuth...")
    creds = Credentials(
        token=None,
        refresh_token=os.environ['GCP_REFRESH_TOKEN'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.environ['GCP_CLIENT_ID'],
        client_secret=os.environ['GCP_CLIENT_SECRET']
    )
    return build('drive', 'v3', credentials=creds)

def get_media_duration(filepath):
    """Uses ffprobe to get the duration of the media file in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration', '-of',
        'default=noprint_wrappers=1:nokey=1', filepath
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

def process_and_compress(input_file, output_file, start_time=None, duration=None):
    """Compresses the file based on whether it is audio or video."""
    cmd = ['ffmpeg', '-y']
    
    if start_time is not None:
        cmd.extend(['-ss', str(start_time)])
    if duration is not None:
        cmd.extend(['-t', str(duration)])
        
    cmd.extend(['-i', input_file])
    
    # Detect if file is audio-only based on extension
    is_audio = input_file.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'))
    
    if is_audio:
        # Audio compression: MP3 format, 64k bitrate
        cmd.extend([
            '-c:a', 'libmp3lame',
            '-b:a', '64k'
        ])
    else:
        # Video compression: libx264 video, CRF 28, fast preset, 64k AAC audio
        cmd.extend([
            '-c:v', 'libx264',
            '-crf', '28',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '64k'
        ])
    
    cmd.append(output_file)
    print(f"Running FFmpeg: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def main():
    service = get_gdrive_service()
    
    # List files in the target folder
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()
    files = results.get('files', [])

    if not files:
        print("No files found in the specified Drive folder.")
        return

    for f in files:
        file_id = f['id']
        file_name = f['name']
        
        # Skip previously processed files to prevent infinite loops
        if file_name.startswith("processed_"):
            continue

        print(f"\n--- Processing: {file_name} ---")
        local_filename = f"temp_{file_name}"

        # 1. Download the file
        print("Downloading...")
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(local_filename, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        # 2. Check duration
        duration = get_media_duration(local_filename)
        print(f"Duration: {duration} seconds")

        output_files = []

        # 3. Split if over 2 hours, otherwise just compress
        if duration > CHUNK_DURATION_SEC:
            chunks = math.ceil(duration / CHUNK_DURATION_SEC)
            print(f"File exceeds 2 hours. Splitting into {chunks} parts...")
            for i in range(chunks):
                start = i * CHUNK_DURATION_SEC
                part_name = f"processed_part{i+1}_{file_name}"
                process_and_compress(local_filename, part_name, start_time=start, duration=CHUNK_DURATION_SEC)
                output_files.append(part_name)
        else:
            print("File is under 2 hours. Compressing whole file...")
            out_name = f"processed_{file_name}"
            process_and_compress(local_filename, out_name)
            output_files.append(out_name)

        # 4. Upload the processed files back to the same folder
        for out_file in output_files:
            print(f"Uploading {out_file}...")
            file_metadata = {'name': out_file, 'parents': [FOLDER_ID]}
            media = MediaFileUpload(out_file, resumable=True)
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            os.remove(out_file)

        # 5. Delete the original massive file from Drive
        print(f"Deleting original file '{file_name}' from Drive...")
        service.files().delete(fileId=file_id).execute()
        
        os.remove(local_filename)
        print("Done with this file.")

if __name__ == '__main__':
    main()
                  
