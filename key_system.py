import sqlite3
import secrets
import string
import hashlib
import csv
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict

DB_NAME = "keys.db"

VALIDADES = {
    "6h": timedelta(hours=6),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            hash TEXT NOT NULL,
            validade TEXT NOT NULL,
            criada_em TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            usada INTEGER DEFAULT 0,
            usada_em TEXT,
            usada_por INTEGER,
            usos_maximos INTEGER DEFAULT 1,
            usos_atuais INTEGER DEFAULT 0,
            ip_vinculado TEXT,
            nota TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acessos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            user_id INTEGER,
            ip TEXT,
            sucesso INTEGER,
            mensagem TEXT,
            data_hora TEXT NOT NULL
        )
    """)
    
    try:
        cursor.execute("ALTER TABLE keys ADD COLUMN ip_vinculado TEXT")
    except:
        pass
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado.")

def get_connection():
    return sqlite3.connect(DB_NAME)

def registrar_acesso(key: str, user_id: int = None, ip: str = None, sucesso: bool = False, mensagem: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO acessos (key, user_id, ip, sucesso, mensagem, data_hora)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        key.upper() if key else None,
        user_id,
        ip,
        1 if sucesso else 0,
        mensagem,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def gerar_key_string(prefixo="TG", blocos=4, tamanho=4) -> str:
    caracteres = string.ascii_uppercase + string.digits
    caracteres = caracteres.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    partes = [''.join(secrets.choice(caracteres) for _ in range(tamanho)) for _ in range(blocos)]
    return f"{prefixo}-{'-'.join(partes)}"

def criar_key(validade: str = "7d", usos_maximos: int = 1, nota: str = None, ip: str = None) -> Dict:
    if validade not in VALIDADES:
        raise ValueError(f"Validade inválida. Use: {list(VALIDADES.keys())}")
    
    key = gerar_key_string()
    hash_key = hashlib.sha256(key.encode()).hexdigest()
    agora = datetime.now()
    expira_em = agora + VALIDADES[validade]
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO keys (key, hash, validade, criada_em, expira_em, usos_maximos, ip_vinculado, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        key, hash_key, validade,
        agora.strftime("%Y-%m-%d %H:%M:%S"),
        expira_em.strftime("%Y-%m-%d %H:%M:%S"),
        usos_maximos, ip, nota
    ))
    conn.commit()
    key_id = cursor.lastrowid
    conn.close()
    
    return {
        "id": key_id,
        "key": key,
        "validade": validade,
        "criada_em": agora.strftime("%Y-%m-%d %H:%M:%S"),
        "expira_em": expira_em.strftime("%Y-%m-%d %H:%M:%S"),
        "usos_maximos": usos_maximos,
        "ip_vinculado": ip
    }

def validar_key(key: str, user_id: int = None, ip: str = None) -> Dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key = ?", (key.upper(),))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        registrar_acesso(key, user_id, ip, False, "Key não encontrada")
        return {"valida": False, "mensagem": "❌ Key não encontrada."}
    
    dados = {
        "id": row[0],
        "key": row[1],
        "validade": row[3],
        "criada_em": row[4],
        "expira_em": row[5],
        "usada": bool(row[6]),
        "usada_em": row[7],
        "usada_por": row[8],
        "usos_maximos": row[9],
        "usos_atuais": row[10],
        "ip_vinculado": row[11],
        "nota": row[12]
    }
    
    expira = datetime.strptime(dados["expira_em"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expira:
        conn.close()
        registrar_acesso(key, user_id, ip, False, "Key expirada")
        return {"valida": False, "mensagem": "⏰ Key expirada."}
    
    if dados["usos_atuais"] >= dados["usos_maximos"]:
        conn.close()
        registrar_acesso(key, user_id, ip, False, "Key sem usos restantes")
        return {"valida": False, "mensagem": "🚫 Key já foi totalmente utilizada."}
    
    if dados["ip_vinculado"]:
        if not ip:
            conn.close()
            registrar_acesso(key, user_id, ip, False, "IP necessário")
            return {
                "valida": False,
                "mensagem": "🔒 Esta key está vinculada a um IP.\nEnvie seu IP para validar.",
                "precisa_ip": True
            }
        if ip.strip() != dados["ip_vinculado"]:
            conn.close()
            registrar_acesso(key, user_id, ip, False, f"IP não autorizado ({ip})")
            return {"valida": False, "mensagem": "🚫 IP não autorizado para esta key."}
    
    novos_usos = dados["usos_atuais"] + 1
    usada = 1 if novos_usos >= dados["usos_maximos"] else 0
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    novo_ip = dados["ip_vinculado"] or ip
    
    cursor.execute("""
        UPDATE keys 
        SET usos_atuais = ?, usada = ?, usada_em = ?, usada_por = ?, ip_vinculado = ?
        WHERE id = ?
    """, (novos_usos, usada, agora, user_id, novo_ip, dados["id"]))
    conn.commit()
    conn.close()
    
    registrar_acesso(key, user_id, novo_ip, True, f"Ativada com sucesso ({novos_usos}/{dados['usos_maximos']})")
    
    return {
        "valida": True,
        "mensagem": f"✅ Key ativada com sucesso! ({novos_usos}/{dados['usos_maximos']} usos)",
        "dados": dados,
        "ip_vinculado": novo_ip
    }

def listar_acessos(limite: int = 30, key: str = None, user_id: int = None, ip: str = None) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM acessos WHERE 1=1"
    params = []
    if key:
        query += " AND key = ?"
        params.append(key.upper())
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if ip:
        query += " AND ip = ?"
        params.append(ip)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        "id": row[0],
        "key": row[1],
        "user_id": row[2],
        "ip": row[3],
        "sucesso": bool(row[4]),
        "mensagem": row[5],
        "data_hora": row[6]
    } for row in rows]

def listar_keys(apenas_ativas: bool = False) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if apenas_ativas:
        cursor.execute("""
            SELECT * FROM keys 
            WHERE usada = 0 AND datetime(expira_em) > datetime('now')
            ORDER BY id DESC
        """)
    else:
        cursor.execute("SELECT * FROM keys ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        "id": row[0],
        "key": row[1],
        "validade": row[3],
        "criada_em": row[4],
        "expira_em": row[5],
        "usada": bool(row[6]),
        "usada_por": row[8],
        "usos": f"{row[10]}/{row[9]}",
        "ip_vinculado": row[11],
        "nota": row[12]
    } for row in rows]

def deletar_key(key: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keys WHERE key = ?", (key.upper(),))
    afetadas = cursor.rowcount
    conn.commit()
    conn.close()
    return afetadas > 0

def limpar_logs(dias: int = 30) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM acessos 
        WHERE datetime(data_hora) < datetime('now', ?)
    """, (f"-{dias} days",))
    afetadas = cursor.rowcount
    conn.commit()
    conn.close()
    return afetadas

