# 🎙️ Etcetera — Dictée vocale pour Windows

> *Parlez. Ça s'écrit tout seul.*

Dictée vocale **100% locale**, gratuite et sans abonnement.
Basée sur [Whisper](https://github.com/openai/whisper) (OpenAI) — aucune donnée ne quitte votre machine.

---

## Télécharger

**[⬇️ Télécharger Etcetera.exe](../../actions)**
*(onglet Actions → dernier build → section Artifacts)*

| | |
| --- | --- |
| Plateforme | Windows 10 / 11 (64-bit) |
| Taille de l'exe | ~100–150 Mo |
| Modèles Whisper | téléchargés automatiquement au premier lancement (~40–500 Mo selon le modèle choisi) |
| Dépendances | aucune — tout est inclus |

---

## Utilisation

### Raccourci global

**`Ctrl + Shift + Espace`** — maintenez appuyé pendant que vous parlez, relâchez pour transcrire et injecter.

### Bouton manuel

Cliquez sur **🔴 Démarrer la dictée** pour enregistrer, recliquez pour arrêter.

Le texte est injecté directement à l'endroit du curseur — dans VS Code, un navigateur, Word, Notepad, n'importe où.

---

## Modèles disponibles

| Modèle | Taille | Vitesse | Précision |
| --- | --- | --- | --- |
| Small | ~460 Mo | Rapide | Bonne |
| Turbo ⭐ | ~800 Mo | Rapide | Très bonne |
| Large-v3 | ~1.5 Go | Modérée | Excellente |

---

## Langues supportées

Auto-détection + Français, English, Espagnol, Deutsch, Italiano, Português

---

## Lancer depuis les sources

```bash
pip install customtkinter faster-whisper pyaudio pyautogui pyperclip keyboard pystray pillow
python etcetera.py
```

---

## Construire l'exe

```bash
pyinstaller --onefile --windowed --name Etcetera --collect-data faster_whisper etcetera.py
```

Ou laisser GitHub Actions le faire automatiquement à chaque push sur `main`.
