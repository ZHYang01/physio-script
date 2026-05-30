# Physio Script

Real-time voice-to-clinical-notes for physiotherapy practice. Record patient conversations, transcribe with Whisper AI, and generate structured SOAP notes using local Ollama models.

## Features

- **Real-time recording** - Continuous microphone capture with chunked processing
- **Local transcription** - faster-whisper (large-v3-turbo) runs fully offline — no audio leaves your machine
- **SOAP note generation** - Local Ollama LLM creates structured clinical notes
- **Cliniko integration** - Direct patient search and treatment note creation
- **Clipboard support** - One-click copy for manual paste into any system

## Prerequisites

1. **Python 3.10+**
2. **Ollama** - Install at https://ollama.ai
   ```bash
   ollama pull llama3
   ```
3. **PyAudio dependencies** (macOS):
   ```bash
   brew install portaudio
   ```
4. **faster-whisper** - Model downloads automatically on first launch (~1.6 GB for large-v3-turbo)

## Setup

1. **Clone and enter the project:**
   ```bash
   cd "Physio Script"
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   ```
    Edit `.env` with your settings:
    ```
    WHISPER_MODEL=large-v3-turbo
    CLINIKO_API_KEY=your-cliniko-key  # Optional
    CLINIKO_SHARD=au1                 # Your Cliniko region
    CLINIKO_EMAIL=you@example.com
    OLLAMA_MODEL=llama3
    ```

5. **Run the application:**
   ```bash
   python main.py
   ```

## Usage

1. **Start Ollama** (in a separate terminal):
   ```bash
   ollama serve
   ```

2. **Launch Physio Script:**
   ```bash
   python main.py
   ```

3. **Record a session:**
   - Click **Start Recording** to begin capturing audio
   - Speak with your patient as normal
   - Click **Stop Recording** when the session ends
   - Transcript appears automatically

4. **Generate SOAP note:**
   - Click **Generate SOAP Note**
   - Review the generated note on the right panel

5. **Use the note:**
   - **Copy to Clipboard** - Paste manually into Cliniko or any system
   - **Push to Cliniko** - Direct API integration (requires Cliniko setup)

## Cliniko API Setup (Optional)

To enable direct Cliniko integration:

1. Log into Cliniko
2. Go to **My Info** → **Manage API keys**
3. Click **Add an API key**
4. Copy the key (format: `xxxxx-au1`)
5. Add to your `.env` file:
   ```
   CLINIKO_API_KEY=xxxxx-au1
   CLINIKO_SHARD=au1
   CLINIKO_EMAIL=your@email.com
   ```

## Building as Desktop App (.app)

Package as a standalone macOS app that can be double-clicked to launch:

### Quick Build

> **Important:** Build inside a clean virtualenv, **not** an Anaconda/conda
> environment. Conda ships its own Qt5 (`qt-main`), which PyInstaller will
> bundle by mistake, producing an app that crashes on launch with
> *"Could not find the Qt platform plugin 'cocoa'"*. A plain venv only has
> PyQt6, so the correct Qt6 plugins get bundled.

```bash
# Create an isolated build environment (requires: brew install portaudio)
python3 -m venv .build-venv
.build-venv/bin/pip install -r requirements.txt pyinstaller

# Build the .app bundle
.build-venv/bin/python build.py

# The app will be at: dist/PhysioScript.app
```

### Build with DMG Installer

```bash
# Build .app + create DMG installer
.build-venv/bin/python build.py --dmg

# Output:
# - dist/PhysioScript.app
# - dist/PhysioScript-Installer.dmg
```

### Using Shell Script

```bash
chmod +x build_dmg.sh
./build_dmg.sh
```

### After Building

1. **First launch**: Right-click → Open (macOS security)
2. **Microphone permission**: Allow when prompted
3. **Ollama**: Must still be running separately on your machine

## Project Structure

```
physio-script/
├── main.py              # PyQt6 GUI application
├── build.py             # Build script for .app
├── physio_script.spec   # PyInstaller config
├── build_dmg.sh         # DMG build script
├── audio/
│   └── recorder.py      # Microphone recording (PyAudio)
├── transcription/
│   └── whisper.py       # OpenAI Whisper API
├── summarization/
│   └── ollama.py        # Ollama SOAP note generation
├── cliniko/
│   └── client.py        # Cliniko REST API v1
├── clipboard/
│   └── manager.py       # Clipboard copy/paste
├── config/
│   └── settings.py      # Configuration from .env
├── prompts/
│   └── soap_prompt.txt  # Physio SOAP note prompt
├── requirements.txt
└── .env.example
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Transcription model (large-v3-turbo, medium.en, small.en) | `large-v3-turbo` |
| `CLINIKO_API_KEY` | Cliniko API key | Optional |
| `CLINIKO_SHARD` | Cliniko region (au1, us1, etc.) | `au1` |
| `CLINIKO_EMAIL` | Your email for Cliniko User-Agent | Required for API |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3` |
| `CHUNK_DURATION_SECONDS` | Audio chunk length | `5` |
| `SAMPLE_RATE` | Audio sample rate | `16000` |

## Troubleshooting

**PyAudio installation fails (macOS):**
```bash
brew install portaudio
pip install pyaudio
```

**Ollama not connecting:**
```bash
# Make sure Ollama is running
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

**Cliniko API errors:**
- Ensure your API key is correct
- Check the shard matches your Cliniko region
- Verify API key permissions in Cliniko

## License

MIT
