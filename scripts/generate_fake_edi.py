"""
generate_fake_edi.py - Générateur de messages EDI avec pics et variations
----------------------------------------------------------------------
Génère des messages EDI (ANSI X12 et EDIFACT) avec des quantités variables,
incluant des pics, des chutes et des tendances.
"""

import argparse
import os
import random
from datetime import datetime, timedelta

LEAR_ID = "LEARX88"

CLIENTS = [
    {"id": "RENAULTFR", "name": "Renault", "standard": "EDIFACT"},
    {"id": "VOLVOSE01", "name": "Volvo", "standard": "EDIFACT"},
    {"id": "TESLAUS01", "name": "Tesla", "standard": "ANSI_X12"},
    {"id": "BMWDEU01", "name": "BMW", "standard": "ANSI_X12"},
    {"id": "MERCEDESDE", "name": "Mercedes", "standard": "EDIFACT"},
]

SUPPLIERS = [
    {"id": "FRANSERV01", "name": "Frankenfeld"},
    {"id": "CABLEX0022", "name": "CableX"},
    {"id": "WIREPRO014", "name": "WirePro"},
    {"id": "TERMILEC09", "name": "Termilec"},
    {"id": "PLASTIK01", "name": "PlastikTech"},
]

ITEM_REFS = [
    "127010676", "1933893-01-D", "1489061-00-E-00", "2599960-00-C-01",
    "127020022", "123091126", "1933912-00-C-01", "1489062-00-F-00",
]

X12_MESSAGES = [
    ("830", "Inbound"), ("862", "Inbound"), ("850", "Inbound"),
    ("856", "Outbound"), ("810", "Outbound"), ("855", "Outbound"), ("997", "Outbound"),
]

EDIFACT_EQUIV = {
    "830": "DELFOR", "862": "DELJIT", "850": "ORDERS", "856": "DESADV",
    "810": "INVOIC", "855": "ORDRSP", "997": "CONTRL",
}

def rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

def generate_forecast_qty(base_qty, week_index, horizon_weeks, spike_week=None, spike_factor=3.0, trend=0.02):
    """
    Génère une quantité pour une semaine donnée, avec possibilité de pic.
    - base_qty : quantité de base
    - week_index : numéro de la semaine (0 = première)
    - horizon_weeks : nombre total de semaines
    - spike_week : semaine où placer un pic (None = aléatoire)
    - spike_factor : multiplicateur pour le pic (ex: 3.0 = triple)
    - trend : tendance par semaine (ex: 0.02 = +2% par semaine)
    """
    # Tendance progressive
    trend_val = base_qty * (1 + trend * week_index)
    
    # Bruit aléatoire (±5%)
    noise = random.uniform(-0.05, 0.05) * base_qty
    
    qty = trend_val + noise
    
    # Si on est sur la semaine du pic, on multiplie par le facteur
    if spike_week is not None and week_index == spike_week:
        qty *= spike_factor
    
    # Si pas de pic spécifié, on peut en déclencher un aléatoirement (probabilité 5%)
    elif spike_week is None and random.random() < 0.05:
        qty *= random.uniform(2.0, 4.0)
    
    return max(1, int(round(qty)))

def x12_message(msg_type, sender, receiver, doc_number, doc_dt, item_ref, base_qty, uom="EA",
                horizon_weeks=10, spike_week=None, spike_factor=3.0, trend=0.02):
    date_str = doc_dt.strftime("%y%m%d")
    time_str = doc_dt.strftime("%H%M")
    full_date = doc_dt.strftime("%Y%m%d")
    segs = []
    segs.append(f"ISA*00*          *00*          *ZZ*{sender:<15}*ZZ*{receiver:<15}*{date_str}*{time_str}*U*00401*{doc_number:0>9}*0*P*>")
    segs.append(f"GS*SH*{sender}*{receiver}*{full_date}*{time_str}*1*X*004010")
    segs.append(f"ST*{msg_type}*0001")

    if msg_type in ("830", "862"):
        segs.append(f"BFR*04*{doc_number}**{full_date}*{full_date}")
        segs.append(f"N1*ST*{receiver}")
        segs.append(f"LIN*1*BP*{item_ref}")

        for i in range(horizon_weeks):
            qty = generate_forecast_qty(base_qty, i, horizon_weeks, spike_week, spike_factor, trend)
            d = (doc_dt + timedelta(days=7 * i)).strftime("%Y%m%d")
            segs.append(f"FST*{qty}*C*{uom}*{d}")
    else:
        # Pour les autres messages, une quantité unique
        qty = generate_forecast_qty(base_qty, 0, 1, spike_week=None, spike_factor=1, trend=0)
        segs.append(f"SN1*1*{qty}*{uom}")

    segs.append(f"SE*{len(segs) - 2}*0001")
    segs.append(f"GE*1*1")
    segs.append(f"IEA*1*{doc_number:0>9}")
    return "~\n".join(segs) + "~\n"

