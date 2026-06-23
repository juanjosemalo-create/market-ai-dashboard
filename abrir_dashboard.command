#!/bin/bash
set -e

# Ir a la carpeta donde está este archivo
cd "$(dirname "$0")"

echo "======================================"
echo " Dashboard IA/Semis - Inicio automático"
echo "======================================"
echo "Carpeta: $(pwd)"
echo ""

# Verificar Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: No encuentro Python 3 en tu Mac."
  echo "Instalalo desde https://www.python.org/downloads/ y volvé a abrir este archivo."
  read -p "Presioná Enter para cerrar..."
  exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d ".venv" ]; then
  echo "Primera vez: creando entorno virtual..."
  python3 -m venv .venv
fi

# Activar entorno
source .venv/bin/activate

# Instalar/actualizar dependencias básicas si falta Streamlit
if ! python -c "import streamlit" >/dev/null 2>&1; then
  echo "Primera vez: instalando librerías necesarias..."
  pip install --upgrade pip
  pip install -r requirements.txt
fi

echo ""
echo "Abriendo dashboard..."
echo "Si el navegador no se abre solo, entrá a: http://localhost:8501"
echo ""

streamlit run app.py
