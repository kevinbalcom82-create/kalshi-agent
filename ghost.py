import sqlite3
import smtplib
from email.message import EmailMessage
import datetime

# --- SECURE CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com" 
SMTP_PORT = 587
EMAIL_ADDRESS = "contact@suncoast-treasures.com"
EMAIL_PASSWORD = "@Kalvin121618"

def sweep_ghosts():
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    
    # TEST MODE: Targets ANY pending lead instantly
    c.execute("""
        SELECT id, email FROM leads 
        WHERE status = 'pending_audit'
    """)
    ghosts = c.fetchall()
    
    if not ghosts:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] NO GHOSTS DETECTED. Engine sleeping.")
        conn.close()
        return

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] GHOST PROTOCOL ENGAGED. Targets acquired: {len(ghosts)}")
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except Exception as e:
        print(f"⚠️ COMMS FAILURE: SMTP Connection Refused. Check App Password. Error: {e}")
        conn.close()
        return

    for lead in ghosts:
        lead_id, target_email = lead
        
        msg = EmailMessage()
        msg['Subject'] = "Your bare-metal AI infrastructure spec"
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = target_email
        
        payload = """Hey,

I noticed you ran a test on the Hermes localized engine yesterday but didn't secure a slot for the architecture audit. 

If you are serious about dropping your cloud API costs and bringing your AI infrastructure entirely in-house (bare-metal), I have a few slots open this week.

You can grab a 15-minute slot on my calendar here to spec out your hardware limits:
https://cal.com/kevin-balcom-cgz7vy

Talk soon,

Kevin Balcom | Sovereign AI Architect
Suncoast Treasures
"""
        msg.set_content(payload)
        
        try:
            server.send_message(msg)
            print(f"✅ Payload successfully delivered to: {target_email}")
            c.execute("UPDATE leads SET status = 'ghost_emailed' WHERE id = ?", (lead_id,))
            conn.commit()
        except Exception as e:
            print(f"❌ Failed to email {target_email}. Target evaded. Error: {e}")
            
    server.quit()
    conn.close()
    print("Ghost sweep cycle concluded.")

if __name__ == "__main__":
    sweep_ghosts()
