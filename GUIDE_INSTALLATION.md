# 📖 Guide complet — Compiler Etcetera.exe via GitHub Actions

Aucune installation de Python sur ton PC. Tout se passe dans le cloud.

---

## Ce dont tu as besoin

- Un compte GitHub (gratuit) → https://github.com
- Git installé sur ton PC (WSL ou Windows natif)
- Les fichiers du projet (ce dossier)

## Structure des fichiers à pousser

GitHub Actions ne détecte les workflows **que** dans `.github/workflows/`. Le projet doit donc avoir cette structure avant le push :

```
etcetera/
├── .github/
│   └── workflows/
│       └── build.yml       ← déclenche la compilation automatique
├── etcetera.py
├── README.md
├── LICENSE
└── .gitignore
```

> ⚠️ Si `build.yml` est à la racine au lieu de `.github/workflows/`, l'onglet Actions sera vide et rien ne se compilera.

---

## ÉTAPE 1 — Créer un compte GitHub (si pas déjà fait)

1. Va sur https://github.com
2. Clique **Sign up**
3. Choisis un nom d'utilisateur, email, mot de passe
4. Valide ton email

---

## ÉTAPE 2 — Créer un nouveau repo GitHub

1. Connecte-toi sur https://github.com
2. Clique sur le **+** en haut à droite → **New repository**
3. Remplis :
   - **Repository name** : `etcetera`
   - **Visibility** : `Private` (recommandé) ou `Public`
   - **NE PAS** cocher "Add a README" (on a déjà le nôtre)
4. Clique **Create repository**
5. GitHub affiche une page avec des instructions — **garde cette page ouverte**

---

## ÉTAPE 3 — Pousser le code depuis WSL

Ouvre ton terminal WSL et lance ces commandes une par une :

```bash
# 1. Aller dans le dossier du projet
cd /chemin/vers/etcetera-project
# Exemple : cd ~/projets/etcetera-project

# 2. Initialiser Git
git init

# 3. Configurer ton identité Git (si pas déjà fait)
git config --global user.email "ton@email.com"
git config --global user.name "Ton Nom"

# 4. Créer le dossier workflows (OBLIGATOIRE pour GitHub Actions)
mkdir -p .github/workflows
mv build.yml .github/workflows/build.yml

# 5. Ajouter tous les fichiers
git add .

# 6. Premier commit
git commit -m "Initial commit - Etcetera"

# 7. Renommer la branche en 'main'
git branch -M main

# 8. Connecter au repo GitHub
#    Remplace TON_USERNAME par ton nom GitHub
git remote add origin https://github.com/TON_USERNAME/etcetera.git

# 9. Pousser le code
git push -u origin main
```

GitHub va te demander ton **nom d'utilisateur** et un **token** (pas ton mot de passe).

---

## ÉTAPE 3b — Créer un token GitHub (nécessaire pour le push)

GitHub n'accepte plus les mots de passe pour Git. Il faut un token :

1. Va sur https://github.com/settings/tokens
2. Clique **Generate new token (classic)**
3. Donne-lui un nom : `etcetera-push`
4. Durée : `90 days` (ou `No expiration`)
5. Coche la case **repo** (toute la ligne)
6. Clique **Generate token**
7. **Copie le token** (affiché une seule fois !)

Quand Git demande le mot de passe → colle ce token.

---

## ÉTAPE 4 — Vérifier que le build se lance

1. Va sur ton repo : `https://github.com/TON_USERNAME/etcetera`
2. Clique sur l'onglet **Actions**
3. Tu dois voir "Build Etcetera.exe" en cours d'exécution (icône jaune ⏳)
4. Attends ~5 minutes que ça se termine (icône verte ✅)

> ⚠️ Si l'onglet Actions est **vide** → le fichier `build.yml` n'est pas au bon endroit. Vérifie que tu as bien un dossier `.github/workflows/` dans ton repo (visible dans l'onglet **Code**).

Si c'est rouge ❌ → clique dessus pour voir l'erreur, et dis-moi ce que ça affiche.

---

## ÉTAPE 5 — Télécharger le .exe

1. Clique sur le workflow vert ✅
2. Tout en bas de la page, section **Artifacts**
3. Clique sur **Etcetera-Windows**
4. Un fichier `.zip` se télécharge
5. Dézippe → tu as ton **Etcetera.exe** !

---

## ÉTAPE 6 — Lancer l'app

1. Double-clique sur `Etcetera.exe`
2. Au premier lancement, il télécharge le modèle Whisper (~75 Mo) — attendre ~1 min
3. C'est prêt ! 🎙️

> ⚠️ Si Windows Defender bloque : clic droit → Propriétés → "Débloquer"
> ⚠️ Pour le raccourci global Ctrl+Shift+Espace : clic droit sur le .exe → "Exécuter en tant qu'administrateur"

---

## Pour les mises à jour

Si tu modifies `etcetera.py` plus tard, il suffit de :

```bash
git add etcetera.py
git commit -m "Mise à jour"
git push
```

GitHub Actions recompile automatiquement un nouveau `.exe`.

---

## Récapitulatif visuel

```
WSL (ton PC)              GitHub (cloud)           Ton PC
─────────────             ──────────────           ──────
etcetera.py  ──push──▶  Repo GitHub   
                           ↓ déclenche
                          Actions (VM Windows)
                           ↓ compile
                          Etcetera.exe  ◀──download── Double-clic !
```
