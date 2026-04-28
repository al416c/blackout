# Design Spec: Topologie Organique à 17 Secteurs

## Vision
Transformer la carte du réseau en une métropole complexe divisée en 17 secteurs (clusters) interconnectés. Chaque secteur possède sa propre identité visuelle et est protégé par des "Gateways" (routeurs).

## 1. Topologie des Secteurs
- **Nombre :** 17 secteurs (ID: `0x00` à `0x10`).
- **Placement :** Distribution de points d'ancrage (seeds) sur un plan de 4000x3000px avec une contrainte de distance minimale pour éviter les chevauchements.
- **Composition :** Chaque secteur contient 4 à 8 nœuds générés autour de son point d'ancrage.
- **Gateways :** 1 nœud par secteur est désigné comme `GATEWAY`. Il possède un style visuel carré et sert de pont inter-secteur.

## 2. Connectivité & Propagation
- **Liens intra-secteur :** Connexions classiques, propagation à 100% de la vitesse normale.
- **Liens inter-secteur :** Uniquement entre deux `GATEWAY` de secteurs adjacents.
- **Passage Poreux :** 
    - Si Gateway cible NON infecté : Probabilité de propagation = 1% par tick.
    - Si Gateway cible INFECTÉ : Probabilité de propagation = 100% (vitesse normale).

## 3. Identité Visuelle
- **Couleurs :** Palette de 8 couleurs néon. Attribution aléatoire aux secteurs en évitant que deux secteurs reliés aient la même couleur.
- **Canvas :** Rendu d'un halo coloré (blur) au centre de chaque cluster pour délimiter visuellement les zones.

## 4. Nouvelles Upgrades
- `net_scanner` (Cost: 60) : Révèle les secteurs voisins.
- `gateway_exploit` (Cost: 150) : Réduit le coût d'infection forcée des Gateways.
- `signal_booster` (Cost: 250) : Augmente la porosité inter-secteur de 1% à 5%.
