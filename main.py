import sqlite3
import requests
import time
import os
from datetime import datetime

print("===== TRADEMIND SYSTEM =====")

DB = "trademind.db"
PASTA = "cards"

RISCO = 0.02
MAX_ABERTOS = 5
STOP_DIA = -0.05
GAIN_DIA = 0.08
BANCA = 1000

INTERVALO = 300  # 5 minutos


# ========================
# SETUP
# ========================
if not os.path.exists(PASTA):
    os.makedirs(PASTA)


def conectar():
    return sqlite3.connect(DB)


def criar_tabela():
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        par TEXT,
        entrada REAL,
        alvo REAL,
        stop REAL,
        hora TEXT,
        resultado TEXT,
        score REAL,
        valor REAL
    )
    """)

    conn.commit()
    conn.close()


# ========================
# GESTÃO
# ========================
def resultado_dia():
    conn = conectar()
    c = conn.cursor()

    hoje = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT entrada, alvo, stop, resultado, valor FROM trades WHERE DATE(hora)=?", (hoje,))
    dados = c.fetchall()

    conn.close()

    total = 0
    for e, a, s, r, v in dados:
        if r == "WIN":
            total += ((a - e) / e) * v
        elif r == "LOSS":
            total -= ((e - s) / e) * v

    return total


def trades_abertos():
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM trades WHERE resultado IS NULL")
    n = c.fetchone()[0]
    conn.close()
    return n


def pode_entrar():
    lucro = resultado_dia()

    if lucro <= STOP_DIA * BANCA:
        return False

    if lucro >= GAIN_DIA * BANCA:
        return False

    if trades_abertos() >= MAX_ABERTOS:
        return False

    return True


def valor_trade():
    return BANCA * RISCO


# ========================
# TRADEMIND
# ========================
def gerar_oportunidades():
    return [
        {
            "par": "AVAXUSDT",
            "entrada": 35,
            "alvo": 36,
            "stop": 34,
            "score": 0.7,
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    ]


def salvar(t):
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    INSERT INTO trades (par, entrada, alvo, stop, hora, resultado, score, valor)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        t["par"], t["entrada"], t["alvo"], t["stop"],
        t["hora"], None, t["score"], t["valor"]
    ))

    conn.commit()
    conn.close()


def criar_card(t):
    nome = f"{PASTA}/{t['par']}_{int(time.time())}.txt"

    with open(nome, "w") as f:
        f.write(f"""
PAR: {t['par']}
ENTRADA: {t['entrada']}
ALVO: {t['alvo']}
STOP: {t['stop']}
SCORE: {t['score']}
VALOR: {t['valor']}
HORA: {t['hora']}
""")


# ========================
# PREÇO REAL
# ========================
def preco(par):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={par}"
        return float(requests.get(url, timeout=5).json()["price"])
    except:
        return None


# ========================
# ANALISAR
# ========================
def analisar():
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id, par, entrada, alvo, stop, valor FROM trades WHERE resultado IS NULL")
    trades = c.fetchall()

    win = 0
    loss = 0

    for t in trades:
        id_, par, entrada, alvo, stop, valor = t

        p = preco(par)
        if not p:
            continue

        if p >= alvo:
            c.execute("UPDATE trades SET resultado='WIN' WHERE id=?", (id_,))
            win += 1

        elif p <= stop:
            c.execute("UPDATE trades SET resultado='LOSS' WHERE id=?", (id_,))
            loss += 1

    conn.commit()
    conn.close()

    return win, loss


# ========================
# RELATÓRIO
# ========================
def relatorio():
    conn = conectar()
    c = conn.cursor()

    hoje = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT resultado FROM trades WHERE DATE(hora)=?", (hoje,))
    dados = c.fetchall()

    total = len(dados)
    win = sum(1 for d in dados if d[0] == "WIN")
    loss = sum(1 for d in dados if d[0] == "LOSS")
    aberto = sum(1 for d in dados if d[0] is None)

    print("\n===== RELATÓRIO =====")
    print("Total:", total)
    print("WIN:", win)
    print("LOSS:", loss)
    print("Abertos:", aberto)

    if total > 0:
        print("Winrate:", round(win / total * 100, 2), "%")

    conn.close()
def gestor_status():
    conn = conectar()
    c = conn.cursor()

    hoje = datetime.now().strftime("%Y-%m-%d")

    c.execute("""
    SELECT entrada, alvo, stop, resultado, valor
    FROM trades
    WHERE DATE(hora)=?
    """, (hoje,))
    dados = c.fetchall()

    c.execute("SELECT resultado FROM trades")
    hist = c.fetchall()

    conn.close()

    total = len(dados)
    win = sum(1 for d in dados if d[3] == "WIN")
    loss = sum(1 for d in dados if d[3] == "LOSS")
    aberto = sum(1 for d in dados if d[3] is None)

    lucro = 0
    for e, a, s, r, v in dados:
        if r == "WIN":
            lucro += ((a - e) / e) * v
        elif r == "LOSS":
            lucro -= ((e - s) / e) * v

    total_hist = len(hist)
    win_hist = sum(1 for h in hist if h[0] == "WIN")

    print("\n===== GESTOR STATUS =====")
    print("Hoje:")
    print("Trades:", total)
    print("WIN:", win)
    print("LOSS:", loss)
    print("Abertos:", aberto)

    if total > 0:
        print("Winrate:", round(win/total*100, 2), "%")

    print("Lucro dia:", round(lucro, 2))

    print("\nHistórico:")
    print("Total:", total_hist)
    if total_hist > 0:
        print("Winrate geral:", round(win_hist/total_hist*100, 2), "%")



# ========================
# LOOP
# ========================
def main():
    criar_tabela()

    print("\nSistema iniciado...\n")

    while True:
        try:
            print("🔎 Analisando mercado...")

            if pode_entrar():
                ops = gerar_oportunidades()

                for t in ops:
                    t["valor"] = valor_trade()
                    salvar(t)
                    criar_card(t)

                print(f"{len(ops)} trade(s) criado(s)")

            w, l = analisar()

            if w or l:
                print(f"Resultado parcial → WIN: {w} | LOSS: {l}")

            relatorio()
            gestor_status()

            print("\n⏳ Aguardando...\n")
            time.sleep(INTERVALO)

        except Exception as e:
            print("Erro:", e)
            time.sleep(60)


if __name__ == "__main__":
    main()