def exportar_logs_csv(caminho: str = None, key: str = None, user_id: int = None, ip: str = None) -> str:
    if caminho is None:
        caminho = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    acessos = listar_acessos(limite=10000, key=key, user_id=user_id, ip=ip)
    with open(caminho, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Key", "User ID", "IP", "Sucesso", "Mensagem", "Data/Hora"])
        for a in acessos:
            writer.writerow([
                a["id"], a["key"] or "", a["user_id"] or "", a["ip"] or "",
                "Sim" if a["sucesso"] else "Não", a["mensagem"] or "", a["data_hora"]
            ])
    return caminho

def exportar_logs_txt(caminho: str = None, key: str = None, user_id: int = None, ip: str = None) -> str:
    if caminho is None:
        caminho = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    acessos = listar_acessos(limite=10000, key=key, user_id=user_id, ip=ip)
    with open(caminho, mode="w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("       LOG DE ACESSOS - SISTEMA DE KEYS\n")
        f.write(f"       Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        if not acessos:
            f.write("Nenhum registro encontrado.\n")
        else:
            for a in acessos:
                status = "SUCESSO" if a["sucesso"] else "FALHA"
                f.write(f"[{a['data_hora']}] {status}\n")
                f.write(f"  Key     : {a['key'] or '—'}\n")
                f.write(f"  User ID : {a['user_id'] or '—'}\n")
                f.write(f"  IP      : {a['ip'] or '—'}\n")
                f.write(f"  Mensagem: {a['mensagem'] or '—'}\n")
                f.write("-" * 40 + "\n")
        f.write(f"\nTotal de registros: {len(acessos)}\n")
    return caminho
