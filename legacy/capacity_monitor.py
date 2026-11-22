import asyncio
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    walk_cmd,
)


# ============================================================
# DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
INVENTORY_DIR = BASE_DIR / "inventory"

DEVICES_FILE = CONFIG_DIR / "devices.csv"
INTERFACES_FILE = OUTPUT_DIR / "interfaces.csv"
UPLINKS_FILE = INVENTORY_DIR / "uplinks.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
INVENTORY_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv(BASE_DIR / ".env")

SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_PORT = int(os.getenv("SNMP_PORT", "161"))
SNMP_TIMEOUT = int(os.getenv("SNMP_TIMEOUT", "3"))
SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "2"))

MAX_CONCURRENT_DEVICES = int(
    os.getenv("MAX_CONCURRENT_DEVICES", "5")
)

GET_BATCH_SIZE = int(
    os.getenv("GET_BATCH_SIZE", "10")
)

SAMPLE_INTERVAL = int(
    os.getenv("SAMPLE_INTERVAL", "300")
)


# ============================================================
# OIDs
# ============================================================

OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_IF_NUMBER = "1.3.6.1.2.1.2.1.0"

OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_MTU = "1.3.6.1.2.1.2.2.1.4"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"

OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"


# ============================================================
# CORES
# ============================================================

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"


def enable_windows_ansi():
    """
    Habilita ANSI no Windows moderno.
    """

    if os.name == "nt":

        os.system("")


# ============================================================
# UTILITÁRIOS
# ============================================================

def safe_str(value):
    if value is None:
        return ""

    try:
        return str(value)
    except Exception:
        return ""


def clean_alias(value):
    value = safe_str(value)

    value = value.replace("\n", " ")
    value = value.replace("\r", " ")

    return value.strip()


def oid_index(oid):
    """
    Extrai o último componente do OID.
    """

    oid = safe_str(oid)

    try:
        return int(oid.split(".")[-1])
    except Exception:
        return None


def normalize_name(value):
    """
    Normaliza nome de interface para comparação.
    """

    value = safe_str(value).strip().lower()

    value = value.replace(" ", "")

    return value


# ============================================================
# SNMP
# ============================================================

async def snmp_get(engine, ip, oid):
    """
    Executa SNMP GET de um único OID.
    """

    error_indication, error_status, error_index, var_binds = await get_cmd(
        engine,
        CommunityData(
            SNMP_COMMUNITY,
            mpModel=1
        ),
        await UdpTransportTarget.create(
            (ip, SNMP_PORT),
            timeout=SNMP_TIMEOUT,
            retries=SNMP_RETRIES
        ),
        ContextData(),
        ObjectType(
            ObjectIdentity(oid)
        )
    )

    if error_indication:
        raise RuntimeError(
            f"SNMP error: {error_indication}"
        )

    if error_status:
        raise RuntimeError(
            f"SNMP error: {error_status.prettyPrint()}"
        )

    result = {}

    for var_bind in var_binds:

        oid_obj, value = var_bind

        result[str(oid_obj)] = value

    return result


async def snmp_get_batch(engine, ip, oids):
    """
    Executa SNMP GET em lote.
    """

    if not oids:
        return {}

    error_indication, error_status, error_index, var_binds = await get_cmd(
        engine,
        CommunityData(
            SNMP_COMMUNITY,
            mpModel=1
        ),
        await UdpTransportTarget.create(
            (ip, SNMP_PORT),
            timeout=SNMP_TIMEOUT,
            retries=SNMP_RETRIES
        ),
        ContextData(),
        *[
            ObjectType(
                ObjectIdentity(oid)
            )
            for oid in oids
        ]
    )

    if error_indication:
        raise RuntimeError(
            f"SNMP error: {error_indication}"
        )

    if error_status:
        raise RuntimeError(
            f"SNMP error: {error_status.prettyPrint()}"
        )

    result = {}

    for var_bind in var_binds:

        oid_obj, value = var_bind

        result[str(oid_obj)] = value

    return result