def edifact_message(msg_type, sender, receiver, doc_number, doc_dt, item_ref, base_qty, uom="C62",
                    horizon_weeks=10, spike_week=None, spike_factor=3.0, trend=0.02):
    date_str = doc_dt.strftime("%y%m%d")
    time_str = doc_dt.strftime("%H%M")
    full_date = doc_dt.strftime("%Y%m%d")
    segs = []
    segs.append(f"UNB+UNOA:1+{sender}+{receiver}+{date_str}:{time_str}+{doc_number}++{msg_type}")
    segs.append(f"UNH+{doc_number}+{msg_type}:D:97A:UN")
    segs.append(f"BGM+351+{doc_number}+9")
    segs.append(f"DTM+137:{full_date}{time_str}:203")
    segs.append(f"NAD+SU+{sender}::16")
    segs.append(f"NAD+ST+{receiver}::92")
    segs.append(f"LIN+++{item_ref}:IN")

    if msg_type in ("DELFOR", "DELJIT"):
        for i in range(horizon_weeks):
            qty = generate_forecast_qty(base_qty, i, horizon_weeks, spike_week, spike_factor, trend)
            d = (doc_dt + timedelta(days=7 * i)).strftime("%Y%m%d")
            segs.append(f"QTY+1:{qty}:{uom}")
            segs.append(f"DTM+2:{d}:102")
    else:
        qty = generate_forecast_qty(base_qty, 0, 1, spike_week=None, spike_factor=1, trend=0)
        segs.append(f"QTY+12:{qty}:{uom}")

    segs.append(f"UNT+{len(segs) - 1}+{doc_number}")
    segs.append(f"UNZ+1+{doc_number}")
    return "'\n".join(segs) + "'\n"

def build_message(msg_type_x12, sense, client, supplier, doc_seq, base_date, spike_info=None):
    item_ref = random.choice(ITEM_REFS)
    base_qty = random.choice([10, 12, 15, 20, 25, 30, 50, 60, 80])

    # spike_info = {"week": int, "factor": float, "trend": float} ou None
    if spike_info:
        spike_week = spike_info.get("week")
        spike_factor = spike_info.get("factor", 3.0)
        trend = spike_info.get("trend", 0.02)
    else:
        # Aléatoire : une chance sur 3 d'avoir un pic dans le message
        if random.random() < 0.33:
            spike_week = random.randint(0, 9)
            spike_factor = random.uniform(2.0, 5.0)
            trend = random.uniform(0.01, 0.03)
        else:
            spike_week = None
            spike_factor = 1.0
            trend = random.uniform(-0.01, 0.03)

    doc_number = f"{doc_seq:07d}"
    is_client_flow = random.random() < 0.7

    if is_client_flow:
        partner = client
        standard = client["standard"]
        if sense == "Inbound":
            sender, receiver = partner["id"], LEAR_ID
        else:
            sender, receiver = LEAR_ID, partner["id"]
        partner_role = "client"
    else:
        partner = random.choice(SUPPLIERS)
        standard = "ANSI_X12"
        if msg_type_x12 in ("830", "862", "850"):
            sense = "Outbound"
            sender, receiver = LEAR_ID, partner["id"]
        else:
            sense = "Inbound"
            sender, receiver = partner["id"], LEAR_ID
        partner_role = "fournisseur"

    horizon_weeks = 10 if msg_type_x12 in ("830", "862") else 1

    if standard == "ANSI_X12":
        content = x12_message(
            msg_type_x12, sender, receiver, doc_seq, base_date, item_ref, base_qty,
            horizon_weeks=horizon_weeks, spike_week=spike_week, spike_factor=spike_factor, trend=trend
        )
        ext = "x12"
    else:
        edifact_type = EDIFACT_EQUIV[msg_type_x12]
        content = edifact_message(
            edifact_type, sender, receiver, doc_number, base_date, item_ref, base_qty,
            horizon_weeks=horizon_weeks, spike_week=spike_week, spike_factor=spike_factor, trend=trend
        )
        ext = "edifact"

    meta = {
        "sense": sense, "standard": standard, "partner_id": partner["id"],
        "partner_name": partner["name"], "partner_role": partner_role,
        "message_type": msg_type_x12, "item_ref": item_ref, "qty": base_qty,
        "date": base_date, "spike": spike_week is not None,
        "spike_week": spike_week,
        "spike_factor": spike_factor if spike_week is not None else None,
    }
    return content, ext, meta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../data/edi_messages")
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--spike-prob", type=float, default=0.33, help="Probabilité d'un pic par message (0-1)")
    args = parser.parse_args()

    random.seed(args.seed)

    out_dir = os.path.abspath(args.out)
    os.makedirs(os.path.join(out_dir, "inbound"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "outbound"), exist_ok=True)

    start_date = datetime(2026, 1, 5)
    end_date = datetime(2026, 7, 20)

    doc_seq = 1000

    for i in range(args.n):
        msg_type, default_sense = random.choice(X12_MESSAGES)
        client = random.choice(CLIENTS)
        base_date = rand_date(start_date, end_date)

        # Décider si ce message aura un pic
        spike_info = None
        if random.random() < args.spike_prob:
            spike_week = random.randint(0, 9)
            spike_factor = random.uniform(2.0, 5.0)
            trend = random.uniform(0.01, 0.04)
            spike_info = {"week": spike_week, "factor": spike_factor, "trend": trend}

        doc_seq += 1
        content, ext, meta = build_message(msg_type, default_sense, client, None, doc_seq, base_date, spike_info)

        folder = "inbound" if meta["sense"] == "Inbound" else "outbound"
        filename = f"{meta['standard']}_{meta['message_type']}_{meta['partner_id']}_{doc_seq}.{ext}"
        filepath = os.path.join(out_dir, folder, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"{args.n} messages EDI fictifs generes dans : {out_dir}")
    print(f"  - inbound  : {len(os.listdir(os.path.join(out_dir, 'inbound')))} fichiers")
    print(f"  - outbound : {len(os.listdir(os.path.join(out_dir, 'outbound')))} fichiers")
    print(f"  - Probabilité de pic : {args.spike_prob*100}%")

if __name__ == "__main__":
    main()