import streamlit as st
import ll_backend
import uuid
import docx
import base64
import random
import os
import datetime
import extra_streamlit_components as stx
from pypdf import PdfReader
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from your .env file
load_dotenv()

# ==========================================
# PAGE SETUP & DYNAMIC AESTHETICS (CSS)
# ==========================================
st.set_page_config(page_title="Nova Support", page_icon="💠", layout="wide")

st.markdown("""
<style>
    .stApp { 
        background: linear-gradient(180deg, var(--secondary-background-color) 0%, var(--background-color) 60%); 
    }
    .block-container { 
        padding-top: 3rem; 
    }
    
    /* --- CSS HACK: MOBILE-RESPONSIVE DISCLAIMER --- */
    [data-testid="stChatInput"] { 
        /* Increased from 25px to 45px to comfortably fit 2 lines on phones */
        padding-bottom: 45px !important; 
    }
    [data-testid="stChatInput"]::after {
        content: "Nova is an AI assistant and may make mistakes. Please verify critical information before taking action.";
        position: absolute; 
        bottom: 12px; /* Lifted slightly off the absolute bottom */
        left: 0; 
        right: 0; 
        text-align: center; 
        font-size: 0.70rem; /* Slightly smaller to fit better on mobile */
        color: #888888;
        line-height: 1.3; /* Better vertical spacing between the two lines */
        padding-left: 15px; /* Keeps text away from the left edge on phones */
        padding-right: 15px; /* Keeps text away from the right edge on phones */
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# PREDEFINED PROMPT POOL
# ==========================================
PROMPT_POOL = [
    "⛅ Check Weather",
    "📅 Date & Time",
    "🎫 Create Ticket",
    "💻 System Info",
    "📋 My Tickets",
    "🛜 Wi-Fi Issue",
    "🔑 Reset Password",
    "📱 Mobile Config",
    "🖨️ Printer Issue",
    "🐌 Slow PC"
]

if "welcome_prompts" not in st.session_state:
    st.session_state.welcome_prompts = random.sample(PROMPT_POOL, 4)

# ==========================================
# SUPABASE DATABASE SETUP
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_chats(user_id):
    response = supabase.table("Chats").select("*").eq("user_id", user_id).order("created_at", desc=False).execute()
    chats = {}
    for row in response.data:
        chats[row["session_id"]] = row["history"]
    return chats

def save_chat(session_id, user_id, history):
    supabase.table("Chats").upsert({
        "session_id": session_id,
        "user_id": user_id,
        "history": history
    }).execute()

def delete_chat(session_id):
    supabase.table("Chats").delete().eq("session_id", session_id).execute()

def delete_user_chats(user_id):
    supabase.table("Chats").delete().eq("user_id", user_id).execute()

# ==========================================
# TIME HELPERS (AZURE BULLETPROOF IST)
# ==========================================
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_chat_separator_time(iso_string):
    """Generates the centered 'Today 1:09 PM' separator"""
    if not iso_string: return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_string)
        now = datetime.datetime.now(IST)
        if dt.date() == now.date(): return f"Today {dt.strftime('%I:%M %p')}"
        elif dt.date() == now.date() - datetime.timedelta(days=1): return f"Yesterday {dt.strftime('%I:%M %p')}"
        else: return dt.strftime("%b %d, %Y, %I:%M %p")
    except Exception: return ""

# ==========================================
# USER IDENTITY (RACE-CONDITION FIX)
# ==========================================
cookie_manager = stx.CookieManager(key="nova_cookie_manager")

if "user_id" not in st.session_state:
    if "cookie_timer" not in st.session_state:
        st.session_state.cookie_timer = True
        st.stop() 
        
    cookie_user_id = cookie_manager.get(cookie="nova_user_id")
    
    if cookie_user_id:
        st.session_state.user_id = cookie_user_id
    else:
        new_id = str(uuid.uuid4())[:8]
        st.session_state.user_id = new_id
        expire_date = datetime.datetime.now(IST) + datetime.timedelta(days=365)
        cookie_manager.set("nova_user_id", new_id, expires_at=expire_date)

user_id = st.session_state.user_id
chats_dictionary = get_user_chats(user_id)

# ==========================================
# LAZY CHAT SESSION LOADING
# ==========================================
url_chat_id = st.query_params.get("chat_id")

if "current_chat_id" not in st.session_state:
    if url_chat_id and url_chat_id in chats_dictionary:
        st.session_state.current_chat_id = url_chat_id
    else:
        st.session_state.current_chat_id = None

if st.session_state.current_chat_id:
    st.query_params["chat_id"] = st.session_state.current_chat_id
elif "chat_id" in st.query_params:
    del st.query_params["chat_id"]

# ==========================================
# SIDEBAR (CLEAN, NATIVE STREAMLIT)
# ==========================================
with st.sidebar:
    st.title("💠 Nova")

    if st.button("+ New Chat", use_container_width=True):
        st.session_state.current_chat_id = None
        if "chat_id" in st.query_params:
            del st.query_params["chat_id"]
        
        st.session_state.welcome_prompts = random.sample(PROMPT_POOL, 4)
        st.rerun()

    st.divider()
    st.write("**Previous Chats**")

    for chat_id, history in list(chats_dictionary.items()):
        if not history:
            continue
        chat_name = "New Chat"
        for message in history:
            if message["role"] == "user":
                chat_name = message["content"][:18]
                if len(message["content"]) > 18:
                    chat_name += "..."
                break

        col1, col2 = st.columns([8, 2])
        with col1:
            if st.button(chat_name, key=f"chat_{chat_id}", use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.query_params["chat_id"] = chat_id
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{chat_id}"):
                delete_chat(chat_id)
                del chats_dictionary[chat_id]
                if st.session_state.current_chat_id == chat_id:
                    st.session_state.current_chat_id = None
                    if "chat_id" in st.query_params:
                        del st.query_params["chat_id"]
                st.rerun()

    st.divider()
    if st.button("🔄 Reset Profile", use_container_width=True):
        if "user_id" in st.session_state:
            delete_user_chats(st.session_state.user_id)
            
        fresh_id = str(uuid.uuid4())[:8]
        expire_date = datetime.datetime.now(IST) + datetime.timedelta(days=365)
        cookie_manager.set("nova_user_id", fresh_id, expires_at=expire_date)
        
        st.session_state.clear()
        st.session_state.user_id = fresh_id
        st.query_params.clear()
        st.rerun()

# ==========================================
# RETRIEVE ACTIVE CHAT HISTORY
# ==========================================
active_id = st.session_state.current_chat_id
if active_id and active_id in chats_dictionary:
    active_history = chats_dictionary[active_id]
else:
    active_history = []

# --- BUG FIX: PREVENT SUPABASE READ DELAY ON FIRST MESSAGE ---
if "local_active_history" in st.session_state and st.session_state.local_active_id == active_id:
    if len(st.session_state.local_active_history) > len(active_history):
        active_history = st.session_state.local_active_history

user_input = st.chat_input("Ask Nova", accept_file=True, file_type=["pdf", "docx", "png", "jpg", "jpeg", "webp"])

# ==========================================
# UI CONTAINERS & CHATGPT DATE SEPARATOR
# ==========================================
welcome_placeholder = st.empty()
chat_box = st.container()
pills_placeholder = st.empty()

suggestion_clicked = None
prompt_clicked = None

if not active_history:
    with welcome_placeholder.container():
        _, center_col, _ = st.columns([1, 3, 1])
        with center_col:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align: center; font-size: 2.2rem; margin-bottom: 5px;'>How can I help you today?</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; font-size: 1.05rem; margin-top: 0px; opacity: 0.7;'>Ask me to troubleshoot IT issues, run system diagnostics, or manage your Jira tickets.</p>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            prompts = st.session_state.welcome_prompts
            c1, c2 = st.columns(2)
            with c1:
                if st.button(prompts[0], use_container_width=True): prompt_clicked = prompts[0]
                if st.button(prompts[2], use_container_width=True): prompt_clicked = prompts[2]
            with c2:
                if st.button(prompts[1], use_container_width=True): prompt_clicked = prompts[1]
                if st.button(prompts[3], use_container_width=True): prompt_clicked = prompts[3]

if not user_input and active_history and active_history[-1]["role"] == "assistant":
    last_msg = active_history[-1]["content"]
    if "===SUGGESTIONS===" in last_msg:
        sug_text = last_msg.split("===SUGGESTIONS===")[1].strip()
        suggestions = [s.strip("- 1234567890.*") for s in sug_text.split("\n") if s.strip()]
        if suggestions:
            with pills_placeholder.container():
                st.markdown("<br>", unsafe_allow_html=True)
                selection = st.pills("Quick Replies:", options=suggestions, label_visibility="collapsed", key=f"pills_{len(active_history)}")
                if selection:
                    suggestion_clicked = selection

is_new_message = bool(user_input or suggestion_clicked or prompt_clicked)

with chat_box:
    last_date = None
    
    for msg in active_history:
        # --- CHATGPT STYLE DATE SEPARATOR ---
        if "timestamp" in msg:
            try:
                msg_dt = datetime.datetime.fromisoformat(msg["timestamp"]).date()
                if msg_dt != last_date:
                    separator_text = get_chat_separator_time(msg["timestamp"])
                    st.markdown(f"<div style='text-align: center; color: gray; font-size: 0.85rem; margin-top: 15px; margin-bottom: 15px;'>{separator_text}</div>", unsafe_allow_html=True)
                    last_date = msg_dt
            except Exception:
                pass

        with st.chat_message(msg["role"]):
            if "file_name" in msg:
                st.caption(f"**Attached File:** {msg['file_name']}")
            if "image_base64" in msg:
                st.image(base64.b64decode(msg["image_base64"]), width=300)
            if msg["role"] == "assistant" and msg.get("tools"):
                with st.expander("Tools used", expanded=False):
                    for tool_name in msg["tools"]:
                        st.write(tool_name)

            display_text = msg["content"].split("===SUGGESTIONS===")[0].strip()
            st.markdown(display_text.replace("\n", "  \n") if msg["role"] == "user" else display_text)

# ==========================================
# PROCESS NEW MESSAGE & LAZY ID CREATION
# ==========================================
if is_new_message:
    welcome_placeholder.empty()
    pills_placeholder.empty()

    user_text = ""
    uploaded_files = []

    if user_input:
        user_text = user_input.text.strip()
        uploaded_files = user_input.files
    elif suggestion_clicked:
        user_text = suggestion_clicked
    elif prompt_clicked:
        user_text = prompt_clicked

    if not st.session_state.current_chat_id:
        new_id = str(uuid.uuid4())[:8]
        st.session_state.current_chat_id = new_id
        st.query_params["chat_id"] = new_id
        active_id = new_id
        chats_dictionary[active_id] = []
        active_history = chats_dictionary[active_id]
    else:
        active_id = st.session_state.current_chat_id

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

    # Render User Message immediately
    with chat_box:
        current_iso_time = datetime.datetime.now(IST).isoformat()
        current_date_obj = datetime.datetime.fromisoformat(current_iso_time).date()
        if current_date_obj != last_date:
            separator_text = get_chat_separator_time(current_iso_time)
            st.markdown(f"<div style='text-align: center; color: gray; font-size: 0.85rem; margin-top: 15px; margin-bottom: 15px;'>{separator_text}</div>", unsafe_allow_html=True)
            last_date = current_date_obj

        with st.chat_message("user"):
            if file_name and not image_base64:
                st.caption(f"**Attached File:** {file_name}")
            if image_base64:
                st.image(base64.b64decode(image_base64), width=300)
            if user_text:
                st.markdown(user_text.replace("\n", "  \n"))

    if file_name and not user_text:
        user_text = "Please analyze this attached file/image."

    user_message_data = {
        "role": "user", 
        "content": user_text,
        "timestamp": current_iso_time
    }
    if file_name:
        user_message_data["file_name"] = file_name
    if image_base64:
        user_message_data["image_base64"] = image_base64

    active_history.append(user_message_data)
    save_chat(active_id, user_id, active_history)
    
    st.session_state.local_active_id = active_id
    st.session_state.local_active_history = active_history

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
                            display_answer = bot_answer.split("===SUGGESTIONS===")[0].strip()
                            answer_box.markdown(display_answer)

            if tools_used:
                tool_box.empty()
                with st.expander("Tools used", expanded=False):
                    for tool_name in tools_used:
                        st.write(tool_name)

    assistant_message = {
        "role": "assistant", 
        "content": bot_answer,
        "timestamp": datetime.datetime.now(IST).isoformat()
    }
    if tools_used:
        assistant_message["tools"] = tools_used

    active_history.append(assistant_message)
    save_chat(active_id, user_id, active_history)
    
    st.session_state.local_active_id = active_id
    st.session_state.local_active_history = active_history

    st.rerun()