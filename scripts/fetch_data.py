#!/usr/bin/env python3
"""Baixa o histórico diário das criptomoedas no Yahoo Finance e grava data/crypto.json.

O Yahoo não tem API oficial e bloqueia chamadas do navegador (CORS), por isso os
dados são coletados aqui, no GitHub Actions, e servidos como arquivo estático pelo
GitHub Pages. Usa o yfinance, que imita um navegador (TLS + cookie/crumb); com
urllib puro o Yahoo responde 429.
"""
import json
import math
import sys
import time
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yfinance as yf
from statsmodels.tsa.arima.model import ARIMA

# Para trocar/adicionar ativos, edite somente esta lista.
ASSETS = [
    {"key": "BTC", "name": "Bitcoin", "symbol": "BTC-USD", "type": "crypto", "color": "#F7931A"},
    {"key": "ETH", "name": "Ethereum", "symbol": "ETH-USD", "type": "crypto", "color": "#627EEA"},
    {"key": "SOL", "name": "Solana", "symbol": "SOL-USD", "type": "crypto", "color": "#9945FF"},
    {"key": "USDT", "name": "Tether", "symbol": "USDT-USD", "type": "stablecoin", "color": "#26A17B"},
    {"key": "USDC", "name": "USD Coin", "symbol": "USDC-USD", "type": "stablecoin", "color": "#E5484D"},
]

RANGE = "2y"
INTERVAL = "1d"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "crypto.json"

# Projeção ARIMA sobre o log do preço: ordem (p,1,q) escolhida por AIC.
HORIZON = 30
ORDERS = [(p, 1, q) for p in range(3) for q in range(3)]
BACKTEST_FOLDS = 8
TRAIN_DAYS = 730

yf.config.debug.hide_exceptions = False  # falhas viram exceção em vez de DataFrame vazio


def fetch(symbol, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=RANGE, interval=INTERVAL, auto_adjust=False)
            history = history.dropna(subset=["Close"])
            if history.empty:
                raise ValueError("série vazia")
            return ticker.history_metadata or {}, history
        except Exception as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"{symbol}: {last_error}")


def search_symbols(asset):
    """Tickers alternativos: o Yahoo acrescenta um número quando o código colide (ex.: UNI7083-USD)."""
    try:
        quotes = yf.Search(asset["key"], max_results=15, news_count=0, lists_count=0).quotes
    except Exception as error:
        print(f"     busca por {asset['key']} falhou: {error}", file=sys.stderr)
        return []
    return [
        q["symbol"] for q in quotes
        if q.get("quoteType") == "CRYPTOCURRENCY"
        and q.get("symbol", "").startswith(asset["key"])
        and q["symbol"].endswith("-USD")
        and q["symbol"] != asset["symbol"]
    ]


def fetch_asset(asset):
    try:
        return asset["symbol"], fetch(asset["symbol"])
    except RuntimeError as error:
        candidates = search_symbols(asset)
        print(f"     {error}; candidatos na busca: {candidates or 'nenhum'}", file=sys.stderr)
        for symbol in candidates:
            try:
                return symbol, fetch(symbol, attempts=1)
            except RuntimeError:
                continue
        raise


def fit_arima(y, order):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # avisos de convergência são comuns e não invalidam o AIC
        return ARIMA(y, order=order, trend="n").fit()


def backtest(y, order):
    """Refaz a previsão de HORIZON dias em origens passadas e compara com repetir o último preço."""
    model_err, naive_err, hits, calls = [], [], 0, 0
    for k in range(BACKTEST_FOLDS, 0, -1):
        origin = len(y) - HORIZON * k
        train, actual = y[:origin], y[origin + HORIZON - 1]
        pred = fit_arima(train, order).forecast(HORIZON)[-1]
        model_err.append(abs(pred - actual))
        naive_err.append(abs(train[-1] - actual))
        if abs(pred - train[-1]) > 1e-4:  # o modelo apontou uma direção
            calls += 1
            hits += (pred > train[-1]) == (actual > train[-1])
    mae_model, mae_naive = float(np.mean(model_err)), float(np.mean(naive_err))
    return {
        "folds": BACKTEST_FOLDS,
        "mae_model": mae_model,
        "mae_naive": mae_naive,
        "ratio": mae_model / mae_naive if mae_naive > 0 else None,
        "direction_calls": calls,
        "direction_hits": int(hits),
    }


def forecast(dates, close):
    y = np.log(np.asarray(close[-TRAIN_DAYS:], dtype=float))
    if len(y) < HORIZON * (BACKTEST_FOLDS + 2):
        raise ValueError(f"histórico curto demais ({len(y)} dias)")
    fits = [(fit_arima(y, order), order) for order in ORDERS]
    result, order = min(fits, key=lambda f: f[0].aic)
    fc = result.get_forecast(HORIZON)
    mean, ci80, ci95 = fc.predicted_mean, fc.conf_int(alpha=0.2), fc.conf_int(alpha=0.05)
    start = date.fromisoformat(dates[-1])
    as_price = lambda values: [round(float(math.exp(v)), 6) for v in values]
    return {
        "order": list(order),
        "aic": round(float(result.aic), 2),
        "train_days": len(y),
        "dates": [(start + timedelta(days=i)).isoformat() for i in range(1, HORIZON + 1)],
        "mean": as_price(mean),
        "lo80": as_price(ci80[:, 0]), "hi80": as_price(ci80[:, 1]),
        "lo95": as_price(ci95[:, 0]), "hi95": as_price(ci95[:, 1]),
        "backtest": backtest(y, order),
    }


def plain(value):
    """Converte Timestamp/numpy do metadata do yfinance em tipos aceitos pelo JSON."""
    if hasattr(value, "timestamp"):
        return int(value.timestamp())
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # NaN/Infinity viram JSON inválido no navegador
    return value


def parse(meta, history):
    # Yahoo às vezes repete o candle do dia corrente; mantém o último por data.
    history = history[~history.index.strftime("%Y-%m-%d").duplicated(keep="last")]
    return {
        "meta": {
            "currency": plain(meta.get("currency")),
            "price": plain(meta.get("regularMarketPrice")),
            "time": plain(meta.get("regularMarketTime")),
            "high52w": plain(meta.get("fiftyTwoWeekHigh")),
            "low52w": plain(meta.get("fiftyTwoWeekLow")),
            "volume": plain(meta.get("regularMarketVolume")),
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
            symbol, (meta, history) = fetch_asset(asset)
            entry["symbol"] = symbol
            entry.update(parse(meta, history))
            if not entry["dates"]:
                raise RuntimeError(f"{asset['symbol']}: série vazia")
            entry["error"] = None
            print(f"ok   {entry['symbol']:<14} {len(entry['dates'])} dias", file=sys.stderr)
            try:  # a projeção é opcional: se falhar, os dados seguem publicados
                entry["forecast"] = forecast(entry["dates"], entry["close"])
                bt = entry["forecast"]["backtest"]
                print(f"     ARIMA{tuple(entry['forecast']['order'])} erro/ingênuo={bt['ratio']:.2f}", file=sys.stderr)
            except Exception as error:
                entry["forecast"] = None
                print(f"     ARIMA falhou: {error}", file=sys.stderr)
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
    OUTPUT.write_text(json.dumps(document, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"Gravado {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
