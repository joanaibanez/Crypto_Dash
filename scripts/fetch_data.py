#!/usr/bin/env python3
"""Baixa o histórico diário das criptomoedas no Yahoo Finance e grava data/crypto.json.

O Yahoo não tem API oficial e bloqueia chamadas do navegador (CORS), por isso os
dados são coletados aqui, no GitHub Actions, e servidos como arquivo estático pelo
GitHub Pages. Usa o yfinance, que imita um navegador (TLS + cookie/crumb); com
urllib puro o Yahoo responde 429.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

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
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "crypto.json"


def fetch(symbol):
    last_error = None
    for attempt in range(3):
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=RANGE, interval=INTERVAL, auto_adjust=False, raise_errors=True)
            history = history.dropna(subset=["Close"])
            if history.empty:
                raise ValueError("série vazia")
            return ticker.history_metadata or {}, history
        except Exception as error:
            last_error = error
            time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"{symbol}: {last_error}")


def parse(meta, history):
    # Yahoo às vezes repete o candle do dia corrente; mantém o último por data.
    history = history[~history.index.strftime("%Y-%m-%d").duplicated(keep="last")]
    return {
        "meta": {
            "currency": meta.get("currency"),
            "price": meta.get("regularMarketPrice"),
            "time": meta.get("regularMarketTime"),
            "high52w": meta.get("fiftyTwoWeekHigh"),
            "low52w": meta.get("fiftyTwoWeekLow"),
            "volume": meta.get("regularMarketVolume"),
        },
        "dates": list(history.index.strftime("%Y-%m-%d")),
        "close": [round(float(x), 6) for x in history["Close"]],
        "high": [round(float(x), 6) for x in history["High"].fillna(history["Close"])],
        "low": [round(float(x), 6) for x in history["Low"].fillna(history["Close"])],
        "volume": [int(x) for x in history["Volume"].fillna(0)],
    }


def main():
    assets = []
    failures = 0
    for asset in ASSETS:
        entry = dict(asset)
        try:
            entry.update(parse(*fetch(asset["symbol"])))
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
        "source": "Yahoo Finance",
        "range": RANGE,
        "interval": INTERVAL,
        "assets": assets,
    }
    OUTPUT.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    print(f"Gravado {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