async def snmp_walk(engine, ip, oid):
    """
    Executa SNMP WALK.
    """

    result = []

    transport = await UdpTransportTarget.create(
        (ip, SNMP_PORT),
        timeout=SNMP_TIMEOUT,
        retries=SNMP_RETRIES
    )

    async for (
        error_indication,
        error_status,
        error_index,
        var_binds
    ) in walk_cmd(
        engine,
        CommunityData(
            SNMP_COMMUNITY,
            mpModel=1
        ),
        transport,
        ContextData(),
        ObjectType(
            ObjectIdentity(oid)
        ),
        lexicographicMode=False
    ):

        if error_indication:
            raise RuntimeError(
                f"SNMP error: {error_indication}"
            )

        if error_status:
            raise RuntimeError(
                f"SNMP error: {error_status.prettyPrint()}"
            )

        for var_bind in var_binds:

            oid_obj, value = var_bind

            result.append(
                (
                    str(oid_obj),
                    value
                )
            )

    return result


# ============================================================
# INFORMAÇÕES BÁSICAS
# ============================================================

async def get_basic_info(engine, device):

    ip = device["ip"]

    oids = [
        OID_SYS_DESCR,
        OID_SYS_NAME,
        OID_IF_NUMBER
    ]

    values = await snmp_get_batch(
        engine,
        ip,
        oids
    )

    return {
        "sysDescr": safe_str(
            values.get(OID_SYS_DESCR)
        ),
        "sysName": safe_str(
            values.get(OID_SYS_NAME)
        ),
        "ifNumber": safe_str(
            values.get(OID_IF_NUMBER)
        )
    }


# ============================================================
# FILTROS DE INTERFACE
# ============================================================

def is_logical_interface(name):

    n = normalize_name(name)

    patterns = [
        r"^vlanif",
        r"^vlan\d+",
        r"^loopback",
        r"^lo\d*",
        r"^null",
        r"^virtual",
        r"^nve",
        r"^tunnel",
        r"^cpu",
        r"^system",
        r"^mgmt",
        r"^management",
        r"^meth",
        r"^inband",
        r"^bridge",
        r"^bdi",
        r"^irb",
        r"^ve\d+",
    ]

    for pattern in patterns:

        if re.match(pattern, n):
            return True

    # Subinterface
    if "." in n:
        return True

    return False


def is_aggregate_interface(name):

    n = normalize_name(name)

    patterns = [
        r"^port-channel",
        r"^portchannel",
        r"^po\d+",
        r"^bundle",
        r"^eth-trunk",
        r"^ethtrunk",
        r"^ae\d+",
        r"^lag\d+",
        r"^link-aggregation",
    ]

    for pattern in patterns:

        if re.match(pattern, n):
            return True

    return False


# ============================================================
# NORMALIZAÇÃO DE INTERFACES FÍSICAS
# ============================================================

def normalize_physical_interface(
    name,
    device_type
):

    n = normalize_name(name)

    # --------------------------------------------------------
    # HUAWEI
    # --------------------------------------------------------

    if device_type in [
        "OLT_HUAWEI_MA5800",
        "ROUTER_HUAWEI_CX600"
    ]:

        patterns = [
            r"^ethernet\d+/\d+/\d+$",
            r"^10ge\d+/\d+/\d+$",
            r"^25ge\d+/\d+/\d+$",
            r"^40ge\d+/\d+/\d+$",
            r"^100ge\d+/\d+/\d+$",
            r"^gigabitethernet\d+/\d+/\d+$",
            r"^xgigabitethernet\d+/\d+/\d+$",
        ]

        for pattern in patterns:

            if re.match(pattern, n):
                return n

        return None

    # --------------------------------------------------------
    # ZTE
    # --------------------------------------------------------

    if device_type == "OLT_ZTE_C600":

        patterns = [
            r"^xgei-\d+/\d+/\d+$",
            r"^xge-\d+/\d+/\d+$",
            r"^25gei-\d+/\d+/\d+$",
            r"^25ge-\d+/\d+/\d+$",
            r"^40gei-\d+/\d+/\d+$",
            r"^40ge-\d+/\d+/\d+$",
            r"^100gei-\d+/\d+/\d+$",
            r"^100ge-\d+/\d+/\d+$",
            r"^gei-\d+/\d+/\d+$",
        ]

        for pattern in patterns:

            if re.match(pattern, n):
                return n

        return None

    # --------------------------------------------------------
    # CISCO CBR8
    # --------------------------------------------------------

    if device_type == "CMTS_CISCO_CBR8":

        # Somente portas TeX/1/2, TeX/1/3 e TeX/1/4
        #
        # Exemplos válidos:
        #
        # Te4/1/2
        # Te4/1/3
        # Te4/1/4
        # Te5/1/2
        # Te5/1/3
        # Te5/1/4
        #
        # Não entram:
        #
        # Te4/1/5
        # Te4/1/6
        # Hu4/1/0
        # Hu4/1/1

        pattern = r"^te\d+/1/[2-4]$"

        if re.match(pattern, n):
            return n

        return None

    return None


