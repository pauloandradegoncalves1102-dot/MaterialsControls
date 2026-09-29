"""
Sistema de Controle de Materiais Cautelados
============================================
Gerencia bens apreendidos/sequestrados sob medidas cautelares.
Base legal: CPP arts. 118, 125-144-A; CPC art. 301.
"""

import sqlite3
from datetime import datetime, date
from enum import Enum
from typing import Optional

class TipoMedida(Enum):
    ARRESTO = "Arresto"
    SEQUESTRO = "Sequestro"
    BUSCA_APRENSAO = "Busca e Apreensão"
    ARROLAMENTO = "Arrolamento de Bens"
    HIPOTECA_LEGAL = "Hipoteca Legal"
    OUTRA = "Outra"

class StatusMaterial(Enum):
    APREENDIDO = "Apreendido"
    EM_CUSTODIA = "Em Custódia"
    EM_DEPOSITO = "Em Depósito (fiel depositário)"
    TRANSFERIDO = "Transferido"
    ALIENADO = "Alienado (antecipada)"
    RESTITUIDO = "Restituído"
    DESTRUIDO = "Destruido"
    CONFISCADO = "Confiscado"
    PERDIDO = "Perdido/Inutilizado"

class TipoBem(Enum):
    MOVEL = "Móvel"
    IMOVEL = "Imóvel"
    VEICULO = "Veículo"
    VALOR_DINHEIRO = "Valor em Dinheiro"
    SEMOVEL = "Semi-móvel"
    OUTRO = "Outro"


def parse_valor(s: str) -> float:
    """Converte strings como '30K', '1.5M', '2mi', '1000', 'R$ 5.000,00' em float."""
    s = s.strip().lower().replace("r$", "").replace(" ", "").replace("\xa0", "")
    if not s:
        return 0.0

    # Formata brasileiro: 1.000,50 -> 1000.50
    if "," in s:
        s = s.replace(".", "").replace(",", ".")

    multipliers = {"k": 1_000, "m": 1_000_000, "mi": 1_000_000}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return float(s[:-len(suffix)]) * mult

    try:
        return float(s)
    except ValueError:
        print("  ⚠️  Valor inválido, usando 0.0")
        return 0.0

DB_FILE = "materiais_cautelados.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS materiais (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_processo TEXT    NOT NULL,
        tipo_bem        TEXT    NOT NULL,
        descricao       TEXT    NOT NULL,
        tipo_medida     TEXT    NOT NULL,
        status          TEXT    NOT NULL DEFAULT 'Apreendido',
        localizacao     TEXT,
        custodiante     TEXT,
        fiel_depositario TEXT,
        valor_estimado  REAL    DEFAULT 0,
        data_apreensao  TEXT    NOT NULL,
        data_ultima_mov TEXT,
        observacoes     TEXT,
        criado_em       TEXT    NOT NULL,
        atualizado_em   TEXT
    );

    CREATE TABLE IF NOT EXISTS movimentacoes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        material_id     INTEGER NOT NULL,
        data            TEXT    NOT NULL,
        tipo_mov        TEXT    NOT NULL,
        de              TEXT,
        para            TEXT,
        responsavel     TEXT    NOT NULL,
        fundamento_legal TEXT,
        observacoes     TEXT,
        FOREIGN KEY (material_id) REFERENCES materiais(id)
    );

    CREATE INDEX IF NOT EXISTS idx_proc ON materiais(numero_processo);
    CREATE INDEX IF NOT EXISTS idx_status ON materiais(status);
    CREATE INDEX IF NOT EXISTS idx_mov_material ON movimentacoes(material_id);
    """)
    conn.commit()
    conn.close()


def cadastrar_material(
    numero_processo: str,
    tipo_bem: TipoBem,
    descricao: str,
    tipo_medida: TipoMedida,
    localizacao: str = "",
    custodiante: str = "",
    valor_estimado: float = 0.0,
    data_apreensao: Optional[str] = None,
    observacoes: str = "",
) -> int:
    conn = get_connection()
    agora = datetime.now().isoformat()
    data_ap = data_apreensao or date.today().isoformat()

    cur = conn.execute(
        """INSERT INTO materiais
           (numero_processo, tipo_bem, descricao, tipo_medida, status,
            localizacao, custodiante, valor_estimado, data_apreensao,
            observacoes, criado_em, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            numero_processo, tipo_bem.value, descricao, tipo_medida.value,
            StatusMaterial.APREENDIDO.value, localizacao, custodiante,
            valor_estimado, data_ap, observacoes, agora, agora,
        ),
    )
    material_id = cur.lastrowid

    conn.execute(
        """INSERT INTO movimentacoes
           (material_id, data, tipo_mov, de, para, responsavel, fundamento_legal)
           VALUES (?,?,?,?,?,?,?)""",
        (material_id, data_ap, "APREENSÃO", "", localizacao or "—",
         custodiante or "Sistema", "Art. 240-250 CPP / Art. 301 CPC"),
    )
    conn.commit()
    conn.close()
    return material_id


