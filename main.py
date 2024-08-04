import os
#
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
#


from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
import uvicorn
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from faster_whisper import WhisperModel
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from io import BytesIO

app = FastAPI()

# Initialize the model (make sure you have the model files)
model = WhisperModel('base', device="cpu", compute_type="int8")

# Azure Key Vault configuration
key_vault_url = "https://storagekvd.vault.azure.net/"
secret_name = "connectStr"

# Retrieve the secret from Azure Key Vault
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_url, credential=credential)
retrieved_secret = secret_client.get_secret(secret_name)
connect_str = retrieved_secret.value

# Azure Blob Storage configuration
container_name = "demo-container"

blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_client = blob_service_client.get_container_client(container_name)

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

    # Read the uploaded file in-memory
    file_data = await file.read()

    # Upload the file directly to Azure Blob Storage
    blob_client = container_client.get_blob_client(file.filename)
    blob_client.upload_blob(file_data, overwrite=True)

    # Download the file from Azure Blob Storage to process it
    download_stream = blob_client.download_blob()
    audio_data = download_stream.readall()

    # Process the audio file using BytesIO
    audio_file = BytesIO(audio_data)
    segments, info = model.transcribe(audio_file)
    transcription = ''.join([segment.text for segment in segments])

    # Delete the blob from Azure Blob Storage
    blob_client.delete_blob()

    return {"transcription": transcription}
