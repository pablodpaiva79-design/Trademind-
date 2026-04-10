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
# TEMPO / MODOS
# ========================
def tempo_por_horario():
    hora = datetime.now().hour

    if 13 <= hora <= 18:
        return 10
    elif 9 <= hora < 13 or 18 < hora <= 22:
        return 20
    else:
        return 60


def modo_madrugada():
    return 0 <= datetime.now().hour <= 6


def rotina_madrugada():
    conn = conectar()
    c = conn.cursor()

    c.execute("DELETE FROM trades WHERE hora < datetime('now', '-2 days')")

    conn.commit()
    conn.close()

    print("🌙 manutenção ok")


# ========================
# BASE
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
# PROTEÇÃO
# ========================
def protecao_sistema():
    lucro = resultado_dia()

    if lucro <= STOP_DIA * BANCA:
        return "STOP_DIA"

    conn = conectar()
    c = conn.cursor()

    hoje = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
    SELECT resultado FROM trades
    WHERE DATE(hora)=?
    ORDER BY hora DESC
    LIMIT 5
    """, (hoje,))
    ultimos = c.fetchall()
    conn.close()

    loss_seq = 0
    for r in ultimos:
        if r[0] == "LOSS":
            loss_seq += 1
        else:
            break

    if loss_seq >= 3:
        return "PAUSA"

    return "OK"


def tem_trade_aberto():
    return trades_abertos() > 0


# ========================
# GESTÃO ATIVA
# ========================
def gerenciar_trades():
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    SELECT id, par, entrada, stop, alvo, valor, hora
    FROM trades
    WHERE resultado IS NULL
    """)

    trades = c.fetchall()

    for t in trades:
        trade_id, par, entrada, stop, alvo, valor, hora = t

        p = preco(par)
        if not p:
            continue

        tempo_aberto = (datetime.now() - datetime.strptime(hora, "%Y-%m-%d %H:%M:%S")).seconds

        if tempo_aberto > 600:
            print(f"⏳ encerrado por tempo {par}")
            c.execute("UPDATE trades SET resultado='LOSS' WHERE id=?", (trade_id,))
            continue

        if p < entrada * 0.995:
            print(f"⚠️ saída antecipada {par}")
            c.execute("UPDATE trades SET resultado='LOSS' WHERE id=?", (trade_id,))
            continue

        if p > entrada * 1.01:
            novo_stop = p * 0.995
            if novo_stop > stop:
                c.execute("UPDATE trades SET stop=? WHERE id=?", (novo_stop, trade_id))

    conn.commit()
    conn.close()


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
# PREÇO
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

    for t in trades:
        id_, par, entrada, alvo, stop, valor = t

        p = preco(par)
        if not p:
            continue

        if p >= alvo:
            c.execute("UPDATE trades SET resultado='WIN' WHERE id=?", (id_,))
            print(f"✅ WIN {par} | {entrada} → {alvo}")

        elif p <= stop:
            c.execute("UPDATE trades SET resultado='LOSS' WHERE id=?", (id_,))
            print(f"❌ LOSS {par} | {entrada} → {stop}")

    conn.commit()
    conn.close()


# ========================
# LOOP
# ========================
def main():
    criar_tabela()

    while True:
        try:
            # madrugada
            if modo_madrugada():
                rotina_madrugada()
                time.sleep(300)
                continue

            status = protecao_sistema()

            if status == "STOP_DIA":
                time.sleep(86400)
                continue

            if status == "PAUSA":
                time.sleep(1800)
                continue

            if pode_entrar():
                ops = gerar_oportunidades()

                for t in ops:
                    t["valor"] = valor_trade()
                    salvar(t)
                    criar_card(t)

                    print(f"📥 NOVO TRADE {t['par']} | {t['entrada']} → {t['alvo']}")

            analisar()
            gerenciar_trades()

            base = tempo_por_horario()

            if tem_trade_aberto():
                tempo = max(5, base // 2)
            else:
                tempo = base

            time.sleep(tempo)

        except Exception as e:
            print("Erro:", e)
            time.sleep(60)


if __name__ == "__main__":
    main()

