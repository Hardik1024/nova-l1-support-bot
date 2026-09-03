from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import platform
import psutil
import requests
import streamlit as st

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
JIRA_ISSUE_TYPE = os.getenv("JIRA_ISSUE_TYPE", "Task")

# ==========================================
# SYSTEM TOOLS
# ==========================================
@tool
def get_current_datetime():
    """Get the current date and time in India."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A, %d %B %Y, %I:%M:%S %p IST")

@tool
def get_weather(city: str):
    """Get live real-time weather information for any city or location in the world without an API key."""
    try:
        clean_city = city.strip().replace(" ", "+")
        url = f"https://wttr.in/{clean_city}?format=%C,+Temp:+%t,+Wind:+%w,+Humidity:+%h"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            weather_data = response.text.strip()
            if "<html" in weather_data.lower() or "unknown location" in weather_data.lower():
                return f"Could not find live weather data for '{city.title()}'."
            return f"Live weather in {city.title()}: {weather_data}"
        return f"Weather service unavailable (HTTP {response.status_code})."
    except Exception:
        return "Unable to connect to the live weather service at this time."

@tool
def get_system_info():
    """Get the backend Cloud Server system information (NOT the user's local PC)."""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    cpu = psutil.cpu_percent(interval=1)
    return (
        f"\n[Nova Cloud Server Diagnostics]\n"
        f"OS: {platform.system()} {platform.release()}\n"
        f"CPU Usage: {cpu}%\n"
        f"RAM Usage: {memory.percent}%\n"
        f"Free RAM: {round(memory.available / (1024**3), 2)} GB\n"
    )

# ==========================================
# JIRA HELPERS & TOOLS
# ==========================================
def jira_request(method, url, data=None):
    try:
        response = requests.request(
            method,
            f"{JIRA_BASE_URL}{url}",
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=data,
            timeout=30
        )
        return response
    except Exception:
        return None

@tool
def create_ticket(problem_summary, device, application, error_message, impact, troubleshooting, priority):
    """Create an IT support ticket in Jira."""
    description = (
        f"Problem: {problem_summary}\n"
        f"Device: {device}\n"
        f"Application: {application}\n"
        f"Error: {error_message}\n"
        f"Impact: {impact}\n"
        f"Troubleshooting: {troubleshooting}"
    )
    data = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": problem_summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            },
            "issuetype": {"name": JIRA_ISSUE_TYPE},
            "priority": {"name": priority}
        }
    }
    response = jira_request("POST", "/rest/api/3/issue", data)
    if response and response.status_code == 201:
        ticket_id = response.json()["key"]
        return f"Success. Ticket ID: {ticket_id}. It has been successfully routed to the L2 IT Support queue."
    return "Unable to connect to Jira."

@tool
def get_ticket(ticket_id):
    """Read an existing Jira ticket."""
    ticket_id = ticket_id.strip().upper()
    response = jira_request("GET", f"/rest/api/3/issue/{ticket_id}")
    if response and response.status_code == 200:
        fields = response.json()["fields"]
        return (
            f"Ticket ID: {ticket_id}\n"
            f"Summary: {fields.get('summary', '')}\n"
            f"Status: {fields.get('status', {}).get('name', '')}\n"
            f"Priority: {fields.get('priority', {}).get('name', '')}"
        )
    return "Ticket not found."

@tool
def search_tickets(search_text):
    """Search Jira support tickets."""
    data = {
        "jql": f'project = "{JIRA_PROJECT_KEY}" AND text ~ "{search_text}" ORDER BY created DESC',
        "maxResults": 10,
        "fields": ["summary", "status", "priority"]
    }
    response = jira_request("POST", "/rest/api/3/search/jql", data)
    if response and response.status_code == 200:
        issues = response.json().get("issues", [])
        if not issues:
            return "No matching tickets found."
        result = "Matching tickets:\n"
        for issue in issues:
            result += f"\n{issue['key']} | {issue['fields'].get('summary', '')} | {issue['fields'].get('status', {}).get('name', '')}"
        return result
    return "Unable to search tickets."

@tool
def list_all_tickets():
    """Fetch a broad list of all recent available tickets in the Jira system."""
    data = {
        "jql": f'project = "{JIRA_PROJECT_KEY}" ORDER BY created DESC',
        "maxResults": 15,
        "fields": ["summary", "status", "priority"]
    }
    response = jira_request("POST", "/rest/api/3/search/jql", data)
    if response and response.status_code == 200:
        issues = response.json().get("issues", [])
        if not issues:
            return "There are currently no tickets in the system."
        result = "Here are the most recent tickets in the system:\n"
        for issue in issues:
            result += f"\n- **{issue['key']}**: {issue['fields'].get('summary', '')} (Status: {issue['fields'].get('status', {}).get('name', '')})"
        return result
    return "Unable to fetch the list of tickets."

@tool
def update_ticket(ticket_id, summary="", priority="", description=""):
    """Update an existing Jira ticket."""
    fields = {}
    if summary:
        fields["summary"] = summary
    if priority:
        fields["priority"] = {"name": priority}
    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
        }
    if not fields:
        return "Nothing to update."
    ticket_id = ticket_id.strip().upper()
    response = jira_request("PUT", f"/rest/api/3/issue/{ticket_id}", {"fields": fields})
    if response and response.status_code == 204:
        return f"Ticket {ticket_id} updated successfully."
    return "Unable to update ticket."

