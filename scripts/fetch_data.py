#!/usr/bin/env python3
"""Baixa o histórico diário das criptomoedas no Yahoo Finance e grava data/crypto.json.

Usa apenas a biblioteca padrão. O endpoint v8/chart do Yahoo não é oficial e
não aceita chamadas do navegador (CORS), por isso os dados são coletados aqui,
no GitHub Actions, e servidos como arquivo estático pelo GitHub Pages.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Para trocar/adicionar ativos, edite somente esta lista.
ASSETS = [
    {"key": "BTC", "name": "Bitcoin", "symbol": "BTC-USD", "type": "crypto", "color": "#F7931A"},
    {"key": "ETH", "name": "Ethereum", "symbol": "ETH-USD", "type": "crypto", "color": "#627EEA"},
    {"key": "SOL", "name": "Solana", "symbol": "SOL-USD", "type": "crypto", "color": "#9945FF"},
    {"key": "USD1", "name": "USD1 (World Liberty)", "symbol": "USD1-USD", "type": "stablecoin", "color": "#E5484D"},
    {"key": "USDT", "name": "Tether", "symbol": "USDT-USD", "type": "stablecoin", "color": "#26A17B"},
]

RANGE = "2y"
INTERVAL = "1d"
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "crypto.json"


def fetch_chart(symbol):
    params = urllib.parse.urlencode(
        {"range": RANGE, "interval": INTERVAL, "includePrePost": "false", "events": "history"}
    )
    last_error = None
    for attempt in range(3):
        for host in HOSTS:
            url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol)}?{params}"
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.load(response)
                chart = payload.get("chart") or {}
                if chart.get("error"):
                    raise ValueError(chart["error"].get("description") or str(chart["error"]))
                result = (chart.get("result") or [None])[0]
                if not result:
                    raise ValueError("resposta sem dados")
                return result
            except (urllib.error.URLError, ValueError, TimeoutError) as error:
                last_error = error
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{symbol}: {last_error}")


def parse_chart(result):
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    offset = meta.get("gmtoffset") or 0

    def column(name):
        values = quote.get(name) or []
        return values + [None] * (len(timestamps) - len(values))

    closes, highs, lows, volumes = column("close"), column("high"), column("low"), column("volume")

    # Yahoo às vezes repete o candle do dia corrente; o dicionário mantém o último.
    rows = {}
    for i, ts in enumerate(timestamps):
        if closes[i] is None:
            continue
        day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date().isoformat()
        rows[day] = (
            closes[i],
            highs[i] if highs[i] is not None else closes[i],
            lows[i] if lows[i] is not None else closes[i],
            volumes[i] or 0,
        )

    dates = sorted(rows)
    return {
        "meta": {
            "currency": meta.get("currency"),
            "price": meta.get("regularMarketPrice"),
            "time": meta.get("regularMarketTime"),
            "high52w": meta.get("fiftyTwoWeekHigh"),
            "low52w": meta.get("fiftyTwoWeekLow"),
            "volume": meta.get("regularMarketVolume"),
        },
        "dates": dates,
        "close": [round(rows[d][0], 6) for d in dates],
        "high": [round(rows[d][1], 6) for d in dates],
        "low": [round(rows[d][2], 6) for d in dates],
        "volume": [int(rows[d][3]) for d in dates],
    }


def main():
    assets = []
    failures = 0
    for asset in ASSETS:
        entry = dict(asset)
        try:
            entry.update(parse_chart(fetch_chart(asset["symbol"])))
            if not entry["dates"]:
                raise RuntimeError(f"{asset['symbol']}: série vazia")
            entry["error"] = None
            print(f"ok   {asset['symbol']:<10} {len(entry['dates'])} dias", file=sys.stderr)
        except Exception as error:  # um ativo com falha não derruba os demais
            failures += 1
            entry.update({"meta": {}, "dates": [], "close": [], "high": [], "low": [], "volume": []})
            entry["error"] = str(error)
            print(f"erro {asset['symbol']:<10} {error}", file=sys.stderr)
        assets.append(entry)

    if failures == len(ASSETS):
        print("Nenhum ativo foi baixado; arquivo não atualizado.", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance (v8/finance/chart)",
        "range": RANGE,
        "interval": INTERVAL,
        "assets": assets,
    }
    OUTPUT.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    print(f"Gravado {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