# ============================================================
# DOMÍNIO DE FALHA
# ============================================================

def get_failure_domain(
    interface_name,
    device_type
):

    n = normalize_name(interface_name)

    # --------------------------------------------------------
    # HUAWEI
    # --------------------------------------------------------

    if device_type in [
        "OLT_HUAWEI_MA5800",
        "ROUTER_HUAWEI_CX600"
    ]:

        match = re.search(
            r"(?:ethernet|10ge|25ge|40ge|100ge|gigabitethernet|xgigabitethernet)(\d+)/(\d+)/(\d+)",
            n
        )

        if match:

            chassis = match.group(1)
            slot = match.group(2)

            return f"SLOT_{chassis}_{slot}"

    # --------------------------------------------------------
    # ZTE
    # --------------------------------------------------------

    if device_type == "OLT_ZTE_C600":

        match = re.search(
            r"(?:xgei|xge|25gei|25ge|40gei|40ge|100gei|100ge|gei)-(\d+)/(\d+)/(\d+)",
            n
        )

        if match:

            chassis = match.group(1)
            slot = match.group(2)

            return f"SLOT_{chassis}_{slot}"

    # --------------------------------------------------------
    # CISCO
    # --------------------------------------------------------

    if device_type == "CMTS_CISCO_CBR8":

        match = re.search(
            r"^(?:te|ten|hu|hundred|fo|forty|gi|gigabitethernet)(\d+)/",
            n
        )

        if match:

            slot = match.group(1)

            return f"SLOT_{slot}"

    return None


# ============================================================
# CAPACIDADE
# ============================================================

def parse_capacity_gbps(
    if_high_speed,
    if_speed
):

    try:

        value = int(
            safe_str(if_high_speed)
        )

        if value > 0:

            return value / 1000.0

    except Exception:
        pass

    try:

        value = int(
            safe_str(if_speed)
        )

        if value > 0:

            return value / 1_000_000_000.0

    except Exception:
        pass

    return 0.0


# ============================================================
# STATUS
# ============================================================

def parse_oper_status(value):

    value = safe_str(value).strip()

    mapping = {
        "1": "UP",
        "2": "DOWN",
        "3": "TESTING",
        "4": "UNKNOWN",
        "5": "DORMANT",
        "6": "NOT_PRESENT",
        "7": "LOWER_LAYER_DOWN",
    }

    return mapping.get(
        value,
        value
    )


# ============================================================
# DISCOVERY
# ============================================================

