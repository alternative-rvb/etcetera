"""
Etcetera v2 - Dictée vocale avec injection directe dans tous les éditeurs
Basée sur Whisper (OpenAI) - 100% locale, 100% gratuite
- Raccourci global : Ctrl+Shift+Espace (maintenir pour dicter, relâcher pour transcrire)
- Injecte le texte directement là où se trouve le curseur
"""

import re
import struct
import ctypes
import tkinter as tk
import customtkinter as ctk
import threading
import pyaudio
import wave
import tempfile
import os
import time
import queue
import pyperclip
import pyautogui
import keyboard
import pystray
from PIL import Image, ImageDraw
from faster_whisper import WhisperModel

# ─── Configuration ────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SAMPLE_RATE = 16000
CHUNK       = 1024
CHANNELS    = 1
FORMAT      = pyaudio.paInt16

LANGUAGES = {
    "Auto-détection": None,
    "Français":       "fr",
    "English":        "en",
    "Español":        "es",
    "Deutsch":        "de",
    "Italiano":       "it",
    "Português":      "pt",
}

MODELS = {
    "Léger (small)":   "small",
    "Rapide (turbo)":  "turbo",
    "Précis (large)":  "large-v3",
}


# ─── Application ──────────────────────────────────────────────────────────────
class EtceteraApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🎙️ Etcetera v2")
        self.geometry("760x640")
        self.minsize(620, 520)

        # État
        self.recording       = False
        self.hotkey_held     = False
        self.model           = None
        self.model_name      = None
        self.audio_frames    = []
        self.p               = pyaudio.PyAudio()
        self.status_queue    = queue.Queue()
        self._placeholder_on  = True
        self._inject_after    = False
        self.debug_mode       = False
        self.debug_logs       = []
        self._target_hwnd     = None   # fenêtre cible pour l'injection
        self._tray_icon       = None   # icône system tray
        self._audio_running   = False  # verrou anti-double thread audio

        # Réglages avancés — transcription
        self._beam_size_str   = None   # StringVar, initialisé dans _build_ui
        self._temperature_str = None   # StringVar, initialisé dans _build_ui
        self._prompt_var      = None   # StringVar, initialisé dans _build_ui

        # Réglages avancés — post-traitement
        self.autocap_var      = None   # BooleanVar, initialisé dans _build_ui
        self.filler_var       = None   # BooleanVar, initialisé dans _build_ui

        # Réglages avancés — hotkey
        self.hotkey_trigger   = "space"
        self.hotkey_mods      = ["ctrl", "shift"]
        self._hotkey_capture  = False

        # Panneau avancé
        self.adv_mode         = False

        self._build_ui()
        self._load_model()
        self._poll_status()
        self._register_hotkey()

    # ─── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="#0d0d1a", corner_radius=0, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Etcetera v2",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#4fc3f7"
        ).pack(side="left", padx=20, pady=12)

        status_frame = ctk.CTkFrame(header, fg_color="#1a1a2e", corner_radius=8)
        status_frame.pack(side="right", padx=20, pady=18)

        self._status_dot = tk.Canvas(
            status_frame, width=10, height=10,
            bg="#1a1a2e", highlightthickness=0
        )
        self._status_dot.pack(side="left", padx=(10, 4), pady=6)
        self._dot_oval = self._status_dot.create_oval(1, 1, 9, 9, fill="#555", outline="")

        self.status_badge = ctk.CTkLabel(
            status_frame, text="Chargement...",
            font=ctk.CTkFont(size=12), text_color="#888"
        )
        self.status_badge.pack(side="left", padx=(0, 10), pady=6)

        # Bandeau raccourci
        hotkey_frame = ctk.CTkFrame(self, fg_color="#1a2744", corner_radius=0, height=36)
        hotkey_frame.pack(fill="x")
        hotkey_frame.pack_propagate(False)

        self.hotkey_banner_label = ctk.CTkLabel(
            hotkey_frame,
            text="⌨️  Raccourci global :  Ctrl + Shift + Espace  "
                 "— Maintenez appuyé pour dicter, relâchez pour transcrire & injecter",
            font=ctk.CTkFont(size=12), text_color="#7eb3ff"
        )
        self.hotkey_banner_label.pack(side="left", padx=16, pady=8)

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(10, 0))

        ctk.CTkLabel(toolbar, text="Langue :", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.lang_var = ctk.StringVar(value="Auto-détection")
        ctk.CTkOptionMenu(
            toolbar, values=list(LANGUAGES.keys()),
            variable=self.lang_var, width=130,
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(toolbar, text="Modèle :", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value="Léger (small)")
        ctk.CTkOptionMenu(
            toolbar, values=list(MODELS.keys()),
            variable=self.model_var, width=165,
            font=ctk.CTkFont(size=12),
            command=self._on_model_change
        ).pack(side="left", padx=(0, 15))

        self.inject_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            toolbar, text="Injection directe dans l'éditeur actif",
            variable=self.inject_var, font=ctk.CTkFont(size=12),
            command=lambda: setattr(self, "inject_mode", self.inject_var.get())
        ).pack(side="left", padx=(10, 0))

        self.adv_btn = ctk.CTkButton(
            toolbar, text="⚙ Avancé",
            font=ctk.CTkFont(size=12), height=28, width=90,
            fg_color="#333", hover_color="#444",
            command=self._toggle_adv
        )
        self.adv_btn.pack(side="right", padx=(0, 6))

        self.debug_btn = ctk.CTkButton(
            toolbar, text="🐛 Debug",
            font=ctk.CTkFont(size=12), height=28, width=90,
            fg_color="#333", hover_color="#444",
            command=self._toggle_debug
        )
        self.debug_btn.pack(side="right", padx=(0, 0))

        # Zone texte / historique
        text_frame = ctk.CTkFrame(self, corner_radius=10)
        text_frame.pack(fill="both", expand=True, padx=15, pady=10)

        ctk.CTkLabel(
            text_frame, text="Historique des transcriptions",
            font=ctk.CTkFont(size=11), text_color="#666"
        ).pack(anchor="nw", padx=10, pady=(8, 0))

        self.textbox = ctk.CTkTextbox(
            text_frame, font=ctk.CTkFont(size=14),
            wrap="word", corner_radius=8,
            border_width=1, border_color="#333"
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._set_placeholder()
        self.textbox.bind("<Button-1>", self._clear_placeholder)
        self.textbox.bind("<Key>", self._clear_placeholder)

        # Barre de volume
        vol_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        vol_frame.pack(fill="x", padx=15)
        vol_frame.pack_propagate(False)

        ctk.CTkLabel(vol_frame, text="Volume :",
                     font=ctk.CTkFont(size=11), text_color="#666").pack(side="left")
        self.volume_bar = ctk.CTkProgressBar(vol_frame, width=200, height=8, corner_radius=4)
        self.volume_bar.set(0)
        self.volume_bar.pack(side="left", padx=10)

        # ── Panel Avancé (caché par défaut) ───────────────────────────────────
        self.adv_frame = ctk.CTkFrame(
            self, corner_radius=8,
            fg_color="#111827", border_width=1, border_color="#334155"
        )
        # Ne pas pack() ici — affiché uniquement quand adv_mode est actif

        adv_inner = ctk.CTkFrame(self.adv_frame, fg_color="transparent")
        adv_inner.pack(fill="x", padx=12, pady=8)

        # Colonne 1 — Transcription
        col1 = ctk.CTkFrame(adv_inner, fg_color="transparent")
        col1.pack(side="left", padx=(0, 24), anchor="n")

        ctk.CTkLabel(
            col1, text="TRANSCRIPTION",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b"
        ).pack(anchor="w")

        beam_row = ctk.CTkFrame(col1, fg_color="transparent")
        beam_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(beam_row, text="Beam size :", font=ctk.CTkFont(size=12)).pack(side="left")
        self._beam_size_str = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            beam_row, values=["1", "2", "3", "4", "5"],
            variable=self._beam_size_str,
            width=70, font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(8, 0))

        temp_row = ctk.CTkFrame(col1, fg_color="transparent")
        temp_row.pack(fill="x", pady=2)
        ctk.CTkLabel(temp_row, text="Température :", font=ctk.CTkFont(size=12)).pack(side="left")
        self._temperature_str = ctk.StringVar(value="0.0")
        ctk.CTkOptionMenu(
            temp_row, values=["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"],
            variable=self._temperature_str,
            width=70, font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(8, 0))

        prompt_row = ctk.CTkFrame(col1, fg_color="transparent")
        prompt_row.pack(fill="x", pady=2)
        ctk.CTkLabel(prompt_row, text="Prompt initial :", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._prompt_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            col1, textvariable=self._prompt_var,
            placeholder_text="Ex : Bonjour, comment allez-vous ?",
            width=220, font=ctk.CTkFont(size=11)
        ).pack(anchor="w", pady=(2, 0))

        # Colonne 2 — Post-traitement
        col2 = ctk.CTkFrame(adv_inner, fg_color="transparent")
        col2.pack(side="left", padx=(0, 24), anchor="n")

        ctk.CTkLabel(
            col2, text="POST-TRAITEMENT",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b"
        ).pack(anchor="w")

        self.autocap_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            col2, text="Majuscule initiale",
            variable=self.autocap_var, font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(6, 2))

        self.filler_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            col2, text="Supprimer mots parasites\n(euh, hmm, ah, ben, hein)",
            variable=self.filler_var, font=ctk.CTkFont(size=11)
        ).pack(anchor="w", pady=2)

        # Colonne 3 — Raccourci
        col3 = ctk.CTkFrame(adv_inner, fg_color="transparent")
        col3.pack(side="left", anchor="n")

        ctk.CTkLabel(
            col3, text="RACCOURCI",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b"
        ).pack(anchor="w")

        self.hotkey_label = ctk.CTkLabel(
            col3, text=self._hotkey_display(),
            font=ctk.CTkFont(size=12), text_color="#7eb3ff",
            fg_color="#1a2744", corner_radius=4
        )
        self.hotkey_label.pack(anchor="w", pady=(6, 4))

        self.hotkey_capture_btn = ctk.CTkButton(
            col3, text="Changer...",
            font=ctk.CTkFont(size=12), height=28, width=100,
            fg_color="#1e3a5f", hover_color="#1d4ed8",
            command=self._start_hotkey_capture
        )
        self.hotkey_capture_btn.pack(anchor="w", pady=2)

        self.hotkey_capture_label = ctk.CTkLabel(
            col3, text="", font=ctk.CTkFont(size=11), text_color="#f59e0b"
        )
        self.hotkey_capture_label.pack(anchor="w")

        # Panel debug (caché par défaut)
        self.debug_frame = ctk.CTkFrame(self, corner_radius=8, fg_color="#1a1a1a", border_width=1, border_color="#ff5722")
        # Ne pas pack() ici — affiché uniquement quand debug_mode est actif

        debug_header = ctk.CTkFrame(self.debug_frame, fg_color="transparent")
        debug_header.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(
            debug_header, text="🐛 Logs d'erreurs",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#ff5722"
        ).pack(side="left")
        ctk.CTkButton(
            debug_header, text="📋 Copier les logs",
            font=ctk.CTkFont(size=11), height=24, width=120,
            fg_color="#333", hover_color="#444",
            command=self._copy_debug_logs
        ).pack(side="right")

        self.debug_textbox = ctk.CTkTextbox(
            self.debug_frame, font=ctk.CTkFont(family="Courier", size=11),
            height=100, corner_radius=6, wrap="word",
            text_color="#ff9800", fg_color="#111"
        )
        self.debug_textbox.pack(fill="x", padx=8, pady=(0, 8))
        self.debug_textbox.configure(state="disabled")

        # Boutons
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=(6, 12))
        self._bottom_ref = bottom

        self.record_btn = ctk.CTkButton(
            bottom,
            text="🔴  Démarrer la dictée",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46, width=230, corner_radius=23,
            fg_color="#c62828", hover_color="#b71c1c",
            command=self._toggle_recording,
            state="disabled"
        )
        self.record_btn.pack(side="left")

        btn_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_frame.pack(side="right")

        for txt, color, hover, cmd in [
            ("📋 Copier tout",  "#1565c0", "#0d47a1", self._copy_text),
            ("💾 Sauvegarder",  "#2e7d32", "#1b5e20", self._save_text),
            ("🗑️  Effacer",     "#424242", "#212121", self._clear_text),
        ]:
            ctk.CTkButton(
                btn_frame, text=txt,
                font=ctk.CTkFont(size=12), height=38, width=120,
                fg_color=color, hover_color=hover, command=cmd
            ).pack(side="left", padx=4)

        self.counter_label = ctk.CTkLabel(
            self, text="0 caractères • 0 mots",
            font=ctk.CTkFont(size=11), text_color="#555"
        )
        self.counter_label.pack(pady=(0, 6))

    # ─── Raccourci clavier global ─────────────────────────────────────────────
    def _register_hotkey(self):
        trigger = self.hotkey_trigger
        mods    = self.hotkey_mods

        def on_press(e):
            if all(keyboard.is_pressed(m) for m in mods):
                if not self.hotkey_held and not self.recording and self.model:
                    try:
                        self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    except Exception:
                        self._target_hwnd = None
                    self.hotkey_held = True
                    self.recording   = True
                    self.status_queue.put(("start_hotkey", None))

        def on_release(e):
            if self.hotkey_held:
                self.hotkey_held = False
                self.status_queue.put(("stop_hotkey", None))

        try:
            keyboard.on_press_key(trigger, on_press)
            keyboard.on_release_key(trigger, on_release)
        except Exception as ex:
            self._log_debug(f"[Hotkey] {ex}")

    # ─── Modèle Whisper ───────────────────────────────────────────────────────
    def _load_model(self, model_size="small"):
        def load():
            self.status_queue.put(("status", f"⏳ Chargement modèle '{model_size}'..."))
            try:
                self.model      = WhisperModel(model_size, device="cpu", compute_type="int8", num_workers=2, cpu_threads=4)
                self.model_name = model_size
                self.status_queue.put(("ready", f"✅ Prêt — {model_size}"))
            except Exception as e:
                self.status_queue.put(("error", f"❌ {e}"))
        threading.Thread(target=load, daemon=True).start()

    def _on_model_change(self, choice):
        if self.recording:
            return
        new = MODELS[choice]
        if new != self.model_name:
            self.record_btn.configure(state="disabled")
            self._load_model(new)

    # ─── Enregistrement ───────────────────────────────────────────────────────
    def _toggle_recording(self):
        if self.recording:
            self._stop_recording(inject=False)
        else:
            self._start_recording()

    def _start_recording(self):
        if self.model is None or self._audio_running:
            return
        self._audio_running = True
        self.recording      = True
        self.audio_frames   = []
        self.record_btn.configure(
            text="⏹️  Arrêter",
            fg_color="#37474f", hover_color="#263238"
        )
        self.status_queue.put(("recording", "🔴 Enregistrement..."))
        threading.Thread(target=self._record_audio, daemon=True).start()

    def _stop_recording(self, inject=False):
        self.recording     = False
        self._inject_after = inject
        self.record_btn.configure(state="disabled", text="⏳ Transcription IA...")
        self.volume_bar.set(0)
        self.status_queue.put(("status", "⏳ Transcription IA..."))
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _record_audio(self):
        stream = self.p.open(
            format=FORMAT, channels=CHANNELS,
            rate=SAMPLE_RATE, input=True,
            frames_per_buffer=CHUNK
        )
        while self.recording:
            data = stream.read(CHUNK, exception_on_overflow=False)
            self.audio_frames.append(data)
            shorts = struct.unpack(f"{len(data)//2}h", data)
            rms    = (sum(s * s for s in shorts) / len(shorts)) ** 0.5
            vol    = min(rms / 8000, 1.0)
            self.status_queue.put(("volume", vol))
        stream.stop_stream()
        stream.close()
        self._audio_running = False

    def _transcribe(self):
        if not self.audio_frames:
            self.status_queue.put(("ready_after", "✅ Prêt"))
            return

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wf  = wave.open(tmp.name, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.p.get_sample_size(FORMAT))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(self.audio_frames))
        wf.close()

        try:
            lang        = LANGUAGES[self.lang_var.get()]  # None = auto-détection
            beam_size   = int(self._beam_size_str.get())   if self._beam_size_str   else 1
            temperature = float(self._temperature_str.get()) if self._temperature_str else 0.0
            prompt      = self._prompt_var.get().strip()    if self._prompt_var       else ""

            transcribe_kwargs = dict(
                beam_size=beam_size,
                temperature=temperature,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                condition_on_previous_text=False,
            )
            if lang is not None:
                transcribe_kwargs["language"] = lang
            if prompt:
                transcribe_kwargs["initial_prompt"] = prompt

            def _collect(segs):
                raw = " ".join(s.text.strip() for s in segs if s.no_speech_prob < 0.5).strip()
                # Assure un espace après . , ! ? : ; sauf en fin de chaîne
                text = re.sub(r'([.,!?:;])(?=[^\s])', r'\1 ', raw)
                # Suppression des mots parasites (opt-in)
                if self.filler_var and self.filler_var.get():
                    text = re.sub(
                        r'\b(euh+|hmm+|ah|ben|hein)\b[\s,]*',
                        ' ', text, flags=re.IGNORECASE
                    ).strip()
                    text = re.sub(r'\s{2,}', ' ', text)
                # Majuscule initiale (opt-in)
                if self.autocap_var and self.autocap_var.get() and text:
                    text = text[0].upper() + text[1:]
                return text

            try:
                segs, info = self.model.transcribe(
                    tmp.name, vad_filter=True, **transcribe_kwargs
                )
                text = _collect(segs)
                if lang is None and text:
                    self._log_debug(f"[Lang] Détectée : {info.language} ({info.language_probability:.0%})")
            except Exception as vad_err:
                if "silero_vad" in str(vad_err) or "NO_SUCH_FILE" in str(vad_err) or "doesn't exist" in str(vad_err):
                    self._log_debug(f"[VAD] Modèle VAD manquant, transcription sans filtre : {vad_err}")
                    segs, info = self.model.transcribe(
                        tmp.name, vad_filter=False, **transcribe_kwargs
                    )
                    text = _collect(segs)
                else:
                    raise

            if text:
                do_inject = self._inject_after or self.inject_var.get()
                self.status_queue.put(("insert_text", (text, do_inject)))
            else:
                self.status_queue.put(("warn", "⚠️ Aucune parole détectée"))

        except Exception as e:
            self.status_queue.put(("error", f"❌ {e}"))
        finally:
            os.unlink(tmp.name)
            self._inject_after = False
            self.status_queue.put(("ready_after", "✅ Prêt"))

    # ─── Injection dans l'éditeur actif ──────────────────────────────────────
    def _inject_text(self, text):
        """
        Place le texte dans le presse-papiers et simule Ctrl+V
        dans la fenêtre qui était active avant la dictée.
        """
        try:
            old = ""
            try:
                old = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)

            # Redonner le focus à la fenêtre cible avant de coller
            # SetForegroundWindow seul est bloqué par Windows depuis un thread
            # non-GUI ; AttachThreadInput contourne cette restriction.
            if self._target_hwnd:
                try:
                    u32 = ctypes.windll.user32
                    fg_tid  = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
                    our_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                    if fg_tid != our_tid:
                        u32.AttachThreadInput(our_tid, fg_tid, True)
                    u32.SetForegroundWindow(self._target_hwnd)
                    if fg_tid != our_tid:
                        u32.AttachThreadInput(our_tid, fg_tid, False)
                except Exception as ex:
                    self._log_debug(f"[Focus] {ex}")
                time.sleep(0.15)
            else:
                time.sleep(0.15)

            pyautogui.hotkey("ctrl", "v")

            # Restaure le presse-papiers après 1 s
            def restore():
                time.sleep(1.0)
                try:
                    pyperclip.copy(old)
                except Exception:
                    pass
            threading.Thread(target=restore, daemon=True).start()
            return True

        except Exception as e:
            self._log_debug(f"[Injection] {e}")
            return False

    # ─── Polling UI ───────────────────────────────────────────────────────────
    def _poll_status(self):
        try:
            while True:
                msg_type, value = self.status_queue.get_nowait()

                if msg_type == "status":
                    self._set_status(value, "#888")

                elif msg_type == "ready":
                    self._set_status(value, "#4caf50")
                    self.record_btn.configure(state="normal")

                elif msg_type == "ready_after":
                    self._set_status(value, "#4caf50")
                    self.record_btn.configure(
                        state="normal",
                        text="🔴  Démarrer la dictée",
                        fg_color="#c62828", hover_color="#b71c1c"
                    )

                elif msg_type == "recording":
                    self._set_status(value, "#f44336")

                elif msg_type == "error":
                    self._set_status(value, "#ff5722")
                    self._log_debug(f"[Erreur] {value}")
                    self.record_btn.configure(
                        state="normal",
                        text="🔴  Démarrer la dictée",
                        fg_color="#c62828", hover_color="#b71c1c"
                    )

                elif msg_type == "warn":
                    self._set_status(value, "#ff9800")
                    self._log_debug(f"[Avertissement] {value}")
                    self.after(2000, lambda: self._set_status("✅ Prêt", "#4caf50"))
                    self.record_btn.configure(
                        state="normal",
                        text="🔴  Démarrer la dictée",
                        fg_color="#c62828", hover_color="#b71c1c"
                    )

                elif msg_type == "volume":
                    self.volume_bar.set(value)

                elif msg_type == "insert_text":
                    text, do_inject = value
                    self._add_to_history(text)
                    if do_inject:
                        self._set_status("⏳ Injection...", "#888")
                        def _do_inject(t=text + " "):
                            ok = self._inject_text(t)
                            msg   = "✅ Texte injecté !" if ok else "⚠️ Injection échouée — copié"
                            color = "#4caf50" if ok else "#ff9800"
                            if not ok:
                                self._log_debug("[Injection] Injection échouée")
                            self.after(0, lambda m=msg, c=color: (
                                self._set_status(m, c),
                                self.after(2500, lambda: self._set_status("✅ Prêt", "#4caf50"))
                            ))
                        threading.Thread(target=_do_inject, daemon=True).start()
                    else:
                        pyperclip.copy(text)
                        self._set_status("✅ Copié dans le presse-papiers", "#4caf50")
                        self.after(2500, lambda: self._set_status("✅ Prêt", "#4caf50"))

                elif msg_type == "start_hotkey":
                    # self.recording est déjà True (posé dans le callback hotkey)
                    # On appelle directement _start_recording sans re-tester
                    if self.model:
                        self._start_recording()

                elif msg_type == "stop_hotkey":
                    if self.recording:
                        self._stop_recording(inject=True)

        except queue.Empty:
            pass
        self.after(50, self._poll_status)

    # Correspondance couleurs hex → RGB pour l'icône tray
    _HEX_TO_RGB = {
        "#f44336": (244, 67,  54),   # enregistrement → rouge vif
        "#4caf50": (76,  175, 80),   # prêt           → vert
        "#ff9800": (255, 152, 0),    # avertissement  → orange
        "#ff5722": (255, 87,  34),   # erreur         → rouge-orange
        "#888":    (100, 100, 100),  # chargement     → gris
    }

    def _set_status(self, text, color):
        self.status_badge.configure(text=text, text_color=color)
        self._status_dot.itemconfig(self._dot_oval, fill=color)
        rgb = self._HEX_TO_RGB.get(color, (100, 100, 100))
        self._update_tray_icon(rgb)

    # ─── Debug ────────────────────────────────────────────────────────────────
    def _log_debug(self, msg):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.debug_logs.append(entry)
        if self.debug_mode:
            self.debug_textbox.configure(state="normal")
            self.debug_textbox.insert("end", entry + "\n")
            self.debug_textbox.see("end")
            self.debug_textbox.configure(state="disabled")

    def _toggle_debug(self):
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.debug_btn.configure(fg_color="#bf360c", hover_color="#e64a19")
            # Remplir avec les logs déjà accumulés
            self.debug_textbox.configure(state="normal")
            self.debug_textbox.delete("1.0", "end")
            for entry in self.debug_logs:
                self.debug_textbox.insert("end", entry + "\n")
            self.debug_textbox.see("end")
            self.debug_textbox.configure(state="disabled")
            self.debug_frame.pack(fill="x", padx=15, pady=(4, 0), before=self._bottom_ref)
        else:
            self.debug_btn.configure(fg_color="#333", hover_color="#444")
            self.debug_frame.pack_forget()

    # ─── Panneau Avancé ───────────────────────────────────────────────────────
    def _hotkey_display(self):
        parts = [m.capitalize() for m in self.hotkey_mods]
        parts.append(self.hotkey_trigger.capitalize())
        return " + ".join(parts)

    def _toggle_adv(self):
        self.adv_mode = not self.adv_mode
        if self.adv_mode:
            self.adv_btn.configure(fg_color="#1e3a5f", hover_color="#1d4ed8")
            anchor = self.debug_frame if self.debug_mode else self._bottom_ref
            self.adv_frame.pack(fill="x", padx=15, pady=(4, 0), before=anchor)
        else:
            self.adv_btn.configure(fg_color="#333", hover_color="#444")
            self.adv_frame.pack_forget()

    def _start_hotkey_capture(self):
        if self._hotkey_capture or self.recording:
            return
        self._hotkey_capture = True
        self.hotkey_capture_btn.configure(state="disabled", text="En attente...")
        self.hotkey_capture_label.configure(text="Appuyez sur votre combinaison...")
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        def _on_capture(event):
            if not self._hotkey_capture:
                return
            if event.name in ("ctrl", "shift", "alt", "windows", "caps lock", "unknown"):
                return
            mods = [m for m in ("ctrl", "shift", "alt") if keyboard.is_pressed(m)]
            new_trigger = event.name
            new_mods    = mods
            self._hotkey_capture = False
            self.after(0, lambda: self._apply_new_hotkey(new_trigger, new_mods))
            return False

        keyboard.hook(_on_capture)

    def _apply_new_hotkey(self, trigger, mods):
        self.hotkey_trigger = trigger
        self.hotkey_mods    = mods
        display = self._hotkey_display()
        self.hotkey_label.configure(text=display)
        self.hotkey_capture_label.configure(text="")
        self.hotkey_capture_btn.configure(state="normal", text="Changer...")
        self.hotkey_banner_label.configure(
            text=f"⌨️  Raccourci global :  {display}  "
                 "— Maintenez appuyé pour dicter, relâchez pour transcrire & injecter"
        )
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self._register_hotkey()
        self._log_debug(f"[Hotkey] Nouveau raccourci : {display}")

    def _copy_debug_logs(self):
        if self.debug_logs:
            pyperclip.copy("\n".join(self.debug_logs))
            self._set_status("✅ Logs copiés !", "#4caf50")
            self.after(2000, lambda: self._set_status("✅ Prêt", "#4caf50"))

    # ─── Zone texte ───────────────────────────────────────────────────────────
    def _set_placeholder(self):
        self.textbox.configure(text_color="#555")
        self.textbox.insert(
            "1.0",
            "Historique de vos dictées...\n\n"
            "• Raccourci Ctrl+Shift+Espace : maintenez pour dicter, relâchez pour injecter\n"
            "• Bouton 🔴 : dictée manuelle (texte copié ou injecté selon le réglage)\n"
            "• L'injection directe écrit automatiquement dans VS Code, le navigateur, etc."
        )
        self._placeholder_on = True

    def _clear_placeholder(self, event=None):
        if self._placeholder_on:
            self.textbox.delete("1.0", "end")
            self.textbox.configure(text_color=("gray10", "gray90"))
            self._placeholder_on = False

    def _add_to_history(self, text):
        self._clear_placeholder()
        ts = time.strftime("%H:%M:%S")
        self.textbox.insert("end", f"\n[{ts}]  {text}\n")
        self.textbox.see("end")
        self._update_counter()

    def _update_counter(self):
        if self._placeholder_on:
            self.counter_label.configure(text="0 caractères • 0 mots")
            return
        content = self.textbox.get("1.0", "end-1c")
        chars   = len(content)
        words   = len(content.split()) if content.strip() else 0
        self.counter_label.configure(text=f"{chars} caractères • {words} mots")

    def _copy_text(self):
        self._clear_placeholder()
        text = self.textbox.get("1.0", "end-1c")
        if text:
            pyperclip.copy(text)
            self._set_status("✅ Copié !", "#4caf50")
            self.after(2000, lambda: self._set_status("✅ Prêt", "#4caf50"))

    def _save_text(self):
        from tkinter import filedialog
        if self._placeholder_on:
            return
        text = self.textbox.get("1.0", "end-1c")
        if not text:
            return
        fp = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt"), ("Tous les fichiers", "*.*")],
            title="Sauvegarder la transcription"
        )
        if fp:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)
            self._set_status("✅ Sauvegardé !", "#4caf50")
            self.after(2000, lambda: self._set_status("✅ Prêt", "#4caf50"))

    def _clear_text(self):
        self.textbox.delete("1.0", "end")
        self._set_placeholder()
        self.counter_label.configure(text="0 caractères • 0 mots")

    # ─── System tray ──────────────────────────────────────────────────────────
    def _create_tray_image(self, dot_color=(198, 40, 40)):
        img = Image.new("RGB", (64, 64), color=(13, 13, 26))
        draw = ImageDraw.Draw(img)
        draw.ellipse((14, 14, 50, 50), fill=dot_color)
        return img

    def _update_tray_icon(self, dot_color):
        if self._tray_icon is not None:
            self._tray_icon.icon = self._create_tray_image(dot_color)

    def _start_tray(self):
        if self._tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Afficher", lambda: self.after(0, self._show_window), default=True),
            pystray.MenuItem("Quitter",  lambda: self.after(0, self._quit_app)),
        )
        # Couleur initiale selon l'état courant (prêt=vert, sinon gris)
        init_color = (76, 175, 80) if self.model else (100, 100, 100)
        self._tray_icon = pystray.Icon("Etcetera", self._create_tray_image(init_color), "Etcetera", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self):
        self.recording = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.p.terminate()
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()

    # ─── Fermeture (croix) → réduit dans le tray ──────────────────────────────
    def on_close(self):
        self.withdraw()
        self._start_tray()


# ─── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = EtceteraApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
