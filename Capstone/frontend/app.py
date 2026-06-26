from __future__ import annotations

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


API_URL = os.getenv("API_URL", "http://localhost:8000/query")


def submit_question(question: str) -> str:
    response = requests.post(API_URL, json={"question": question}, timeout=120)
    response.raise_for_status()
    return response.json()["answer"]


def main() -> None:
    st.set_page_config(page_title="ICS Knowledge Assistant", page_icon="📚", layout="wide")
    st.title("ICS SOP & Knowledge Assistant")
    st.caption("Ask questions about internal SOPs, guidelines, and runbooks.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask an internal knowledge question...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching documents and drafting answer..."):
            try:
                answer = submit_question(question)
            except requests.RequestException as error:
                answer = (
                    "Could not reach the FastAPI backend. Make sure the API is running at "
                    f"`{API_URL}`.\n\nError: `{error}`"
                )
            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
