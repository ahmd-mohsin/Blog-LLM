# app.py

__import__("pysqlite3")
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import os
from datetime import datetime
import pytz
import streamlit as st
from database import BlogDatabase
from dotenv import load_dotenv
from langchain.chains import LLMChain
from langchain_google_genai import GoogleGenerativeAI
from prompts import BLOG_DISCUSSION_PROMPT, FOLLOW_UP_QUESTIONS_PROMPT, MAIN_SYSTEM_PROMPT

load_dotenv()

db = BlogDatabase()
db.start_automatic_updates()

google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("Please set the GOOGLE_API_KEY environment variable")

llm = GoogleGenerativeAI(
    model="gemini-1.5-flash", google_api_key=google_api_key, temperature=0.15
)

custom_css = """
    <style>
        div[data-baseweb="select"] > div {
            overflow-x: auto !important;
        }
        .stAlert {
            margin-top: 1rem;
        }
        .last-update {
            font-size: 0.8rem;
            color: #888;
            margin-top: 0.5rem;
        }
    </style>
"""

def initialize_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "sources" not in st.session_state:
        st.session_state.sources = []
    if "topic" not in st.session_state:
        st.session_state.topic = None
    if "analysis_generated" not in st.session_state:
        st.session_state.analysis_generated = False

def display_chat():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})

def reset_chat():
    st.session_state.messages = []
    st.session_state.sources = []
    st.session_state.topic = None
    st.session_state.analysis_generated = False

def get_chat_history():
    return "\n".join(
        [f"{m['role']}: {m['content']}" for m in st.session_state.messages]
    )

def get_last_update():
    try:
        with open("chroma_db/last_update.txt", "r") as f:
            last_update_str = f.read().strip()
        last_update = datetime.fromisoformat(last_update_str)
        last_update = last_update.replace(tzinfo=pytz.UTC)
        return last_update.strftime("%Y-%m-%d %H:%M:%S (Pakistan Time)")
    except Exception as e:
        print(f"Error reading last update time: {e}")
        return "Unknown"

def main():
    initialize_session_state()

    st.set_page_config(
        layout="wide", page_title="BlogLLM", page_icon="images/favicon.ico"
    )
    st.markdown(custom_css, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1], gap="medium")

    with col1:
        st.markdown(
            "<img src='https://raw.githubusercontent.com/ahmd-mohsin/Blog-LLM/main/Images/1-removebg-preview.png' width='475' style='display: block; margin: 0 auto;'>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p class='last-update'>Last database update: {get_last_update()} | Made by <a href='https://github.com/ahmd-mohsin' target='_blank'>Muhammad Ahmed Mohsin</a></p>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("#### Prompt")
        topics = [
           "5G", "Machine Learning", "Quantum Computing","Artificial Intelligence", "LLMs"
            
        ]

        selected_topic = st.selectbox("Select a topic:", topics)
        selected_topic = selected_topic.split(" ")[0].lower()

        if st.button("Analyze blogs", use_container_width=True, type="primary"):
            reset_chat()
            st.session_state.topic = selected_topic
            with st.spinner("Generating summary..."):
                query = f"{selected_topic} blogs"
                relevant_documents = db.search(query, selected_topic, k=7)

                if not relevant_documents:
                    st.session_state.analysis_generated = False
                    add_message(
                        "assistant",
                        "No relevant blog posts found. Please try a different topic.",
                    )
                else:
                    context = "\n\n".join(
                        [
                            f"Blog Post {i+1}:\n{doc.page_content}..."
                            for i, doc in enumerate(relevant_documents)
                        ]
                    )

                    main_chain = LLMChain(llm=llm, prompt=MAIN_SYSTEM_PROMPT)
                    summary = main_chain.run(
                        topic=selected_topic, context=context
                    )

                    if summary.strip():
                        add_message("assistant", summary)
                        st.session_state.sources = [
                            doc.metadata["source"] for doc in relevant_documents
                        ]
                        st.session_state.analysis_generated = True

                        questions_chain = LLMChain(
                            llm=llm, prompt=FOLLOW_UP_QUESTIONS_PROMPT
                        )
                        follow_up = questions_chain.run(summary=summary)
                        add_message("assistant", follow_up)
                    else:
                        st.session_state.analysis_generated = False
                        add_message(
                            "assistant",
                            "Failed to generate a summary. Please try again.",
                        )

        if st.button("Reset", use_container_width=True):
            reset_chat()

        st.markdown("#### Sources")
        if st.session_state.sources:
            sources_text = "\n".join(
                [f"- [{source}]({source})" for source in st.session_state.sources]
            )
            st.markdown(sources_text)
        else:
            st.info("No sources available. Generate an analysis to see sources.")

    with col1:
        display_chat()

        if st.session_state.analysis_generated:
            user_input = st.chat_input(
                "Ask a follow-up question or type 'new analysis' to start over"
            )
            if user_input:
                if user_input.lower() == "new analysis":
                    reset_chat()
                    st.rerun()
                else:
                    add_message("human", user_input)
                    with st.spinner("Generating response..."):
                        chat_history = get_chat_history()
                        response_chain = LLMChain(llm=llm, prompt=BLOG_DISCUSSION_PROMPT)
                        response = response_chain.run(
                            topic=st.session_state.topic,
                            user_input=user_input,
                            chat_history=chat_history,
                        )
                        add_message("assistant", response)
                    st.rerun()

if __name__ == "__main__":
    main()
