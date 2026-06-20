"""
Shared page setup — call after st.set_page_config() on every page.
"""
from pathlib import Path

import streamlit as st
from PIL import Image

ASSETS = Path(__file__).parent / "assets"
LOGO   = str(ASSETS / "logo.png")
ICON   = Image.open(ASSETS / "favicon.png")


def page_setup():
    pass
