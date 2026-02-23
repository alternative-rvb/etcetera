# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Etcetera** is a single-file Windows voice dictation application. It records audio via a global hotkey (Ctrl+Shift+Space), transcribes it locally using OpenAI's Whisper (via `faster-whisper`), and injects the result into the active window. No data leaves the machine.

The entire application lives in [etcetera.py](etcetera.py) (~507 lines). There are no subdirectories, no package structure, and no test suite.

## Running Locally

Install dependencies:
```bash
pip install customtkinter faster-whisper pyaudio pyautogui pyperclip keyboard
```

Run the app:
```bash
python etcetera.py
```

## Building the Executable

The project is compiled to a standalone `Etcetera.exe` via GitHub Actions (defined in [build.yml](build.yml)):
```
pyinstaller --onefile --windowed --name Etcetera etcetera.py
```

The workflow runs on `windows-latest` with Python 3.11. Artifacts are stored for 30 days.

## Architecture

`EtceteraApp` (subclass of `customtkinter.CTk`) is the single class containing the entire application.

**Threading model:** UI runs on the main thread. Recording, model loading, and transcription each run in daemon threads. All inter-thread communication goes through `self.status_queue` (a `queue.Queue`), polled every 50ms by `_poll_status`.

**Key flow:**
1. User holds Ctrl+Shift+Space → `_record_audio` thread starts, fills `self.audio_frames`
2. User releases hotkey → recording stops, `_transcribe` runs in a thread
3. Transcription result → sent via `status_queue` → `_poll_status` calls `_inject_text`
4. `_inject_text` copies text to clipboard, simulates Ctrl+V, then restores original clipboard after 1 second

**Model loading:** Whisper model is loaded lazily in a background thread on startup and on model-size change. Uses CPU inference with `int8` quantization. Available sizes: `tiny`, `base`, `small`.

**Audio:** 16 kHz, mono, 16-bit PCM via PyAudio. Volume feedback computed as RMS of each 1024-sample chunk.

**Configuration constants** (top of file, lines ~22–44): audio parameters, supported languages, and model size options.
