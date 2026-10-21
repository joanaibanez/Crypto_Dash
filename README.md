# Crypto Dash

Dashboard estático que compara Bitcoin, Ethereum, Solana, USD1 e Tether com dados diários do Yahoo Finance, publicado no GitHub Pages.

## Como funciona

O Yahoo Finance não tem API oficial e o endpoint usado (`/v8/finance/chart`) **bloqueia chamadas feitas direto do navegador (CORS)**. Por isso:

1. `scripts/fetch_data.py` (Python + `yfinance`) baixa 2 anos de candles diários e grava `data/crypto.json`.
2. O workflow `.github/workflows/deploy.yml` roda esse script **a cada hora**, a cada push na `main` e manualmente, e publica `index.html` + `data/crypto.json` no GitHub Pages.
3. O `index.html` lê o JSON e calcula tudo no navegador (Chart.js).

Se um ativo falhar no Yahoo, ele aparece como "Indisponível" e os demais seguem normais. Se todos falharem, o deploy é abortado e a versão anterior continua no ar.

## O que o dashboard mostra

- Cards com preço atual e variação de 24h / 7d / 30d
- Desempenho relativo (base 100), preço + volume por ativo
- Métricas por período (1M a 2A): retorno total e anualizado, volatilidade, Sharpe, Sortino, drawdown máximo, melhor/pior dia, volume médio, desvio da paridade (stablecoins)
- Gráfico risco × retorno, drawdown, volatilidade móvel de 30 dias, paridade das stablecoins
- Simulador: aporte único ou mensal (DCA)
- Matriz de correlação dos retornos diários

Aba **Análise** (`#analise`):

- Leitura técnica: tendência (preço × médias de 50/200 dias), momentum, regime de volatilidade, distância do topo, Sharpe e queda máxima em 1 ano
- Paridade das stablecoins e cenários de estresse (pior/melhor janela de 30 dias aplicada a um valor hipotético)
- Leitura por objetivo gerada a partir dos números atuais
- Contexto de mercado escrito à mão, datado e com fontes (constante `CONTEXT` no `index.html`). A página avisa quando ele passa de 14 dias; atualize o texto e a data para renová-lo.

A aba descreve o comportamento passado; não prevê preço nem recomenda compra.

## Deploy no GitHub Pages

1. Faça merge desta branch na `main`.
2. No repositório: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Em **Actions**, rode "Atualizar dados e publicar no GitHub Pages" (ou faça um push na `main`).
4. O site fica em `https://<usuario>.github.io/<repositorio>/`.

## Rodar localmente

```bash
pip install -r requirements.txt
python scripts/fetch_data.py
python -m http.server 8000
# abra http://localhost:8000
```

Abrir o `index.html` direto pelo `file://` não funciona: o navegador bloqueia o `fetch` do JSON.

## Trocar ativos

Edite a lista `ASSETS` no topo de `scripts/fetch_data.py` (o dashboard se adapta sozinho). Confira o ticker em finance.yahoo.com antes, por exemplo `USDC-USD` para USD Coin.

> Informativo, não é recomendação de investimento.
