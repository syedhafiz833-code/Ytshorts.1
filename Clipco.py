import streamlit as st
import os
import re
from pytube import YouTube
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import tempfile
import base64

# YouTube API setup
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

@st.cache_data
def download_video(url):
    with tempfile.TemporaryDirectory() as temp_dir:
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()
        file_path = stream.download(temp_dir)
        return file_path

@st.cache_data
def analyze_for_clips(video_path, subtitles_path=None):
    clip = VideoFileClip(video_path)
    audio = clip.audio
    volumes = [abs(sample) for sample in audio.to_soundarray(fps=44100).flatten()]
    avg_volume = sum(volumes) / len(volumes)
    peaks = [i for i, v in enumerate(volumes) if v > avg_volume * 1.5]
    
    engaging_keywords = ["amazing", "shocking", "epic", "must-see", "wow"]
    engaging_times = []
    if subtitles_path:
        with open(subtitles_path, 'r') as f:
            subs = f.read()
            for keyword in engaging_keywords:
                matches = re.finditer(keyword, subs, re.IGNORECASE)
                for match in matches:
                    engaging_times.append(match.start() / len(subs) * clip.duration)
    
    all_times = sorted(set(peaks[:len(peaks)//100] + engaging_times))
    clip_starts = all_times[:5] if len(all_times) >= 5 else all_times
    return clip_starts

@st.cache_data
def generate_short_clips(video_path, clip_starts):
    with tempfile.TemporaryDirectory() as temp_dir:
        clip_files = []
        full_clip = VideoFileClip(video_path)
        progress_bar = st.progress(0)
        for i, start in enumerate(clip_starts):
            end = min(start + 30, full_clip.duration)
            subclip = full_clip.subclip(start, end)
            text = TextClip("Watch the FULL VIDEO! 🔥", fontsize=70, color='white', bg_color='black').set_position('center').set_duration(subclip.duration)
            final_clip = CompositeVideoClip([subclip, text])
            output_file = os.path.join(temp_dir, f"short_{i+1}.mp4")
            final_clip.write_videofile(output_file, fps=24, codec="libx264", verbose=False, logger=None)
            clip_files.append(output_file)
            progress_bar.progress((i+1) / len(clip_starts))
        return clip_files

def authenticate_youtube(client_secrets_file):
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    credentials = flow.run_local_server(port=0)
    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

def upload_to_youtube(youtube, file_path, title, description, tags):
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "public",
                "madeForKids": False
            }
        },
        media_body=MediaFileUpload(file_path)
    )
    response = request.execute()
    return response['id']

def get_binary_file_downloader_html(bin_file, file_label='File'):
    with open(bin_file, 'rb') as f:
        data = f.read()
    bin_str = base64.b64encode(data).decode()
    href = f'<a href="data:application/octet-stream;base64,{bin_str}" download="{os.path.basename(bin_file)}">{file_label}</a>'
    return href

# Streamlit UI
st.title("YouTube Auto-Clip Generator for Shorts")
st.write("Upload a YouTube link to generate engaging short clips and boost engagement!")

youtube_url = st.text_input("Enter YouTube Video URL:")
subtitles_file = st.file_uploader("Optional: Upload subtitles (.vtt) for better analysis", type=["vtt"])

if st.button("Generate Clips"):
    if not youtube_url:
        st.error("Please enter a YouTube URL.")
    else:
        with st.spinner("Downloading video..."):
            try:
                video_path = download_video(youtube_url)
                st.success("Video downloaded!")
            except Exception as e:
                st.error(f"Error downloading video: {e}")
                st.stop()
        
        with st.spinner("Analyzing for engaging clips..."):
            subtitles_path = None
            if subtitles_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".vtt") as temp_file:
                    temp_file.write(subtitles_file.read())
                    subtitles_path = temp_file.name
            clip_starts = analyze_for_clips(video_path, subtitles_path)
            if not clip_starts:
                st.warning("No engaging clips detected. Try a different video or subtitles.")
                st.stop()
            st.success(f"Found {len(clip_starts)} potential clips!")
        
        with st.spinner("Generating short clips..."):
            clip_files = generate_short_clips(video_path, clip_starts)
            st.success("Clips generated!")
        
        st.subheader("Generated Clips:")
        for i, clip_file in enumerate(clip_files):
            st.video(clip_file)
            st.markdown(get_binary_file_downloader_html(clip_file, f"Download Short {i+1}"), unsafe_allow_html=True)

# YouTube Upload Section
st.subheader("Upload Clips to YouTube (Optional)")
client_secrets = st.file_uploader("Upload your client_secrets.json (from Google Cloud Console)", type=["json"])
if client_secrets and st.button("Authenticate and Upload Clips"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
        temp_file.write(client_secrets.read())
        secrets_path = temp_file.name
    
    try:
        youtube = authenticate_youtube(secrets_path)
        st.success("Authenticated! Uploading clips...")
        for i, clip_file in enumerate(clip_files):
            title = f"Engaging Clip {i+1} from Original Video! #Shorts"
            description = "Check out the full video for more! Link in bio."
            tags = ["shorts", "viral", "engaging", "youtube"]
            video_id = upload_to_youtube(youtube, clip_file, title, description, tags)
            st.write(f"Uploaded Short {i+1}: https://www.youtube.com/watch?v={video_id}")
        st.success("All uploads complete!")
    except Exception as e:
        st.error(f"Upload failed: {e}")
