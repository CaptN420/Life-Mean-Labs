# Modifications du système de débat multi-agents

## Problèmes identifiés

1. **Sélection trop permissive** : Le modérateur LLM pouvait répéter le même agent sans pénalité forte
2. **Pas de tracking des arguments** : Impossible de détecter les répétitions conceptuelles
3. **Contexte insuffisant** : Les agents ne savaient pas précisément à qui ils répondent
4. **Pas de mémoire d'identité** : Les agents ne tracking pas leurs propres positions changées

## Fichiers modifiés

### 1. `memory/argument_tracker.py` (NOUVEAU)
- Classe `Argument` pour structurer les arguments avec type, concepts clés, et qui on répond
- Classe `DebateState` pour suivre l'état du débat :
  - Distribution des locuteurs
  - Arguments exprimés par chaque agent
  - Objections et accords
  - Scores de pertinence et pénalités de répétition
  - Méthode `get_alternatives()` pour sélectionner intelligemment le prochain locuteur

### 2. `core/debate_engine.py` (MODIFIÉ)
- Ajout de `self.argument_state` pour tracker les arguments
- Méthode `_build_argument_summary()` pour inclure l'état des arguments dans le contexte
- `_get_moderator_decision()` amélioré :
  - Envoie les statistiques des locuteurs au modérateur
  - Avertissements critiques en cas de répétition
  - Liste des alternatives recommandées
  - Règles explicites contre la domination d'un agent
- `_build_context()` inclut maintenant le résumé des arguments

### 3. `agents/base_agent.py` (MODIFIÉ)
- Tracking des arguments exprimés par chaque agent (`_arguments_expressed`)
- Méthode `_extract_and_store_arguments()` pour extraire les positions clés
- Méthode `has_repeated_argument()` pour détecter les répétitions
- `format_response()` amélioré :
  - Montre à l'agent ses propres arguments précédents
  - Instructions claires pour répondre aux autres agents
  - Demande d'identifier explicitement à qui on répond

### 4. `agents/moderator.py` (MODIFIÉ)
- System prompt amélioré avec règles contre la domination
- Exemple montrant l'engagement direct avec les arguments précédents

## Tests effectués

```
✓ Argument tracking test passed
✓ Repetition prevention test passed  
✓ Alternative selection test passed
```

## Comportement attendu

Avant :
```
Pragmatique → Pragmatique → Pragmatique → Sceptique → Pragmatique...
```

Après :
```
Existentialiste → Sceptique critique → Existentialiste répond → 
Pragmatique propose alternative → Stoïcien critique → Nihiliste attaque →
Sceptique identifie contradiction → Pragmatique modifie position → ...
```

## Règles implémentées

1. **Pénalité de répétition** : +0.5 par tour, +2.0 pour tours consécutifs, +1.5 pour arguments établis répétés
2. **Prévention active** : Les agents avec >2.5x la moyenne sont exclus
3. **Score de pertinence** : +2.0 si l'agent a été cité, +1.0 si peu représenté
4. **Contexte enrichi** : Les agents voient leurs propres arguments et ceux des autres
