import streamlit as st
import ll_backend
import uuid
import docx
import base64
import sqlite3
import json
from pypdf import PdfReader

# ==========================================
# PAGE SETUP
# ==========================================
st.set_page_config(page_title="Nova Support", page_icon="💠", layout="wide")

# ==========================================
# SQLITE DATABASE SETUP
# ==========================================
def init_db():
    conn = sqlite3.connect("nova_chats.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chats (session_id TEXT PRIMARY KEY, user_id TEXT, history TEXT)''')
    conn.commit()
    conn.close()

def get_user_chats(user_id):
    conn = sqlite3.connect("nova_chats.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT session_id, history FROM chats WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    chats = {}
    for row in rows:
        chats[row[0]] = json.loads(row[1])
    return chats

def save_chat(session_id, user_id, history):
    conn = sqlite3.connect("nova_chats.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("REPLACE INTO chats (session_id, user_id, history) VALUES (?, ?, ?)", (session_id, user_id, json.dumps(history)))
    conn.commit()
    conn.close()

def delete_chat(session_id):
    conn = sqlite3.connect("nova_chats.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM chats WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# USER IDENTIFICATION
# ==========================================
if "user_id" not in st.query_params:
    new_user_id = str(uuid.uuid4())
    st.query_params["user_id"] = new_user_id
    user_id = new_user_id
else:
    user_id = st.query_params["user_id"]

chats_dictionary = get_user_chats(user_id)

if "current_chat_id" not in st.session_state:
    if chats_dictionary:
        st.session_state.current_chat_id = list(chats_dictionary.keys())[-1]
    else:
        st.session_state.current_chat_id = "PENDING"

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.title("💠 Nova")

    if st.button("+ New Chat", use_container_width=True):
        st.session_state.current_chat_id = "PENDING"
        st.rerun()

    st.divider()
    st.write("Previous Chats:")

    for chat_id, history in list(chats_dictionary.items()):
        if len(history) == 0:
            continue
        chat_name = "New Chat"
        for message in history:
            if message["role"] == "user":
                chat_name = message["content"][:15]
                if len(message["content"]) > 15:
                    chat_name += "..."
                break

        col1, col2 = st.columns([8, 2])
        with col1:
            if st.button(chat_name, key=f"chat_{chat_id}", use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{chat_id}"):
                delete_chat(chat_id)
                del chats_dictionary[chat_id]
                if st.session_state.current_chat_id == chat_id:
                    valid_chats = [cid for cid, hist in chats_dictionary.items() if len(hist) > 0]
                    st.session_state.current_chat_id = valid_chats[-1] if valid_chats else "PENDING"
                st.rerun()

# ==========================================
# MAIN CHAT WINDOW PREPARATION
# ==========================================
active_id = st.session_state.current_chat_id
if active_id == "PENDING":
    active_history = []
else:
    if active_id not in chats_dictionary:
        chats_dictionary[active_id] = []
    active_history = chats_dictionary[active_id]

# 🚨 CHANGE 1: Capture user input BEFORE rendering the chat box UI
user_input = st.chat_input("Ask Nova", accept_file=True, file_type=["pdf", "docx", "png", "jpg", "jpeg", "webp"])

pills_placeholder = st.empty()
suggestion_clicked = None

# 🚨 CHANGE 2: Only show pills if the user hasn't typed anything new yet
if not user_input and active_history and active_history[-1]["role"] == "assistant":
    last_msg = active_history[-1]["content"]
    if "===SUGGESTIONS===" in last_msg:
        sug_text = last_msg.split("===SUGGESTIONS===")[1].strip()
        suggestions = [s.strip("- 1234567890.*") for s in sug_text.split("\n") if s.strip()]

        if suggestions:
            with pills_placeholder.container():
                st.markdown("<br>", unsafe_allow_html=True)
                selection = st.pills(
                    "Quick Replies:",
                    options=suggestions,
                    label_visibility="collapsed",
                    key=f"pills_{len(active_history)}"
                )
                if selection:
                    suggestion_clicked = selection

# Detect if the user triggered a new message
is_new_message = user_input or suggestion_clicked

# ==========================================
# RENDER CHAT HISTORY OR WELCOME SCREEN
# ==========================================
chat_box = st.container()

with chat_box:
    # 🚨 CHANGE 3: Hide welcome screen INSTANTLY if a new message was sent
    if len(active_history) == 0 and not is_new_message:
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>How can I help you?</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 18px;'><b>Ask me about IT issues, upload a screenshot, or manage tickets.</b></p>", unsafe_allow_html=True)
        st.markdown("<br><br><br>", unsafe_allow_html=True)
    else:
        for msg in active_history:
            with st.chat_message(msg["role"]):
                if "file_name" in msg:
                    st.caption(f"**Attached File:** {msg['file_name']}")
                if "image_base64" in msg:
                    st.image(base64.b64decode(msg["image_base64"]), width=300)
                if msg["role"] == "assistant" and msg.get("tools"):
                    with st.expander("Tools used", expanded=False):
                        for tool_name in msg["tools"]:
                            st.write(tool_name)

                # Never display the suggestions delimiter in message history
                display_text = msg["content"].split("===SUGGESTIONS===")[0].strip()

                if msg["role"] == "user":
                    st.markdown(display_text.replace("\n", "  \n"))
                else:
                    st.markdown(display_text)

# ==========================================
# PROCESS NEW MESSAGE
# ==========================================
if is_new_message:
    # Immediately destroy the pills UI so it vanishes while loading
    pills_placeholder.empty()

    user_text = ""
    uploaded_files = []

    if user_input:
        user_text = user_input.text.strip()
        uploaded_files = user_input.files
    elif suggestion_clicked:
        user_text = suggestion_clicked

    if st.session_state.current_chat_id == "PENDING":
        new_id = str(uuid.uuid4())[:6]
        chats_dictionary[new_id] = []
        st.session_state.current_chat_id = new_id
        active_id = new_id
        active_history = chats_dictionary[new_id]

    file_name = None
    extracted_text = ""
    image_base64 = None

    if uploaded_files:
        uploaded_file = uploaded_files[0]
        file_name = uploaded_file.name
        ext = file_name.split('.')[-1].lower()

        if ext == "docx":
            doc = docx.Document(uploaded_file)
            extracted_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        elif ext == "pdf":
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
        elif ext in ["png", "jpg", "jpeg", "webp"]:
            image_bytes = uploaded_file.read()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # Render the user's message dynamically at the TOP of the empty screen
    with chat_box:
        with st.chat_message("user"):
            if file_name and not image_base64:
                st.caption(f"**Attached File:** {file_name}")
            if image_base64:
                st.image(base64.b64decode(image_base64), width=300)
            if user_text:
                st.markdown(user_text.replace("\n", "  \n"))

    if file_name and not user_text:
        user_text = "Please analyze this attached file/image."

    user_message_data = {"role": "user", "content": user_text}
    if file_name:
        user_message_data["file_name"] = file_name
    if image_base64:
        user_message_data["image_base64"] = image_base64

    active_history.append(user_message_data)
    save_chat(active_id, user_id, active_history)

    # ----------------------------------------
    # STREAMING LLM RESPONSE
    # ----------------------------------------
    with chat_box:
        with st.chat_message("assistant"):
            tool_box = st.empty()
            answer_box = st.empty()
            tools_used = []
            bot_answer = ""

            response_stream = ll_backend.get_bot_response_stream(
                active_history[:-1],
                user_text,
                file_text=extracted_text,
                image_base64=image_base64
            )

            with st.spinner("Working on it..."):
                for item in response_stream:
                    if item.get("type") == "tool":
                        tool_name = item.get("name", "")
                        if tool_name and tool_name not in tools_used:
                            tools_used.append(tool_name)
                            tool_box.info(f"Tool: {tool_name}")

                    elif item.get("type") == "text":
                        text = item.get("content", "")
                        if text:
                            bot_answer += text
                            # Hide the suggestion block during live token streaming
                            display_answer = bot_answer.split("===SUGGESTIONS===")[0].strip()
                            answer_box.markdown(display_answer)

            if tools_used:
                tool_box.empty()
                with st.expander("Tools used", expanded=False):
                    for tool_name in tools_used:
                        st.write(tool_name)

    assistant_message = {"role": "assistant", "content": bot_answer}
    if tools_used:
        assistant_message["tools"] = tools_used

    active_history.append(assistant_message)
    save_chat(active_id, user_id, active_history)

    st.rerun()