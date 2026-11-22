import asyncio
import csv
import json
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

from capacity_monitor import (
    snmp_get_batch,
    load_devices,
)

load_dotenv()


# ============================================================
# CONFIGURAÇÃO
# ============================================================

INVENTORY_FILE = "inventory/uplinks.json"
OUTPUT_DIR = "output"
SAMPLES_FILE = os.path.join(OUTPUT_DIR, "samples.csv")

MAX_CONCURRENT_DEVICES = int(
    os.getenv("MAX_CONCURRENT_DEVICES", "3")
)


# ============================================================
# OIDs
# ============================================================

OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"


# ============================================================
# INVENTÁRIO
# ============================================================

def load_inventory():

    if not os.path.exists(INVENTORY_FILE):
        raise FileNotFoundError(
            f"Inventário não encontrado: {INVENTORY_FILE}"
        )

    with open(
        INVENTORY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# COLETA DE UM EQUIPAMENTO
# ============================================================

async def collect_device(
    engine,
    hostname,
    device,
    semaphore
):

    async with semaphore:

        start = time.perf_counter()

        ip = device.get("ip")

        # IMPORTANTE:
        # O inventory usa "uplinks", não "interfaces"
        uplinks = device.get(
            "uplinks",
            []
        )

        if not ip:

            print(
                f"[WARN] {hostname}: "
                f"IP não encontrado"
            )

            return []

        if not uplinks:

            print(
                f"[WARN] {hostname}: "
                f"nenhum uplink no inventário"
            )

            return []

        # ----------------------------------------------------
        # Monta OIDs
        # ----------------------------------------------------

        oids = []

        interface_map = {}

        for uplink in uplinks:

            ifindex = uplink.get("ifIndex")

            if ifindex is None:
                continue

            try:
                ifindex = int(ifindex)

            except (
                TypeError,
                ValueError
            ):
                continue

            interface_map[ifindex] = uplink

            oids.append(
                f"{OID_IF_OPER_STATUS}.{ifindex}"
            )

            oids.append(
                f"{OID_IF_HC_IN_OCTETS}.{ifindex}"
            )

            oids.append(
                f"{OID_IF_HC_OUT_OCTETS}.{ifindex}"
            )

        if not oids:

            print(
                f"[WARN] {hostname}: "
                f"nenhum ifIndex válido"
            )

            return []

        # ----------------------------------------------------
        # SNMP GET
        #
        # Assinatura correta:
        #
        # snmp_get_batch(engine, ip, oids)
        # ----------------------------------------------------

        try:

            values = await snmp_get_batch(
                engine,
                ip,
                oids
            )

        except Exception as e:

            print(
                f"[WARN] {hostname}: "
                f"SNMP GET falhou: {e}"
            )

            return []

        # ----------------------------------------------------
        # Processa resultado
        # ----------------------------------------------------

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        samples = []

        for ifindex, uplink in interface_map.items():

            oid_status = (
                f"{OID_IF_OPER_STATUS}.{ifindex}"
            )

            oid_in = (
                f"{OID_IF_HC_IN_OCTETS}.{ifindex}"
            )

            oid_out = (
                f"{OID_IF_HC_OUT_OCTETS}.{ifindex}"
            )

            status = values.get(
                oid_status
            )

            in_octets = values.get(
                oid_in
            )

            out_octets = values.get(
                oid_out
            )

            # ------------------------------------------------
            # Conversão
            # ------------------------------------------------

            try:

                if status is not None:
                    status = int(status)

            except (
                TypeError,
                ValueError
            ):

                status = None

            try:

                if in_octets is not None:
                    in_octets = int(in_octets)

            except (
                TypeError,
                ValueError
            ):

                in_octets = None

            try:

                if out_octets is not None:
                    out_octets = int(out_octets)

            except (
                TypeError,
                ValueError
            ):

                out_octets = None

            # ------------------------------------------------
            # Dados do inventário
            # ------------------------------------------------

            interface_name = (
                uplink.get("interface")
                or uplink.get("ifName")
                or uplink.get("ifDescr")
                or ""
            )

            alias = (
                uplink.get("alias")
                or ""
            )

            capacity_gbps = uplink.get(
                "capacity_gbps"
            )

            failure_domain = (
                uplink.get(
                    "failure_domain"
                )
                or ""
            )

            oper_state = (
                uplink.get(
                    "oper_state"
                )
                or ""
            )

            # ------------------------------------------------
            # Amostra
            # ------------------------------------------------

            samples.append(
                {
                    "timestamp": timestamp,
                    "hostname": hostname,
                    "ip": ip,
                    "ifIndex": ifindex,
                    "interface": interface_name,
                    "alias": alias,
                    "capacity_gbps": capacity_gbps,
                    "oper_status": status,
                    "oper_state": oper_state,
                    "in_octets": in_octets,
                    "out_octets": out_octets,
                    "failure_domain": failure_domain,
                }
            )

        elapsed = (
            time.perf_counter()
            - start
        )

        print(
            f"[OK] {hostname}: "
            f"{len(samples)} interfaces "
            f"em {elapsed:.2f}s"
        )

        return samples


# ============================================================
# CSV
# ============================================================

CSV_FIELDS = [
    "timestamp",
    "hostname",
    "ip",
    "ifIndex",
    "interface",
    "alias",
    "capacity_gbps",
    "oper_status",
    "oper_state",
    "in_octets",
    "out_octets",
    "failure_domain",
]


def append_samples(samples):

    if not samples:
        return

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    file_exists = (
        os.path.exists(SAMPLES_FILE)
        and os.path.getsize(
            SAMPLES_FILE
        ) > 0
    )

    with open(
        SAMPLES_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS
        )

        if not file_exists:
            writer.writeheader()

        for sample in samples:

            writer.writerow(
                {
                    field: sample.get(
                        field,
                        ""
                    )
                    for field in CSV_FIELDS
                }
            )


# ============================================================
# MAIN
# ============================================================

async def main():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Inventário
    # --------------------------------------------------------

    inventory = load_inventory()

    print(
        f"[INFO] Dispositivos no inventário: "
        f"{len(inventory)}"
    )

    total_interfaces = sum(
        len(
            device.get(
                "uplinks",
                []
            )
        )
        for device in inventory.values()
    )

    print(
        f"[INFO] Interfaces monitoradas: "
        f"{total_interfaces}"
    )

    print(
        f"[INFO] Concorrência máxima: "
        f"{MAX_CONCURRENT_DEVICES}"
    )

    # --------------------------------------------------------
    # SNMP Engine
    # --------------------------------------------------------

    engine = SnmpEngine()

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENT_DEVICES
    )

    # --------------------------------------------------------
    # Tarefas
    # --------------------------------------------------------

    tasks = []

    for hostname, device in inventory.items():

        tasks.append(
            collect_device(
                engine,
                hostname,
                device,
                semaphore
            )
        )

    # --------------------------------------------------------
    # Execução
    # --------------------------------------------------------

    start = time.perf_counter()

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    # --------------------------------------------------------
    # Consolidação
    # --------------------------------------------------------

    all_samples = []

    for result in results:

        if isinstance(
            result,
            Exception
        ):

            print(
                f"[WARN] Erro na coleta: "
                f"{result}"
            )

            continue

        all_samples.extend(
            result
        )

    # --------------------------------------------------------
    # Salva CSV
    # --------------------------------------------------------

    append_samples(
        all_samples
    )

    print()

    print(
        f"Tempo total: "
        f"{elapsed:.2f}s"
    )

    print(
        f"Amostras processadas: "
        f"{len(all_samples)}"
    )

    print(
        f"Arquivo: "
        f"{SAMPLES_FILE}"
    )


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "[INFO] Coleta interrompida pelo usuário."
        )
        