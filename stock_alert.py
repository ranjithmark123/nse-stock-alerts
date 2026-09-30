from datetime import datetime
import os
from bs4 import BeautifulSoup
import pytz
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Official NSE Equity Trading Holidays for 2026 (Format: YYYY-MM-DD)
NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}


def send_telegram_alert(message: str):
  """Sends notification chunks to avoid Telegram 4096 character limits."""
  if not BOT_TOKEN or not CHAT_ID:
    print("❌ ERROR: Telegram secrets missing.")
    return

  url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
  chunks = [message[i : i + 3900] for i in range(0, len(message), 3900)]
  for chunk in chunks:
    payload = {"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"}
    try:
      resp = requests.post(url, json=payload, timeout=15)
      print(f"Telegram status: {resp.status_code}")
      resp.raise_for_status()
    except Exception as e:
      print(f"Telegram dispatch error: {e}")


def check_holiday_status():
  """Checks whether today is a weekend or an official NSE trading holiday."""
  ist = pytz.timezone("Asia/Kolkata")
  today = datetime.now(ist)
  date_str = today.strftime("%Y-%m-%d")
  day_name = today.strftime("%A")

  # 1. Check Weekend
  if today.weekday() >= 5:  # Saturday=5, Sunday=6
    return (
        True,
        f"🏖️ *NSE Market Holiday ({day_name})*\nThe Indian stock market is"
        " closed for the weekend.",
    )

  # 2. Check NSE Listed Holidays
  if date_str in NSE_HOLIDAYS_2026:
    holiday_reason = NSE_HOLIDAYS_2026[date_str]
    return (
        True,
        f"🇮🇳 *NSE Market Holiday Alert*\nDate: *{date_str}*"
        f" ({day_name})\nMarket is closed today on account of"
        f" *{holiday_reason}*.",
    )

  return False, ""


def scan_entire_nse_market():
  # Check if market is closed today
  is_holiday, holiday_msg = check_holiday_status()
  if is_holiday:
    print(holiday_msg)
    send_telegram_alert(holiday_msg)
    return

  print("Scanning all Indian Equities across NSE for ±5% moves...")

  session = requests.Session()
  session.headers.update({
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "X-Requested-With": "XMLHttpRequest",
  })

  # Fetch CSRF token
  try:
    init_resp = session.get("https://chartink.com/screener", timeout=12)
    soup = BeautifulSoup(init_resp.text, "html.parser")
    csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]
    session.headers.update({"X-CSRF-TOKEN": csrf_token})
  except Exception as e:
    print(f"Failed to obtain screener session: {e}")
    send_telegram_alert("⚠️ Alert Bot Error: Unable to fetch market session.")
    return

  # Scan clause for all Indian cash equities moving >= +5% OR <= -5%
  screener_clause = {
      "scan_clause": (
          "( {cash} ( [0] latest close > [ -1 ] 1 day ago close * 1.05 or [0]"
          " latest close < [ -1 ] 1 day ago close * 0.95 ) )"
      )
  }

  try:
    resp = session.post(
        "https://chartink.com/screener/process",
        data=screener_clause,
        timeout=20,
    )
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
    p_change = float(item.get("per_chg", 0.0))
    close_price = float(item.get("close", 0.0))

    if not symbol:
      continue

    if p_change >= 5.0:
      gainers.append(
          f"🟢 *{symbol}*: +{p_change:.2f}% (LTP: ₹{close_price:.2f})"
      )
    elif p_change <= -5.0:
      losers.append(
          f"🔴 *{symbol}*: {p_change:.2f}% (LTP: ₹{close_price:.2f})"
      )

  # Sort by percentage change
  gainers.sort(
      key=lambda x: float(x.split("+")[1].split("%")[0]), reverse=True
  )
  losers.sort(
      key=lambda x: float(x.split(":")[1].split("%")[0].replace(" ", ""))
  )

  ist = pytz.timezone("Asia/Kolkata")
  now_str = datetime.now(ist).strftime("%d %b %Y, %I:%M %p")

  if gainers or losers:
    msg = (
        f"📊 *NSE Closing Movers Alert (±5%)*\n*Timestamp:* {now_str}\n*Total"
        f" Matches:* {len(gainers) + len(losers)} Stocks\n\n"
    )
    if gainers:
      msg += f"🚀 *Gainers ({len(gainers)}):*\n" + "\n".join(gainers) + "\n\n"
    if losers:
      msg += f"🔻 *Losers ({len(losers)}):*\n" + "\n".join(losers)
    send_telegram_alert(msg)
  else:
    send_telegram_alert(
        f"ℹ️ *Market Close ({now_str})*\nNo equities across the cash market"
        " moved beyond ±5% today."
    )


if __name__ == "__main__":
  scan_entire_nse_market()
