import os
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
import uvicorn
import os
from faster_whisper import WhisperModel

app = FastAPI()

# Initialize the model (make sure you have the model files)
model = WhisperModel("tiny",device="cpu",compute_type="int8")

# Directory to store recordings
recordings_dir = 'recordings'

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
    # Ensure the recordings directory exists
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    
    # Delete previous recordings
    for filename in os.listdir(recordings_dir):
        file_path = os.path.join(recordings_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    
    file_location = os.path.join(recordings_dir, file.filename)
    with open(file_location, "wb") as f:
        f.write(await file.read())
    
    # Process the audio file
    segments, info = model.transcribe(file_location)
    transcription = ''.join([segment.text for segment in segments])
    
    return {"transcription": transcription}
