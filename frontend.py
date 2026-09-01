import streamlit as st
import ll_backend
import uuid
import docx
import base64
from pypdf import PdfReader

# ==========================================
# PAGE SETUP
# ==========================================
st.set_page_config(page_title="Nova Support", page_icon="💠", layout="wide")

# ==========================================
# MULTI-USER CHAT DATABASE (Survives Reloads)
# ==========================================
@st.cache_resource
def get_global_chat_db():
    return {}

global_db = get_global_chat_db()

if "user_id" not in st.query_params:
    new_user_id = str(uuid.uuid4())
    st.query_params["user_id"] = new_user_id
    user_id = new_user_id
else:
    user_id = st.query_params["user_id"]

if user_id not in global_db:
    global_db[user_id] = {}

chats_dictionary = global_db[user_id]

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
                del chats_dictionary[chat_id]

                if st.session_state.current_chat_id == chat_id:
                    valid_chats = [cid for cid, history in chats_dictionary.items() if len(history) > 0]
                    if valid_chats:
                        st.session_state.current_chat_id = valid_chats[-1]
                    else:
                        st.session_state.current_chat_id = "PENDING"
                st.rerun()

# ==========================================
# MAIN CHAT WINDOW
# ==========================================
active_id = st.session_state.current_chat_id

if active_id == "PENDING":
    active_history = []
else:
    if active_id not in chats_dictionary:
        chats_dictionary[active_id] = []
    active_history = chats_dictionary[active_id]

chat_box = st.container()

with chat_box:
    
    if len(active_history) == 0:
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>How can I help you?</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 18px;'><b>Ask me about IT issues, upload a screenshot, or manage tickets.</b></p>", unsafe_allow_html=True)
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        
    else:
        for msg in active_history:
            with st.chat_message(msg["role"]):
                
                # Render uploaded files/images in chat history
                if "file_name" in msg:
                    st.caption(f"**Attached File:** {msg['file_name']}")
                if "image_base64" in msg:
                    # Decode and display the image
                    image_bytes = base64.b64decode(msg["image_base64"])
                    st.image(image_bytes, width=300)

                if msg["role"] == "assistant" and msg.get("tools"):
                    with st.expander("Tools used", expanded=False):
                        for tool_name in msg["tools"]:
                            st.write(tool_name)

                if msg["role"] == "user":
                    st.markdown(msg["content"].replace("\n", "  \n"))
                else:
                    st.markdown(msg["content"])

# ==========================================
# USER INPUT & FILE HANDLING (Now with Images)
# ==========================================
user_input = st.chat_input(
    "Ask Nova",
    accept_file=True,
    file_type=["pdf", "docx", "png", "jpg", "jpeg", "webp"]
)

if user_input:
    user_text = user_input.text.strip()
    uploaded_files = user_input.files

    if st.session_state.current_chat_id == "PENDING":
        new_id = str(uuid.uuid4())[:6]
        chats_dictionary[new_id] = []
        st.session_state.current_chat_id = new_id
        active_history = chats_dictionary[new_id]

    file_name = None
    extracted_text = ""
    image_base64 = None

    if uploaded_files:
        uploaded_file = uploaded_files[0]
        file_name = uploaded_file.name
        ext = file_name.split('.')[-1].lower()

        # Handle Documents
        if ext == "docx":
            doc = docx.Document(uploaded_file)
            extracted_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        elif ext == "pdf":
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
        
        # Handle Images
        elif ext in ["png", "jpg", "jpeg", "webp"]:
            image_bytes = uploaded_file.read()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # Render current message instantly
    with chat_box:
        with st.chat_message("user"):
            if file_name and not image_base64:
                st.caption(f"**Attached File:** {file_name}")
            if image_base64:
                st.image(base64.b64decode(image_base64), width=300)
            if user_text:
                st.markdown(user_text.replace("\n", "  \n"))

    # Generate text for empty submissions
    if file_name and not user_text:
        user_text = "Please analyze this attached file/image."

    # Save to history
    user_message_data = {
        "role": "user",
        "content": user_text
    }
    if file_name:
        user_message_data["file_name"] = file_name
    if image_base64:
        user_message_data["image_base64"] = image_base64

    active_history.append(user_message_data)

    # ----------------------------------------
    # USER PROMPT + TOOL STREAMING
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
                            answer_box.markdown(bot_answer)

            if tools_used:
                tool_box.empty()
                with st.expander("Tools used", expanded=False):
                    for tool_name in tools_used:
                        st.write(tool_name)

    assistant_message = {
        "role": "assistant",
        "content": bot_answer
    }

    if tools_used:
        assistant_message["tools"] = tools_used

    active_history.append(assistant_message)
    st.rerun()