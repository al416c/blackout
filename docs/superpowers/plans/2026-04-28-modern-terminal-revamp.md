# Refonte du Terminal Moderne Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter un terminal "Semi-Assisté" moderne avec autocomplétion riche, shop détaillé (avec descriptions), et une interface visuelle épurée (suppression des commandes spammables).

**Architecture:** 
- Centralisation de la logique de commande sur le backend (`server/game_engine.py`).
- Amélioration de l'UI côté client (`client/js/terminal.js` et `client/js/upgrades.js`) pour gérer les suggestions et le formattage en grille/boîtes.
- Ajout de styles CSS pour le nouveau rendu.

**Tech Stack:** 
- Python (Asyncio/WebSockets)
- Vanilla JavaScript
- CSS Variables

---

### Task 1: Backend Command Refinement

**Files:**
- Modify: `server/game_engine.py`

- [ ] **Step 1: Épurer la commande `help`**
Retirer les commandes à cooldown (`nmap`, `phishing`, `shadow`) de la liste d'aide pour ne garder que le Core + `hack`.

- [ ] **Step 2: Unifier les commandes `install` et `upgrade`**
S'assurer que les deux termes fonctionnent de la même manière et appellent la logique d'achat.

- [ ] **Step 3: Harmoniser le retour de `status`**
Rendre le texte plus compact et informatif.

- [ ] **Step 4: Commit**
```bash
git add server/game_engine.py
git commit -m "refactor(server): clean up red team commands and help protocols"
```

---

### Task 2: Detailed Shop Implementation

**Files:**
- Modify: `client/js/upgrades.js`

- [ ] **Step 1: Mettre à jour `getAvailableModulesText` pour inclure les descriptions**
Utiliser une structure en tableau/grille (via des espaces ou caractères box-drawing) pour afficher ID, NOM, PRIX et EFFET (description).

- [ ] **Step 2: Corriger le bug du shop vide**
S'assurer que si `allUpgrades` est vide, une demande `get_upgrades` est renvoyée au serveur.

- [ ] **Step 3: Commit**
```bash
git add client/js/upgrades.js
git commit -m "feat(client): add detailed shop descriptions and fix empty shop bug"
```

---

### Task 3: Terminal UI Enhancements (JS)

**Files:**
- Modify: `client/js/terminal.js`

- [ ] **Step 1: Implémenter la barre de suggestions d'autocomplétion**
Modifier `handleAutocomplete` pour afficher visuellement les suggestions au-dessus ou en-dessous du prompt.

- [ ] **Step 2: Améliorer la fonction `print`**
Ajouter des classes CSS selon le type de message (`success`, `error`, `highlight`) pour permettre un stylisage plus fin.

- [ ] **Step 3: Ajouter les raccourcis visuels dans l'en-tête**
Modifier l'init pour afficher "TAB: COMPLETE" et "CTRL+L: CLEAR".

- [ ] **Step 4: Commit**
```bash
git add client/js/terminal.js
git commit -m "feat(client): implement modern terminal UI features and autocomplete bar"
```

---

### Task 4: Terminal Styling (CSS)

**Files:**
- Modify: `client/css/style.css`

- [ ] **Step 1: Ajouter les styles pour la barre de suggestions**
`.terminal-suggestions`, `.suggestion-item`, etc.

- [ ] **Step 2: Styliser les boîtes d'aide et les rangées du shop**
Ajouter des bordures dashed, des fonds translucides et des couleurs pour les variables `--blue`, `--green`, etc.

- [ ] **Step 3: Commit**
```bash
git add client/css/style.css
git commit -m "style(client): add CSS for modern terminal look and shop layout"
```

---

### Task 5: Validation & Final Polish

- [ ] **Step 1: Lancer le serveur et tester les commandes**
Vérifier `help`, `shop`, `status`, `install <id>`.

- [ ] **Step 2: Vérifier l'autocomplétion**
Taper `ins` + `Tab`, puis `02` + `Tab`.

- [ ] **Step 3: Nettoyage**
Supprimer les mockups temporaires dans `.superpowers/brainstorm/`.

- [ ] **Step 4: Commit final**
```bash
rm -rf .superpowers/brainstorm/terminal-design
git commit -m "chore: remove brainstorm mockups and finalize terminal revamp"
```
