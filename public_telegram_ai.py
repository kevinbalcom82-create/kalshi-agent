
import telebot

import requests

import time

import re

import os



# --- CONFIGURATION ---

TOKEN = "8681500188:AAFnxczSe6KwglMvUD8jkCl671FXxu3KfDo"

bot = telebot.TeleBot(TOKEN)



# --- STATE MANAGEMENT (UPGRADES 1 & 3) ---

user_memory = {}

user_spam_tracker = {}

RATE_LIMIT_WINDOW = 10  # Seconds

MAX_MSGS = 3            # Max messages per window



# --- LOCAL OLLAMA BRIDGE ---

def ask_hermes(user_id, user_message):

    url = "http://127.0.0.1:11434/api/chat"

    

    # The New Closer Prompt

    system_prompt = {

        "role": "system", 

        "content": "You are the Suncoast AI Assistant. Keep answers highly technical but brief (1-3 sentences). Once you answer their question, you MUST actively ask: 'What is the best email to send your custom quote to?'"

    }

    

    # Memory Management (Initialize if new user)

    if user_id not in user_memory:

        user_memory[user_id] = []

        

    # Append the new user message

    user_memory[user_id].append({"role": "user", "content": user_message})

    

    # Keep only the last 6 interactions to prevent memory overflow

    if len(user_memory[user_id]) > 6:

        user_memory[user_id] = user_memory[user_id][-6:]

        

    api_messages = [system_prompt] + user_memory[user_id]

    

    payload = {"model": "hermes3:8b", "messages": api_messages, "stream": False}

    

    try:

        response = requests.post(url, json=payload, timeout=45)

        response.raise_for_status()

        bot_reply = response.json()["message"]["content"]

        

        # Save the AI's reply to memory so it remembers what it said

        user_memory[user_id].append({"role": "assistant", "content": bot_reply})

        return bot_reply

    except Exception as e:

        return "⚠️ Secure Local Engine is currently processing heavy loads. Please email contact@suncoast-treasures.com."



# --- TELEGRAM LISTENERS ---

@bot.message_handler(commands=['start', 'help'])

def send_welcome(message):

    welcome_text = "⚡ System Online. I am the Suncoast AI powered by local silicon. How can I help you automate your workflows today?"

    bot.reply_to(message, welcome_text)



@bot.message_handler(func=lambda message: True)

def handle_message(message):

    uid = message.from_user.id

    now = time.time()

    

    # --- UPGRADE 3: ANTI-SPAM ARMOR ---

    if uid not in user_spam_tracker:

        user_spam_tracker[uid] = []

        

    # Clear old timestamps outside the 10-second window

    user_spam_tracker[uid] = [t for t in user_spam_tracker[uid] if now - t < RATE_LIMIT_WINDOW]

    

    if len(user_spam_tracker[uid]) >= MAX_MSGS:

        bot.reply_to(message, "🛡️ Anti-Spam Protocol Engaged: Please wait 10 seconds before sending another query.")

        return

        

    user_spam_tracker[uid].append(now)



    # --- UPGRADE 2: INLINE LEAD CAPTURE ---

    text = message.text

    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)

    

    if email_match:

        extracted_email = email_match.group(0)

        # Log to a local file on the Mac Mini

        with open("leads.txt", "a") as f:

            f.write(f"Lead Captured | User: {message.from_user.username} | Email: {extracted_email}\n")

        

        bot.reply_to(message, f"✅ Lead secured. I have routed `{extracted_email}` to our backend triage system. The Sovereign team will be in touch shortly.")

        return



    # --- NORMAL AI ROUTING ---

    bot.send_chat_action(message.chat.id, 'typing')

    ai_reply = ask_hermes(uid, text)

    bot.reply_to(message, ai_reply)



if __name__ == "__main__":

    print("🟢 Suncoast V5 Closer Bot is ONLINE and listening...")

    bot.infinity_polling()

