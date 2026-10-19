import subprocess
import json

def get_video_duration(file_path):
    # Use ffprobe to get the exact duration of the video in seconds
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration', '-of',
        'default=noprint_wrappers=1:nokey=1', file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout)

def process_video(input_file):
    duration_seconds = get_video_duration(input_file)
    two_hours_in_seconds = 7200
    
    if duration_seconds > two_hours_in_seconds:
        print(f"File is {duration_seconds/3600:.2f} hours long. Splitting into 2-hour segments...")
        
        # Run the FFmpeg segment command
        split_cmd = [
            'ffmpeg', '-i', input_file, 
            '-c', 'copy', 
            '-map', '0', 
            '-segment_time', '02:00:00', 
            '-f', 'segment', 
            '-reset_timestamps', '1',
            'output_part_%03d.mp4'
        ]
        
        subprocess.run(split_cmd, check=True)
        print("Splitting complete. You can now upload the 'output_part_xxx.mp4' files.")
        
        # Note: You will need to write a small loop here to find all files starting 
        # with 'output_part_' and upload them back to Google Drive using drive_service.
        
    else:
        print("File is under 2 hours. Proceeding with standard compression if needed.")
        # Add your 200MB compression logic here
      
