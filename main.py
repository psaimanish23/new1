#
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
#

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
import uvicorn
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from faster_whisper import WhisperModel

app = FastAPI()

# Initialize the model (make sure you have the model files)
model = WhisperModel('base', device="cpu", compute_type="int8")

# Azure Blob Storage configuration
connect_str = "DefaultEndpointsProtocol=https;AccountName=manishdemostorage;AccountKey="
container_name = "demo-container"

blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_client = blob_service_client.get_container_client(container_name)

# Directory to store temporary recordings
recordings_dir = os.path.join(os.getcwd(), 'recordings')

@app.get("/")
def main():
    html_content = """
    <html>
        <head>
            <title>Record Audio</title>
        </head>
        <body>
            <h1>Record a 5-second Audio</h1>
            <button onclick="startRecording()">Start Recording</button>
            <button onclick="stopRecording()">Stop Recording</button>
            <br><br>
            <audio id="audio" controls></audio>
            <br><br>
            <textarea id="transcription" rows="4" cols="50" readonly></textarea>
            <script>
                let mediaRecorder;
                let audioChunks = [];

                function startRecording() {
                    document.getElementById('transcription').value = ''; // Clear transcription
                    audioChunks = []; // Clear audio chunks
                    navigator.mediaDevices.getUserMedia({ audio: true })
                        .then(stream => {
                            mediaRecorder = new MediaRecorder(stream);
                            mediaRecorder.start();
                            mediaRecorder.ondataavailable = event => {
                                audioChunks.push(event.data);
                            };
                            mediaRecorder.onstop = async () => {
                                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                                const audioUrl = URL.createObjectURL(audioBlob);
                                const audio = document.getElementById('audio');
                                audio.src = audioUrl;
                                const formData = new FormData();
                                formData.append('file', audioBlob, 'recording.wav');
                                const response = await fetch('/upload', { method: 'POST', body: formData });
                                const result = await response.json();
                                document.getElementById('transcription').value = result.transcription;
                            };
                            setTimeout(() => {
                                mediaRecorder.stop();
                            }, 5000); // Stop after 5 seconds
                        });
                }

                function stopRecording() {
                    mediaRecorder.stop();
                }
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Ensure the container exists
    if not container_client.exists():
        container_client.create_container()

    # Ensure the recordings directory exists
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)

    # Save the uploaded file locally
    file_location = os.path.join(recordings_dir, file.filename)
    with open(file_location, "wb") as f:
        f.write(await file.read())

    # Upload the file to Azure Blob Storage
    blob_client = container_client.get_blob_client(file.filename)
    with open(file_location, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    # Process the audio file (download it first)
    download_file_path = os.path.join(recordings_dir, file.filename)
    with open(download_file_path, "wb") as download_file:
        download_file.write(blob_client.download_blob().readall())

    # Process the audio file
    segments, info = model.transcribe(download_file_path)
    transcription = ''.join([segment.text for segment in segments])

    # Delete the local temporary file
    os.remove(download_file_path)

    return {"transcription": transcription}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
