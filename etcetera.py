"""
Etcetera v2 - Dictée vocale avec injection directe dans tous les éditeurs
Basée sur Whisper (OpenAI) - 100% locale, 100% gratuite
- Raccourci global : Ctrl+Shift+Espace (maintenir pour dicter, relâcher pour transcrire)
- Injecte le texte directement là où se trouve le curseur
"""

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
from faster_whisper import WhisperModel

# ─── Configuration ────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SAMPLE_RATE = 16000
CHUNK       = 1024
CHANNELS    = 1
FORMAT      = pyaudio.paInt16

LANGUAGES = {
    "Français":  "fr",
    "English":   "en",
    "Español":   "es",
    "Deutsch":   "de",
    "Italiano":  "it",
    "Português": "pt",
}

MODELS = {
    "Rapide (tiny)":    "tiny",
    "Équilibré (base)": "base",
    "Précis (small)":   "small",
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
        self.inject_mode     = True
        self._placeholder_on = True
        self._inject_after   = False
        self.debug_mode      = False
        self.debug_logs      = []

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
            header, text="🎙️  Etcetera v2",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#4fc3f7"
        ).pack(side="left", padx=20, pady=12)

        self.status_badge = ctk.CTkLabel(
            header, text="⏳ Chargement...",
            font=ctk.CTkFont(size=12), text_color="#888",
            fg_color="#1a1a2e", corner_radius=8, padx=10, pady=4
        )
        self.status_badge.pack(side="right", padx=20, pady=18)

        # Bandeau raccourci
        hotkey_frame = ctk.CTkFrame(self, fg_color="#1a2744", corner_radius=0, height=36)
        hotkey_frame.pack(fill="x")
        hotkey_frame.pack_propagate(False)

        ctk.CTkLabel(
            hotkey_frame,
            text="⌨️  Raccourci global :  Ctrl + Shift + Espace  "
                 "— Maintenez appuyé pour dicter, relâchez pour transcrire & injecter",
            font=ctk.CTkFont(size=12), text_color="#7eb3ff"
        ).pack(side="left", padx=16, pady=8)

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(10, 0))

        ctk.CTkLabel(toolbar, text="Langue :", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.lang_var = ctk.StringVar(value="Français")
        ctk.CTkOptionMenu(
            toolbar, values=list(LANGUAGES.keys()),
            variable=self.lang_var, width=130,
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(toolbar, text="Modèle :", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value="Rapide (tiny)")
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
        self.volume_label = ctk.CTkLabel(
            vol_frame, text="", width=130,
            font=ctk.CTkFont(family="Courier", size=11), text_color="#4fc3f7"
        )
        self.volume_label.pack(side="left")

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
        def on_space_press(e):
            if keyboard.is_pressed("ctrl") and keyboard.is_pressed("shift"):
                if not self.hotkey_held and not self.recording and self.model:
                    self.hotkey_held = True
                    self.status_queue.put(("start_hotkey", None))

        def on_space_release(e):
            if self.hotkey_held and self.recording:
                self.hotkey_held = False
                self.status_queue.put(("stop_hotkey", None))

        try:
            keyboard.on_press_key("space", on_space_press)
            keyboard.on_release_key("space", on_space_release)
        except Exception as ex:
            print(f"[Hotkey] {ex}")

    # ─── Modèle Whisper ───────────────────────────────────────────────────────
    def _load_model(self, model_size="tiny"):
        def load():
            self.status_queue.put(("status", f"⏳ Chargement modèle '{model_size}'..."))
            try:
                self.model      = WhisperModel(model_size, device="cpu", compute_type="int8")
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
        if self.model is None:
            return
        self.recording    = True
        self.audio_frames = []
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
        self.volume_label.configure(text="")
        self.status_queue.put(("status", "⏳ Transcription IA..."))
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _record_audio(self):
        import struct
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
            lang = LANGUAGES[self.lang_var.get()]
            segments, _ = self.model.transcribe(
                tmp.name, language=lang,
                beam_size=3, vad_filter=True
            )
            text = " ".join(s.text.strip() for s in segments).strip()

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
        dans la fenêtre active (VS Code, navigateur, Notepad, etc.)
        """
        try:
            old = ""
            try:
                old = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)
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
            print(f"[Injection] {e}")
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
                    self.record_btn.configure(
                        state="normal",
                        text="🔴  Démarrer la dictée",
                        fg_color="#c62828", hover_color="#b71c1c"
                    )

                elif msg_type == "warn":
                    self._set_status(value, "#ff9800")
                    self.after(2000, lambda: self._set_status("✅ Prêt", "#4caf50"))
                    self.record_btn.configure(
                        state="normal",
                        text="🔴  Démarrer la dictée",
                        fg_color="#c62828", hover_color="#b71c1c"
                    )

                elif msg_type == "volume":
                    self.volume_bar.set(value)
                    bars = int(value * 12)
                    self.volume_label.configure(text="█" * bars + "░" * (12 - bars))

                elif msg_type == "insert_text":
                    text, do_inject = value
                    self._add_to_history(text)
                    if do_inject:
                        ok = self._inject_text(text)
                        msg = "✅ Texte injecté !" if ok else "⚠️ Injection échouée — copié"
                        color = "#4caf50" if ok else "#ff9800"
                    else:
                        pyperclip.copy(text)
                        msg, color = "✅ Copié dans le presse-papiers", "#4caf50"
                    self._set_status(msg, color)
                    self.after(2500, lambda: self._set_status("✅ Prêt", "#4caf50"))

                elif msg_type == "start_hotkey":
                    if self.model and not self.recording:
                        self._start_recording()

                elif msg_type == "stop_hotkey":
                    if self.recording:
                        self._stop_recording(inject=True)

        except queue.Empty:
            pass
        self.after(50, self._poll_status)

    def _set_status(self, text, color):
        self.status_badge.configure(text=text, text_color=color)

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

    # ─── Fermeture ────────────────────────────────────────────────────────────
    def on_close(self):
        self.recording = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.p.terminate()
        self.destroy()


# ─── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = EtceteraApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