def atualizar_status(material_id: int, novo_status: StatusMaterial,
                     responsavel: str, fundamento: str = "",
                     observacoes: str = ""):
    conn = get_connection()
    agora = datetime.now().isoformat()

    conn.execute(
        "UPDATE materiais SET status=?, data_ultima_mov=?, atualizado_em=? WHERE id=?",
        (novo_status.value, agora, agora, material_id),
    )
    conn.execute(
        """INSERT INTO movimentacoes
           (material_id, data, tipo_mov, responsavel, fundamento_legal, observacoes)
           VALUES (?,?,?,?,?,?)""",
        (material_id, agora, f"MUDANÇA DE STATUS → {novo_status.value.upper()}",
         responsavel, fundamento, observacoes),
    )
    conn.commit()
    conn.close()


def registrar_movimentacao(
    material_id: int, tipo_mov: str, de: str, para: str,
    responsavel: str, fundamento: str = "", obs: str = "",
):
    conn = get_connection()
    agora = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO movimentacoes
           (material_id, data, tipo_mov, de, para, responsavel, fundamento_legal, observacoes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (material_id, agora, tipo_mov, de, para, responsavel, fundamento, obs),
    )
    conn.execute(
        "UPDATE materiais SET data_ultima_mov=?, atualizado_em=? WHERE id=?",
        (agora, agora, material_id),
    )
    conn.commit()
    conn.close()


def buscar_materiais(
    numero_processo: Optional[str] = None,
    status: Optional[StatusMaterial] = None,
    tipo_medida: Optional[TipoMedida] = None,
    descricao: Optional[str] = None,
) -> list:
    conn = get_connection()
    sql = "SELECT * FROM materiais WHERE 1=1"
    params = []

    if numero_processo:
        sql += " AND numero_processo LIKE ?"
        params.append(f"%{numero_processo}%")
    if status:
        sql += " AND status = ?"
        params.append(status.value)
    if tipo_medida:
        sql += " AND tipo_medida = ?"
        params.append(tipo_medida.value)
    if descricao:
        sql += " AND descricao LIKE ?"
        params.append(f"%{descricao}%")

    sql += " ORDER BY id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obter_historico(material_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM movimentacoes WHERE material_id=? ORDER BY data DESC",
        (material_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def relatorio_resumo() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM materiais").fetchone()[0]
    por_status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM materiais GROUP BY status"
    ).fetchall())
    por_medida = dict(conn.execute(
        "SELECT tipo_medida, COUNT(*) FROM materiais GROUP BY tipo_medida"
    ).fetchall())
    valor_total = conn.execute(
        "SELECT COALESCE(SUM(valor_estimado),0) FROM materiais"
    ).fetchone()[0]
    conn.close()
    return {
        "total_materiais": total,
        "por_status": por_status,
        "por_tipo_medida": por_medida,
        "valor_total_estimado": valor_total,
    }


def _print_materiais(materiais: list):
    if not materiais:
        print("  (nenhum material encontrado)")
        return
    print(f"\n  {'ID':<5}{'Processo':<22}{'Tipo':<12}{'Medida':<22}{'Status':<20}{'Valor (R$)':>12}")
    print("  " + "─" * 93)
    for m in materiais:
        print(
            f"  {m['id']:<5}{m['numero_processo']:<22}"
            f"{m['tipo_bem']:<12}{m['tipo_medida']:<22}"
            f"{m['status']:<20}{m['valor_estimado']:>12,.2f}"
        )


