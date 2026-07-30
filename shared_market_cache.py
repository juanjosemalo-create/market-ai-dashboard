"""Caché compartida entre las páginas de Streamlit.

Usar una única función cacheada evita que el tablero principal y la página
VIX/VIX3M mantengan snapshots intradía distintos.
"""
from __future__ import annotations

import streamlit as st

from data_sources import fetch_intraday


@st.cache_data(ttl=60 * 3, show_spinner=False)
def cached_intraday_shared():
    return fetch_intraday(period="5d", interval="5m")
