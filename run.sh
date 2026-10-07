#!/usr/bin/env bash
# Script de lancement de Pédantix Local

cd "$(dirname "$0")" || exit 1

echo "Démarrage de Pédantix Local..."
python3 main.py "$@"