def menu():
    init_db()
    print("\n╔══════════════════════════════════════════════════╗")
    print("║   SISTEMA DE CONTROLE – MATERIAIS CAUTELADOS    ║")
    print("╚══════════════════════════════════════════════════╝\n")

    while True:
        print("  [1] Cadastrar material")
        print("  [2] Buscar materiais")
        print("  [3] Atualizar status")
        print("  [4] Registrar movimentação")
        print("  [5] Histórico de um material")
        print("  [6] Relatório resumo")
        print("  [0] Sair")
        op = input("\n  Escolha: ").strip()

        if op == "1":
            print("\n  ── CADASTRO DE MATERIAL ──")
            proc = input("  Nº do processo: ").strip()
            tb = input("  Tipo de bem (movel/imovel/veiculo/valor/semovel/outro): ").strip().lower()
            desc = input("  Descrição: ").strip()
            tm = input("  Tipo de medida (arresto/sequestro/busca_arrepsao/arrolamento/hipotca/outra): ").strip().lower()
            loc = input("  Localização: ").strip()
            cust = input("  Custodiante: ").strip()
            val = input("  Valor estimado (R$) – ex: 30K, 1.5M, 1000: ").strip()
            obs = input("  Observações: ").strip()

            tipo_bem = TipoBem(tb) if tb in [t.value for t in TipoBem] else TipoBem.OUTRO
            tipo_medida = TipoMedida(tm) if tm in [t.value for t in TipoMedida] else TipoMedida.OUTRA

            mid = cadastrar_material(
                numero_processo=proc, tipo_bem=tipo_bem, descricao=desc,
                tipo_medida=tipo_medida, localizacao=loc, custodiante=cust,
                valor_estimado=parse_valor(val), observacoes=obs,
            )
            print(f"\n  ✅ Material cadastrado com ID = {mid}")

        elif op == "2":
            print("\n  ── BUSCA ──")
            proc = input("  Processo (Enter p/ pular): ").strip() or None
            st = input("  Status (Enter p/ pular): ").strip() or None
            status = None
            if st:
                for s in StatusMaterial:
                    if s.value.lower() == st.lower():
                        status = s
                        break
            mats = buscar_materiais(numero_processo=proc, status=status)
            _print_materiais(mats)

        elif op == "3":
            mid = int(input("\n  ID do material: "))
            print("  Status disponíveis:")
            for i, s in enumerate(StatusMaterial, 1):
                print(f"    {i}. {s.value}")
            idx = int(input("  Novo status (número): ")) - 1
            resp = input("  Responsável: ").strip()
            fund = input("  Fundamento legal: ").strip()
            atualizar_status(mid, StatusMaterial[idx], resp, fund)
            print("  ✅ Status atualizado.")

        elif op == "4":
            mid = int(input("\n  ID do material: "))
            tipo = input("  Tipo de movimentação: ").strip()
            de = input("  De (local/pessoa): ").strip()
            para = input("  Para (local/pessoa): ").strip()
            resp = input("  Responsável: ").strip()
            fund = input("  Fundamento: ").strip()
            registrar_movimentacao(mid, tipo, de, para, resp, fund)
            print("  ✅ Movimentação registrada.")

        elif op == "5":
            mid = int(input("\n  ID do material: "))
            hist = obter_historico(mid)
            if not hist:
                print("  (sem movimentações)")
            for h in hist:
                print(f"  [{h['data']}] {h['tipo_mov']} | {h['responsavel']} | {h.get('fundamento_legal','')}")

        elif op == "6":
            r = relatorio_resumo()
            print(f"\n  Total de materiais: {r['total_materiais']}")
            print(f"  Valor total estimado: R$ {r['valor_total_estimado']:,.2f}")
            print("\n  Por status:")
            for k, v in r["por_status"].items():
                print(f"    {k}: {v}")
            print("\n  Por tipo de medida:")
            for k, v in r["por_tipo_medida"].items():
                print(f"    {k}: {v}")

        elif op == "0":
            print("\n  Até logo.")
            break
        else:
            print("  Opção inválida.")


if __name__ == "__main__":
    menu()   