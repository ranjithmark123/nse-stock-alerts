import os
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_alert(message: str):
  """Sends notification chunks to avoid Telegram 4096 character limits."""
  if not BOT_TOKEN or not CHAT_ID:
    print("❌ ERROR: Telegram secrets are missing.")
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


def scan_entire_nse_market():
  print("Scanning all Indian Equities across NSE...")

  session = requests.Session()
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "X-Requested-With": "XMLHttpRequest",
  }
  session.headers.update(headers)

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
    result = resp.json()
    stocks = result.get("data", [])
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

  # Sort by percentage magnitude
  gainers.sort(
      key=lambda x: float(x.split("+")[1].split("%")[0]), reverse=True
  )
  losers.sort(
      key=lambda x: float(x.split(":")[1].split("%")[0].replace(" ", ""))
  )

  print(
      f"Scan completed successfully. Found {len(gainers)} Gainers and"
      f" {len(losers)} Losers."
  )

  if gainers or losers:
    msg = f"📊 *NSE Full Market Alert (±5%)*\n*Total Matches:* {len(gainers) + len(losers)} Stocks\n\n"
    if gainers:
      msg += f"🚀 *Gainers ({len(gainers)}):*\n" + "\n".join(gainers) + "\n\n"
    if losers:
      msg += f"🔻 *Losers ({len(losers)}):*\n" + "\n".join(losers)
    send_telegram_alert(msg)
  else:
    send_telegram_alert(
        "ℹ️ Market Scan Complete: No stocks moved beyond ±5% right now."
    )


if __name__ == "__main__":
  scan_entire_nse_market()
