import os
import requests
from bs4 import BeautifulSoup
import pytz
from datetime import datetime

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message: str):
    """Sends notification chunks to avoid Telegram 4096 character limits."""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ ERROR: Telegram secrets missing.")
        return
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [message[i:i + 3900] for i in range(0, len(message), 3900)]
    for chunk in chunks:
        payload = {"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"}
        try:
            resp = requests.post(url, json=payload, timeout=15)
            print(f"Telegram status: {resp.status_code}")
            resp.raise_for_status()
        except Exception as e:
            print(f"Telegram dispatch error: {e}")

def run_test_scan():
    print("Running off-market test scan for previous completed session movers (±5%)...")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # 1. Fetch CSRF token
    try:
        init_resp = session.get("https://chartink.com/screener", timeout=12)
        soup = BeautifulSoup(init_resp.text, "html.parser")
        csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]
        session.headers.update({"X-CSRF-TOKEN": csrf_token})
    except Exception as e:
        print(f"Failed to obtain screener session: {e}")
        send_telegram_alert("⚠️ Alert Bot Error: Unable to fetch market session.")
        return

    # 2. Query completed session data (1 day ago close vs 2 days ago close)
    screener_clause = {
        "scan_clause": "( {cash} ( [ -1 ] 1 day ago close > [ -2 ] 2 days ago close * 1.05 or [ -1 ] 1 day ago close < [ -2 ] 2 days ago close * 0.95 ) )"
    }
    
    try:
        resp = session.post("https://chartink.com/screener/process", data=screener_clause, timeout=20)
        resp.raise_for_status()
        stocks = resp.json().get("data", [])
    except Exception as e:
        print(f"Query failed: {e}")
        send_telegram_alert(f"⚠️ Scan failed to retrieve results: {e}")
        return

    gainers = []
    losers = []

    for item in stocks:
        symbol = item.get("nsecode")
        close_price = float(item.get("close", 0.0))
        p_change = float(item.get("per_chg", 0.0))
        
        if not symbol:
            continue
            
        if p_change >= 5.0:
            gainers.append(f"🟢 *{symbol}*: +{p_change:.2f}% (Price: ₹{close_price:.2f})")
        elif p_change <= -5.0:
            losers.append(f"🔴 *{symbol}*: {p_change:.2f}% (Price: ₹{close_price:.2f})")

    # Sort gainers descending, losers ascending
    gainers.sort(key=lambda x: float(x.split("+")[1].split("%")[0]), reverse=True)
    losers.sort(key=lambda x: float(x.split(":")[1].split("%")[0].replace(" ", "")))

    ist = pytz.timezone("Asia/Kolkata")
    now_str = datetime.now(ist).strftime("%d %b %Y, %I:%M %p")

    total_count = len(gainers) + len(losers)
    print(f"Found {len(gainers)} Gainers and {len(losers)} Losers.")

    if total_count > 0:
        msg = f"🧪 *TEST ALERT: Settled Session Movers (±5%)*\n*Timestamp:* {now_str}\n*Total Equities Found:* {total_count}\n\n"
        if gainers:
            msg += f"🚀 *Gainers ({len(gainers)}):*\n" + "\n".join(gainers[:50]) + "\n\n"
            if len(gainers) > 50:
                msg += f"_...and {len(gainers) - 50} more gainers_\n\n"
        if losers:
            msg += f"🔻 *Losers ({len(losers)}):*\n" + "\n".join(losers[:50]) + "\n\n"
            if len(losers) > 50:
                msg += f"_...and {len(losers) - 50} more losers_"
        send_telegram_alert(msg)
    else:
        send_telegram_alert(f"ℹ️ *Test Complete ({now_str})*\nConnected successfully, but 0 stocks triggered ±5%.")

if __name__ == "__main__":
    run_test_scan()
