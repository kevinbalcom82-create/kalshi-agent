
import telebot

import requests

import time

import re

import os

import json



# --- CONFIGURATION ---

TOKEN = "8681500188:AAFnxczSe6KwglMvUD8jkCl671FXxu3KfDo"

bot = telebot.TeleBot(TOKEN)



# --- SECURITY ---

ADMIN_ID = 8624674587



# --- STATE MANAGEMENT ---

user_memory = {}

user_spam_tracker = {}

RATE_LIMIT_WINDOW = 10  # Seconds

MAX_MSGS = 3            # Max messages per window



# --- LOCAL OLLAMA BRIDGE ---

def ask_hermes(user_id, user_message):

    url = "http://127.0.0.1:11434/api/chat"

    system_prompt = {

        "role": "system", 

        "content": "You are the Suncoast AI Assistant. Keep answers highly technical but brief (1-3 sentences). Once you answer their question, you MUST actively ask: 'What is the best email to send your custom quote to?'"

    }

    

    if user_id not in user_memory:

        user_memory[user_id] = []

        

    user_memory[user_id].append({"role": "user", "content": user_message})

    if len(user_memory[user_id]) > 6:

        user_memory[user_id] = user_memory[user_id][-6:]

        

    api_messages = [system_prompt] + user_memory[user_id]

    payload = {"model": "hermes3:8b", "messages": api_messages, "stream": False}

    

    try:

        response = requests.post(url, json=payload, timeout=45)

        response.raise_for_status()

        bot_reply = response.json()["message"]["content"]

        user_memory[user_id].append({"role": "assistant", "content": bot_reply})

        return bot_reply

    except Exception as e:

        return "⚠️ Secure Local Engine is currently processing heavy loads. Please email contact@suncoast-treasures.com."



# ==========================================

#      COMMAND & CONTROL (ADMIN ONLY)

# ==========================================

def is_admin(message):

    return message.from_user.id == ADMIN_ID



@bot.message_handler(commands=['status'])

def send_status(message):

    if not is_admin(message): return

    bot.reply_to(message, "🟢 **System Status: ONLINE**\nSniper Engine is armed and awaiting triggers.", parse_mode="Markdown")



@bot.message_handler(commands=['balance'])

def send_balance(message):

    if not is_admin(message): return

    bot.reply_to(message, "⏳ Querying Kalshi API for wallet balance...\n*(API logic pending integration)*")



@bot.message_handler(commands=['positions'])

def send_positions(message):

    if not is_admin(message): return

    bot.reply_to(message, "📡 Fetching open Kalshi contracts...\n*(API logic pending integration)*")



@bot.message_handler(commands=['logs'])

def send_logs(message):

    if not is_admin(message): return

    try:

        log_path = os.path.expanduser("~/kalshi_agent/output/engine.log")

        if not os.path.exists(log_path):

            # Fallback to the brain log if engine log isn't generated yet

            log_path = os.path.expanduser("~/kalshi_agent/output/hermes_brain.log")

            

        with open(log_path, "r", encoding="utf-8") as file:

            lines = file.readlines()[-15:]

            log_text = "".join(lines)

        bot.reply_to(message, f"🖥️ **Latest Logs:**\n```text\n{log_text}\n```", parse_mode="Markdown")

    except Exception as e:

        bot.reply_to(message, f"⚠️ Error reading logs: {e}")



@bot.message_handler(commands=['halt'])

def halt_execution(message):

    if not is_admin(message): return

    config_path = os.path.expanduser("~/kalshi_agent/engine_state.json")

    with open(config_path, "w") as f:

        json.dump({"status": "halted"}, f)

    bot.reply_to(message, "🛑 **EMERGENCY HALT EXECUTED.**\nSniper is locked. No new orders will be fired.", parse_mode="Markdown")



@bot.message_handler(commands=['resume'])

def resume_execution(message):

    if not is_admin(message): return

    config_path = os.path.expanduser("~/kalshi_agent/engine_state.json")

    with open(config_path, "w") as f:

        json.dump({"status": "active"}, f)

    bot.reply_to(message, "🟢 **SYSTEM RESUMED.**\nSniper is armed and listening for triggers.", parse_mode="Markdown")



# ==========================================

#     PUBLIC ROUTING & LEAD CAPTURE

# ==========================================

@bot.message_handler(commands=['start', 'help'])

def send_welcome(message):

    welcome_text = "⚡ System Online. I am the Suncoast AI powered by local silicon. How can I help you automate your workflows today?"

    bot.reply_to(message, welcome_text)



@bot.message_handler(func=lambda message: True)

def handle_message(message):

    uid = message.from_user.id

    now = time.time()

    

    # --- ANTI-SPAM ARMOR ---

    if uid not in user_spam_tracker:

        user_spam_tracker[uid] = []

        

    user_spam_tracker[uid] = [t for t in user_spam_tracker[uid] if now - t < RATE_LIMIT_WINDOW]

    

    if len(user_spam_tracker[uid]) >= MAX_MSGS:

        bot.reply_to(message, "🛡️ Anti-Spam Protocol Engaged: Please wait 10 seconds before sending another query.")

        return

        

    user_spam_tracker[uid].append(now)



    # --- INLINE LEAD CAPTURE ---

    text = message.text

    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)

    

    if email_match:

        extracted_email = email_match.group(0)

        with open("leads.txt", "a") as f:

            f.write(f"Lead Captured | User: {message.from_user.username} | Email: {extracted_email}\n")

        

        bot.reply_to(message, f"✅ Lead secured. I have routed `{extracted_email}` to our backend triage system. The Sovereign team will be in touch shortly.", parse_mode="Markdown")

        return



    # --- NORMAL AI ROUTING ---

    bot.send_chat_action(message.chat.id, 'typing')

    ai_reply = ask_hermes(uid, text)

    bot.reply_to(message, ai_reply)



if __name__ == "__main__":

    print("🟢 Suncoast V5 Commander & Closer Bot is ONLINE and listening...")

    bot.infinity_polling(timeout=60)