async def discover_interfaces(device):

    engine = SnmpEngine()

    hostname = device["hostname"]
    ip = device["ip"]
    vendor = device["vendor"]
    device_type = device["device_type"]

    # --------------------------------------------------------
    # Informações básicas
    # --------------------------------------------------------

    basic = await get_basic_info(
        engine,
        device
    )

    # --------------------------------------------------------
    # WALK das tabelas
    # --------------------------------------------------------

    if_descr_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_DESCR
    )

    if_name_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_NAME
    )

    if_alias_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_ALIAS
    )

    if_high_speed_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_HIGH_SPEED
    )

    if_speed_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_SPEED
    )

    if_oper_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_OPER_STATUS
    )

    if_admin_walk = await snmp_walk(
        engine,
        ip,
        OID_IF_ADMIN_STATUS
    )

    # --------------------------------------------------------
    # Converte WALK para dicionários
    # --------------------------------------------------------

    if_descr = {}

    for oid, value in if_descr_walk:

        index = oid_index(oid)

        if index is not None:

            if_descr[index] = safe_str(value)

    if_name = {}

    for oid, value in if_name_walk:

        index = oid_index(oid)

        if index is not None:

            if_name[index] = safe_str(value)

    if_alias = {}

    for oid, value in if_alias_walk:

        index = oid_index(oid)

        if index is not None:

            if_alias[index] = clean_alias(value)

    if_high_speed = {}

    for oid, value in if_high_speed_walk:

        index = oid_index(oid)

        if index is not None:

            if_high_speed[index] = safe_str(value)

    if_speed = {}

    for oid, value in if_speed_walk:

        index = oid_index(oid)

        if index is not None:

            if_speed[index] = safe_str(value)

    if_oper = {}

    for oid, value in if_oper_walk:

        index = oid_index(oid)

        if index is not None:

            if_oper[index] = safe_str(value)

    if_admin = {}

    for oid, value in if_admin_walk:

        index = oid_index(oid)

        if index is not None:

            if_admin[index] = safe_str(value)

    # --------------------------------------------------------
    # Descoberta
    # --------------------------------------------------------

    interfaces = []

    all_indexes = set()

    all_indexes.update(if_descr.keys())
    all_indexes.update(if_name.keys())

    for index in sorted(all_indexes):

        descr = if_descr.get(
            index,
            ""
        )

        name = if_name.get(
            index,
            ""
        )

        alias = if_alias.get(
            index,
            ""
        )

        # ----------------------------------------------------
        # Nome primário
        # ----------------------------------------------------

        primary_name = name or descr

        if not primary_name:
            continue

        # ----------------------------------------------------
        # Exclui interfaces lógicas
        # ----------------------------------------------------

        if is_logical_interface(
            primary_name
        ):

            continue

        # ----------------------------------------------------
        # Exclui agregações
        # ----------------------------------------------------

        if is_aggregate_interface(
            primary_name
        ):

            continue

        # ----------------------------------------------------
        # Normaliza interface física
        # ----------------------------------------------------

        normalized = normalize_physical_interface(
            primary_name,
            device_type
        )

        # ----------------------------------------------------
        # Fallback ZTE pelo ifDescr
        # ----------------------------------------------------

        if (
            normalized is None
            and device_type == "OLT_ZTE_C600"
        ):

            normalized = normalize_physical_interface(
                descr,
                device_type
            )

        if normalized is None:
            continue

        # ----------------------------------------------------
        # Capacidade
        # ----------------------------------------------------

        capacity = parse_capacity_gbps(
            if_high_speed.get(index),
            if_speed.get(index)
        )

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        oper_status = if_oper.get(
            index,
            ""
        )

        admin_status = if_admin.get(
            index,
            ""
        )

        oper_state = parse_oper_status(
            oper_status
        )

        # ----------------------------------------------------
        # Domínio
        # ----------------------------------------------------

        failure_domain = get_failure_domain(
            normalized,
            device_type
        )

        # ----------------------------------------------------
        # Papel
        # ----------------------------------------------------

        role = "UPLINK"

        interfaces.append({
            "hostname": hostname,
            "ip": ip,
            "vendor": vendor,
            "device_type": device_type,

            "ifIndex": index,

            "interface": normalized,
            "ifName": name,
            "ifDescr": descr,
            "alias": alias,

            "role": role,
            "failure_domain": failure_domain,

            "capacity_gbps": capacity,

            "admin_status": admin_status,
            "oper_status": oper_status,
            "oper_state": oper_state,

            "sysName": basic["sysName"],
            "sysDescr": basic["sysDescr"],
        })

    return {
        "interfaces": interfaces,
        "interface_count": len(if_descr),
        "basic": basic,
    }


# ============================================================
# DEVICES.CSV
# ============================================================

