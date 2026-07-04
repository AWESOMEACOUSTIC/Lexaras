import os
import streamlit as st

def load_styles() -> None:
    css_path = os.path.join(os.path.dirname(__file__), "styles.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
