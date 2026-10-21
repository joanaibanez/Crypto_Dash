#!/usr/bin/env python3
"""Abre o site montado (_site) num Chrome headless e confere se o dashboard renderiza com os dados reais."""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(sys.argv[1] if len(sys.argv) > 1 else "_site").resolve()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    data = json.loads(
        (SITE / "data" / "crypto.json").read_text(encoding="utf-8"),
        parse_constant=lambda c: sys.exit(f"JSON inválido para o navegador: contém {c}"),
    )
    expected = len(data["assets"])

    handler = functools.partial(QuietHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: problems.append(f"erro JS: {e}"))
        page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text}"))
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        error_box = page.inner_text("#error").strip()
        if error_box:
            problems.append(f"aviso na página: {error_box}")
        cards = page.locator("#cards .card")
        if cards.count() != expected:
            problems.append(f"{cards.count()} cards renderizados, esperado {expected}")
        for i in range(cards.count()):
            print("card:", " | ".join(cards.nth(i).inner_text().split("\n")[:3]))
        rows = page.locator("#metrics tbody tr").count()
        if rows == 0:
            problems.append("tabela de métricas vazia")
        print("atualizado:", page.inner_text("#updated"))
        browser.close()
    server.shutdown()

    for problem in problems:
        print("FALHA:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