def load_devices():

    if not DEVICES_FILE.exists():

        print()
        print(
            f"{RED}[ERRO] Arquivo não encontrado:{RESET}"
        )

        print(
            f"       {DEVICES_FILE}"
        )

        sys.exit(1)

    devices = []

    with open(
        DEVICES_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        required = [
            "hostname",
            "ip",
            "vendor",
            "device_type"
        ]

        for column in required:

            if column not in reader.fieldnames:

                print(
                    f"{RED}[ERRO] Coluna obrigatória "
                    f"ausente: {column}{RESET}"
                )

                sys.exit(1)

        for row in reader:

            hostname = safe_str(
                row.get("hostname")
            ).strip()

            ip = safe_str(
                row.get("ip")
            ).strip()

            vendor = safe_str(
                row.get("vendor")
            ).strip()

            device_type = safe_str(
                row.get("device_type")
            ).strip()

            if not hostname or not ip:
                continue

            devices.append({
                "hostname": hostname,
                "ip": ip,
                "vendor": vendor,
                "device_type": device_type,
            })

    return devices


# ============================================================
# RESUMO
# ============================================================

def calculate_summary(interfaces):

    installed = sum(
        item["capacity_gbps"]
        for item in interfaces
    )

    active_interfaces = [
        item
        for item in interfaces
        if item["oper_state"] == "UP"
    ]

    active = sum(
        item["capacity_gbps"]
        for item in active_interfaces
    )

    domains = defaultdict(float)

    # Mantém a lógica atual:
    # domínio considera somente interfaces UP.

    for item in active_interfaces:

        domain = item.get(
            "failure_domain"
        )

        if domain:

            domains[domain] += (
                item["capacity_gbps"]
            )

    largest_domain = max(
        domains.values(),
        default=0.0
    )

    resilient = active - largest_domain

    return {
        "physical": len(interfaces),
        "up": len(active_interfaces),
        "down": (
            len(interfaces)
            - len(active_interfaces)
        ),
        "installed": installed,
        "active": active,
        "largest_domain": largest_domain,
        "resilient": resilient,
        "domains": dict(domains),
    }


# ============================================================
# SALVA INTERFACES
# ============================================================

def save_interfaces(interfaces):

    if not interfaces:
        return

    fields = [
        "hostname",
        "ip",
        "vendor",
        "device_type",
        "ifIndex",
        "interface",
        "ifName",
        "ifDescr",
        "alias",
        "role",
        "failure_domain",
        "capacity_gbps",
        "admin_status",
        "oper_status",
        "oper_state",
        "sysName",
        "sysDescr",
    ]

    with open(
        INTERFACES_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()

        for item in interfaces:

            writer.writerow({
                field: item.get(field, "")
                for field in fields
            })


# ============================================================
# SALVA INVENTÁRIO
# ============================================================

def save_uplinks_inventory(interfaces):

    inventory = {}

    for item in interfaces:

        hostname = item["hostname"]

        if hostname not in inventory:

            inventory[hostname] = {
                "ip": item["ip"],
                "vendor": item["vendor"],
                "device_type": item["device_type"],
                "sysName": item.get(
                    "sysName",
                    ""
                ),
                "sysDescr": item.get(
                    "sysDescr",
                    ""
                ),
                "discovered_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "uplinks": []
            }

        inventory[hostname]["uplinks"].append({
            "ifIndex": item["ifIndex"],
            "interface": item["interface"],
            "ifName": item.get(
                "ifName",
                ""
            ),
            "ifDescr": item.get(
                "ifDescr",
                ""
            ),
            "alias": item.get(
                "alias",
                ""
            ),
            "capacity_gbps": item[
                "capacity_gbps"
            ],
            "failure_domain": item.get(
                "failure_domain"
            ),
            "admin_status": item.get(
                "admin_status"
            ),
            "oper_status": item.get(
                "oper_status"
            ),
            "oper_state": item.get(
                "oper_state"
            ),
            "role": item.get(
                "role"
            ),
        })

    with open(
        UPLINKS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            inventory,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print(
        f"{GREEN}[OK] Inventário de uplinks salvo em:{RESET}"
    )

    print(
        f"     {UPLINKS_FILE}"
    )


# ============================================================
# CARREGA INVENTÁRIO
# ============================================================

def load_uplinks_inventory():

    if not UPLINKS_FILE.exists():

        print()
        print(
            f"{RED}[ERRO] Inventário não encontrado:{RESET}"
        )

        print(
            f"       {UPLINKS_FILE}"
        )

        print()
        print(
            "Execute primeiro:"
        )

        print(
            "       python capacity_monitor.py --discover"
        )

        sys.exit(1)

    with open(
        UPLINKS_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# PRINT RESUMO
# ============================================================

def print_summary(all_interfaces):

    grouped = defaultdict(list)

    for item in all_interfaces:

        grouped[
            item["hostname"]
        ].append(item)

    print()
    print("=" * 60)
    print("RESUMO DE CAPACIDADE")
    print("=" * 60)

    for hostname, interfaces in grouped.items():

        device_type = interfaces[0][
            "device_type"
        ]

        summary = calculate_summary(
            interfaces
        )

        print()
        print(
            f"{hostname} {device_type}"
        )

        print(
            f"  Interfaces físicas: "
            f"{summary['physical']}"
        )

        print(
            f"  Interfaces UP: "
            f"{summary['up']}"
        )

        print(
            f"  Interfaces DOWN: "
            f"{summary['down']}"
        )

        print(
            f"  Capacidade instalada: "
            f"{summary['installed']:.2f} Gbps"
        )

        print(
            f"  Capacidade ativa: "
            f"{summary['active']:.2f} Gbps"
        )

        print(
            f"  Maior domínio de falha: "
            f"{summary['largest_domain']:.2f} Gbps"
        )

        print(
            f"  Capacidade resiliente: "
            f"{summary['resilient']:.2f} Gbps"
        )

        print("  Domínios:")

        for domain, capacity in sorted(
            summary["domains"].items()
        ):

            print(
                f"    {domain}: "
                f"{capacity:.2f} Gbps"
            )


# ============================================================
# DISCOVERY DE UM DEVICE
# ============================================================

async def discover_one(
    device,
    semaphore
):

    async with semaphore:

        hostname = device["hostname"]

        start = time.time()

        try:

            result = await discover_interfaces(
                device
            )

            interfaces = result["interfaces"]

            elapsed = time.time() - start

            print(
                f"{GREEN}[OK]{RESET} "
                f"{hostname}: "
                f"{result['interface_count']} "
                f"interfaces descobertas"
            )

            print(
                f"      {len(interfaces)} "
                f"interfaces físicas "
                f"em {elapsed:.1f}s"
            )

            summary = calculate_summary(
                interfaces
            )

            print(
                f"      UP: {summary['up']} | "
                f"DOWN: {summary['down']}"
            )

            return interfaces

        except Exception as e:

            elapsed = time.time() - start

            print(
                f"{RED}[ERRO]{RESET} "
                f"{hostname}: "
                f"{e} "
                f"({elapsed:.1f}s)"
            )

            return []


# ============================================================
# DISCOVERY COMPLETO
# ============================================================

async def run_discovery():

    print()
    print(
        "╔══════════════════════════════════════════════════════════╗"
    )
    print(
        "║              CAPACITY MONITOR - DISCOVERY                ║"
    )
    print(
        "╚══════════════════════════════════════════════════════════╝"
    )
    print()

    devices = load_devices()

    print(
        f"[INFO] Dispositivos carregados: "
        f"{len(devices)}"
    )

    print(
        f"[INFO] Concorrência máxima: "
        f"{MAX_CONCURRENT_DEVICES}"
    )

    print()

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENT_DEVICES
    )

    tasks = [
        discover_one(
            device,
            semaphore
        )
        for device in devices
    ]

    results = await asyncio.gather(
        *tasks
    )

    all_interfaces = []

    for result in results:

        all_interfaces.extend(
            result
        )

    # --------------------------------------------------------
    # Salva CSV existente
    # --------------------------------------------------------

    save_interfaces(
        all_interfaces
    )

    print()
    print(
        f"{GREEN}[OK] Inventário salvo em:{RESET}"
    )

    print(
        f"     {INTERFACES_FILE}"
    )

    # --------------------------------------------------------
    # Salva inventário rápido
    # --------------------------------------------------------

    save_uplinks_inventory(
        all_interfaces
    )

    # --------------------------------------------------------
    # Resumo
    # --------------------------------------------------------

    print_summary(
        all_interfaces
    )

    print()
    print(
        "=" * 60
    )

    print(
        "[OK] Discovery concluído."
    )

    print(
        "=" * 60
    )


# ============================================================
# COLETA RÁPIDA
# ============================================================

async def collect_known_uplinks(
    device_data
):

    engine = SnmpEngine()

    hostname = device_data["hostname"]
    ip = device_data["ip"]

    uplinks = device_data.get(
        "uplinks",
        []
    )

    if not uplinks:
        return []

    # --------------------------------------------------------
    # Monta OIDs
    # --------------------------------------------------------

    oid_requests = []

    for uplink in uplinks:

        if_index = uplink["ifIndex"]

        oid_requests.extend([
            f"{OID_IF_HC_IN_OCTETS}.{if_index}",
            f"{OID_IF_HC_OUT_OCTETS}.{if_index}",
            f"{OID_IF_OPER_STATUS}.{if_index}",
        ])

    # --------------------------------------------------------
    # GET em lotes
    # --------------------------------------------------------

    values = {}

    for position in range(
        0,
        len(oid_requests),
        GET_BATCH_SIZE
    ):

        batch = oid_requests[
            position:
            position + GET_BATCH_SIZE
        ]

        result = await snmp_get_batch(
            engine,
            ip,
            batch
        )

        values.update(
            result
        )

    # --------------------------------------------------------
    # Monta resultado
    # --------------------------------------------------------

    results = []

    for uplink in uplinks:

        if_index = uplink["ifIndex"]

        in_oid = (
            f"{OID_IF_HC_IN_OCTETS}."
            f"{if_index}"
        )

        out_oid = (
            f"{OID_IF_HC_OUT_OCTETS}."
            f"{if_index}"
        )

        oper_oid = (
            f"{OID_IF_OPER_STATUS}."
            f"{if_index}"
        )

        in_value = values.get(
            in_oid
        )

        out_value = values.get(
            out_oid
        )

        oper_value = values.get(
            oper_oid
        )

        results.append({
            "hostname": hostname,
            "ip": ip,
            "device_type": device_data[
                "device_type"
            ],

            "ifIndex": if_index,
            "interface": uplink[
                "interface"
            ],

            "alias": uplink.get(
                "alias",
                ""
            ),

            "capacity_gbps": uplink[
                "capacity_gbps"
            ],

            "failure_domain": uplink.get(
                "failure_domain"
            ),

            "oper_status": safe_str(
                oper_value
            ),

            "oper_state": parse_oper_status(
                oper_value
            ),

            "in_octets": safe_str(
                in_value
            ),

            "out_octets": safe_str(
                out_value
            ),
        })

    return results


# ============================================================
# FAST POLL DE UM DEVICE
# ============================================================

async def fast_poll_one(
    hostname,
    device_data,
    semaphore
):

    async with semaphore:

        device_data = dict(
            device_data
        )

        device_data["hostname"] = hostname

        start = time.time()

        try:

            results = await collect_known_uplinks(
                device_data
            )

            elapsed = time.time() - start

            print(
                f"{GREEN}[OK]{RESET} "
                f"{hostname}: "
                f"{len(results)} interfaces "
                f"em {elapsed:.2f}s"
            )

            return results

        except Exception as e:

            elapsed = time.time() - start

            print(
                f"{RED}[ERRO]{RESET} "
                f"{hostname}: "
                f"{e} "
                f"({elapsed:.2f}s)"
            )

            return []


# ============================================================
# FAST POLL
# ============================================================

async def run_fast_poll():

    print()
    print(
        "╔══════════════════════════════════════════════════════════╗"
    )
    print(
        "║             CAPACITY MONITOR - FAST POLL               ║"
    )
    print(
        "╚══════════════════════════════════════════════════════════╝"
    )
    print()

    inventory = load_uplinks_inventory()

    total_interfaces = sum(
        len(
            device_data.get(
                "uplinks",
                []
            )
        )
        for device_data in inventory.values()
    )

    print(
        f"[INFO] Dispositivos no inventário: "
        f"{len(inventory)}"
    )

    print(
        f"[INFO] Interfaces monitoradas: "
        f"{total_interfaces}"
    )

    print(
        f"[INFO] Concorrência máxima: "
        f"{MAX_CONCURRENT_DEVICES}"
    )

    print()

    start = time.time()

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENT_DEVICES
    )

    tasks = [
        fast_poll_one(
            hostname,
            device_data,
            semaphore
        )
        for hostname, device_data
        in inventory.items()
    ]

    results = await asyncio.gather(
        *tasks
    )

    all_results = []

    for result in results:

        all_results.extend(
            result
        )

    elapsed = time.time() - start

    print()
    print(
        "=" * 60
    )

    print(
        "COLETA RÁPIDA CONCLUÍDA"
    )

    print(
        "=" * 60
    )

    print(
        f"Interfaces consultadas: "
        f"{len(all_results)}"
    )

    print(
        f"Tempo total: "
        f"{elapsed:.2f}s"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # Mostra dados coletados
    # --------------------------------------------------------

    print()

    for item in all_results:

        print(
            f"{item['hostname']:20} "
            f"{item['interface']:18} "
            f"{item['oper_state']:5} "
            f"IN={item['in_octets']} "
            f"OUT={item['out_octets']}"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    enable_windows_ansi()

    # --------------------------------------------------------
    # DISCOVERY
    # --------------------------------------------------------

    if "--discover" in sys.argv:

        asyncio.run(
            run_discovery()
        )

    # --------------------------------------------------------
    # FAST POLL
    # --------------------------------------------------------

    else:

        asyncio.run(
            run_fast_poll()
        )