@tool
def delete_ticket(ticket_id):
    """Delete an existing Jira ticket."""
    ticket_id = ticket_id.strip().upper()
    response = jira_request("DELETE", f"/rest/api/3/issue/{ticket_id}")
    if response and response.status_code == 204:
        return f"Ticket {ticket_id} deleted successfully."
    return "Unable to delete ticket."

# ==========================================
# SYSTEM INSTRUCTION & MODEL DEFINITION
# ==========================================
SYSTEM_INSTRUCTION = """
You are Nova, an L1 Technical Support Agent for an IT helpdesk.
Your ONLY job is to help with IT-related problems, ticketing, basic diagnostics, and utility tasks.

STRICT PERSONA GUARDRAILS:
- If the user asks for a joke, recipe, poem, or anything unrelated to IT support/helpdesk, YOU MUST POLITELY REFUSE.
- Keep troubleshooting concise, practical, and step-by-step.

TICKET CONFIRMATION RULE (CRITICAL):
- NEVER execute the `create_ticket` or `delete_ticket` tools without explicit final confirmation from the user.
- Once all ticket details (Problem summary, Device, Application, Error, Impact, Priority) are gathered, summarize them clearly and ask: "Should I go ahead and submit this ticket?"
- Only execute the tool after the user explicitly confirms (e.g., "Yes", "Proceed", "Create it").

JIRA DATA RULE (CRITICAL):
- When you use a Jira tool (list_all_tickets, get_ticket, search_tickets), YOU MUST PRINT THE ACTUAL TICKET DATA (ID, Summary, Status) directly into your chat response.
- NEVER say "Here are the tickets" without printing the list.

QUICK REPLIES (CRITICAL UI RULE):
You must provide 1 to 3 Quick Reply buttons at the VERY END of your responses, EXCEPT when the chat is concluding.

WHEN TO HIDE SUGGESTIONS (THE EXCEPTION):
If the conversation is concluding, DO NOT output the ===SUGGESTIONS=== block. This applies when:
- The user says "thank you", "bye", "that's all", or concludes the issue.
- You have just successfully created a Jira ticket and provided the final confirmation sign-off.
In these scenarios, output the message and stop.

WHEN TO USE SUGGESTIONS (ALL OTHER TIMES):
1. Greetings or Off-Topic Refusals: Provide standard navigation (e.g., "- Report an IT Issue", "- Check Existing Tickets").
2. Multiple Choice Steps: If you ask for OS or environment, provide explicit choices (e.g., "- Windows", "- macOS", "- Linux").
3. Troubleshooting Follow-ups: Check current status (e.g., "- That fixed it", "- Still not working").
4. Pre-Ticket Submission: Prompt for approval (e.g., "- Yes, create ticket", "- No, cancel").

FORMAT FOR SUGGESTIONS:
When generating quick replies, append this exact block at the very end of your response:

===SUGGESTIONS===
- Option 1
- Option 2
"""

my_llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    system_instruction=SYSTEM_INSTRUCTION,
    streaming=True,
    thinking_level="low"
)

my_llm_with_tools = my_llm.bind_tools([
    get_current_datetime, get_weather, get_system_info,
    create_ticket, get_ticket, search_tickets, list_all_tickets,
    update_ticket, delete_ticket
])

# ==========================================
# CHAT STREAMING RUNNER
# ==========================================
def get_bot_response_stream(current_chat_history, user_text, file_text="", image_base64=None):
    messages = [SystemMessage(content=SYSTEM_INSTRUCTION)]

    for msg in current_chat_history[-6:]:
        if msg["role"] == "user":
            if msg.get("content"):
                messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            if isinstance(msg.get("content"), str):
                messages.append(AIMessage(content=msg["content"]))

    current_message_content = []

    if file_text:
        current_message_content.append({"type": "text", "text": f"Attached Document Text:\n{file_text}"})

    current_message_content.append({"type": "text", "text": user_text})

    if image_base64:
        current_message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    messages.append(HumanMessage(content=current_message_content))

    response = my_llm_with_tools.invoke(messages)

    if response.tool_calls:
        messages.append(response)
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            yield {"type": "tool", "name": tool_name}

            if tool_name == "get_current_datetime":
                tool_result = get_current_datetime.invoke(tool_call["args"])
            elif tool_name == "get_weather":
                tool_result = get_weather.invoke(tool_call["args"])
            elif tool_name == "get_system_info":
                tool_result = get_system_info.invoke(tool_call["args"])
            elif tool_name == "create_ticket":
                tool_result = create_ticket.invoke(tool_call["args"])
            elif tool_name == "get_ticket":
                tool_result = get_ticket.invoke(tool_call["args"])
            elif tool_name == "search_tickets":
                tool_result = search_tickets.invoke(tool_call["args"])
            elif tool_name == "list_all_tickets":
                tool_result = list_all_tickets.invoke(tool_call["args"])
            elif tool_name == "update_ticket":
                tool_result = update_ticket.invoke(tool_call["args"])
            elif tool_name == "delete_ticket":
                tool_result = delete_ticket.invoke(tool_call["args"])
            else:
                continue

            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))

        for chunk in my_llm_with_tools.stream(messages):
            if chunk.text:
                yield {"type": "text", "content": chunk.text}
    else:
        if response.text:
            yield {"type": "text", "content": response.text}