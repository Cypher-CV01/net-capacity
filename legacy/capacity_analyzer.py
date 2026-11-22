
import csv
import json
import math
import os
from collections import defaultdict
from datetime import datetime
from statistics import quantiles
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SAMPLES_FILE = os.path.join(
    BASE_DIR,
    "output",
    "samples.csv"
)

INVENTORY_FILE = os.path.join(
    BASE_DIR,
    "inventory",
    "uplinks.json"
)

REPORT_FILE = os.path.join(
    BASE_DIR,
    "output",
    "capacity_report.xlsx"
)

# Horário oficial para apresentação dos dados
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


# ============================================================
# UTILITÁRIOS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default

        return float(value)

    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default

        return int(value)

    except (ValueError, TypeError):
        return default


def percentile(values, percent):
    """
    Calcula percentil de forma simples por interpolação.
    """

    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * percent

    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return values[lower]

    weight = position - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * weight
    )


# ============================================================
# TIMESTAMP
# ============================================================

def parse_timestamp(value):
    """
    Converte timestamp ISO 8601.

    Exemplos aceitos:

    2026-09-21T18:43:05.152637+00:00
    2026-09-21T18:43:05+00:00
    2026-09-21T18:43:05.152637Z
    """

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

    except (ValueError, TypeError):
        return None

    # Se não houver timezone, consideramos UTC.
    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=ZoneInfo("UTC")
        )

    return dt


def format_local_timestamp(dt):
    """
    Converte UTC para horário de Brasília
    somente para apresentação.
    """

    if not dt:
        return ""

    local_dt = dt.astimezone(LOCAL_TZ)

    return local_dt.strftime(
        "%d/%m/%Y %H:%M:%S"
    )


# ============================================================
# LEITURA DO INVENTÁRIO
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
# LEITURA DAS AMOSTRAS
# ============================================================

def load_samples():
    if not os.path.exists(SAMPLES_FILE):
        raise FileNotFoundError(
            f"Arquivo de amostras não encontrado: {SAMPLES_FILE}"
        )

    samples = []

    with open(
        SAMPLES_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            timestamp = parse_timestamp(
                row.get("timestamp")
            )

            if timestamp is None:
                continue

            row["_timestamp"] = timestamp

            row["ifIndex"] = safe_int(
                row.get("ifIndex")
            )

            row["capacity_gbps"] = safe_float(
                row.get("capacity_gbps")
            )

            row["in_octets"] = safe_int(
                row.get("in_octets")
            )

            row["out_octets"] = safe_int(
                row.get("out_octets")
            )

            row["oper_status"] = safe_int(
                row.get("oper_status")
            )

            samples.append(row)

    return samples


# ============================================================
# CÁLCULO DE TRÁFEGO
# ============================================================

def calculate_traffic(samples):
    """
    Calcula tráfego entre amostras consecutivas.

    IN:
        delta_in_octets * 8 / segundos

    OUT:
        delta_out_octets * 8 / segundos

    O timestamp permanece em UTC durante o cálculo.
    """

    grouped = defaultdict(list)

    for sample in samples:

        key = (
            sample.get("hostname"),
            sample.get("ifIndex")
        )

        grouped[key].append(sample)

    traffic_samples = []

    for key, rows in grouped.items():

        rows.sort(
            key=lambda x: x["_timestamp"]
        )

        previous = None

        for current in rows:

            if previous is None:
                previous = current
                continue

            current_timestamp = current["_timestamp"]
            previous_timestamp = previous["_timestamp"]

            elapsed = (
                current_timestamp
                - previous_timestamp
            ).total_seconds()

            if elapsed <= 0:
                previous = current
                continue

            current_in = current["in_octets"]
            previous_in = previous["in_octets"]

            current_out = current["out_octets"]
            previous_out = previous["out_octets"]

            delta_in = current_in - previous_in
            delta_out = current_out - previous_out

            # Contador SNMP pode reiniciar.
            if delta_in < 0:
                delta_in = 0

            if delta_out < 0:
                delta_out = 0

            in_bps = (
                delta_in
                * 8
                / elapsed
            )

            out_bps = (
                delta_out
                * 8
                / elapsed
            )

            in_gbps = in_bps / 1_000_000_000
            out_gbps = out_bps / 1_000_000_000

            capacity = current["capacity_gbps"]

            if capacity > 0:

                in_utilization = (
                    in_gbps
                    / capacity
                    * 100
                )

                out_utilization = (
                    out_gbps
                    / capacity
                    * 100
                )

            else:

                in_utilization = 0
                out_utilization = 0

            # Em um link full-duplex, não somamos IN + OUT
            # para comparar com a capacidade.
            #
            # A utilização do link é a maior das duas direções.

            utilization = max(
                in_utilization,
                out_utilization
            )

            traffic_samples.append(
                {
                    "timestamp": current_timestamp,
                    "hostname": current["hostname"],
                    "ip": current.get("ip", ""),
                    "ifIndex": current["ifIndex"],
                    "interface": current.get(
                        "interface",
                        ""
                    ),
                    "alias": current.get(
                        "alias",
                        ""
                    ),
                    "capacity_gbps": capacity,
                    "failure_domain": current.get(
                        "failure_domain",
                        ""
                    ),
                    "oper_status": current[
                        "oper_status"
                    ],
                    "oper_state": current.get(
                        "oper_state",
                        ""
                    ),
                    "in_gbps": in_gbps,
                    "out_gbps": out_gbps,
                    "in_utilization": in_utilization,
                    "out_utilization": out_utilization,
                    "utilization": utilization,
                    "elapsed_seconds": elapsed,
                }
            )

            previous = current

    return traffic_samples


# ============================================================
# RESUMO POR INTERFACE
# ============================================================

def calculate_interface_summary(traffic_samples):
    grouped = defaultdict(list)

    for sample in traffic_samples:

        key = (
            sample["hostname"],
            sample["ifIndex"]
        )

        grouped[key].append(sample)

    summaries = []

    for key, rows in grouped.items():

        rows.sort(
            key=lambda x: x["timestamp"]
        )

        last = rows[-1]

        capacity = last["capacity_gbps"]

        in_values = [
            x["in_gbps"]
            for x in rows
        ]

        out_values = [
            x["out_gbps"]
            for x in rows
        ]

        utilization_values = [
            x["utilization"]
            for x in rows
        ]

        in_util_values = [
            x["in_utilization"]
            for x in rows
        ]

        out_util_values = [
            x["out_utilization"]
            for x in rows
        ]

        p95_in = percentile(
            in_values,
            0.95
        )

        p95_out = percentile(
            out_values,
            0.95
        )

        p95_in_util = percentile(
            in_util_values,
            0.95
        )

        p95_out_util = percentile(
            out_util_values,
            0.95
        )

        p95_utilization = percentile(
            utilization_values,
            0.95
        )

        p99_utilization = percentile(
            utilization_values,
            0.99
        )

        max_utilization = max(
            utilization_values
        )

        # Headroom baseado no pior sentido
        peak_gbps = max(
            p95_in,
            p95_out
        )

        headroom = max(
            capacity - peak_gbps,
            0
        )

        summaries.append(
            {
                "hostname": last["hostname"],
                "ip": last["ip"],
                "ifIndex": last["ifIndex"],
                "interface": last["interface"],
                "alias": last["alias"],
                "capacity_gbps": capacity,
                "failure_domain": last[
                    "failure_domain"
                ],
                "sample_count": len(rows),
                "last_timestamp": last[
                    "timestamp"
                ],
                "last_in_gbps": last[
                    "in_gbps"
                ],
                "last_out_gbps": last[
                    "out_gbps"
                ],
                "last_in_utilization": last[
                    "in_utilization"
                ],
                "last_out_utilization": last[
                    "out_utilization"
                ],
                "last_utilization": last[
                    "utilization"
                ],
                "p95_in_gbps": p95_in,
                "p95_out_gbps": p95_out,
                "p95_in_utilization": p95_in_util,
                "p95_out_utilization": p95_out_util,
                "p95_utilization": p95_utilization,
                "p99_utilization": p99_utilization,
                "max_utilization": max_utilization,
                "headroom_gbps": headroom,
            }
        )

    summaries.sort(
        key=lambda x: (
            x["hostname"],
            x["interface"]
        )
    )

    return summaries


# ============================================================
# STATUS
# ============================================================

def utilization_status(utilization):
    if utilization >= 95:
        return "EMERGÊNCIA"

    if utilization >= 90:
        return "CRÍTICO"

    if utilization >= 80:
        return "PLANEJAMENTO"

    if utilization >= 70:
        return "ATENÇÃO"

    return "NORMAL"


# ============================================================
# RESUMO POR DISPOSITIVO
# ============================================================

def calculate_device_summary(
    inventory,
    interface_summaries
):

    summaries = []

    interfaces_by_device = defaultdict(list)

    for interface in interface_summaries:

        interfaces_by_device[
            interface["hostname"]
        ].append(interface)

    for hostname, device in inventory.items():

        uplinks = device.get(
            "uplinks",
            []
        )

        installed_capacity = sum(
            safe_float(
                uplink.get(
                    "capacity_gbps"
                )
            )
            for uplink in uplinks
        )

        active_capacity = sum(
            safe_float(
                uplink.get(
                    "capacity_gbps"
                )
            )
            for uplink in uplinks
            if str(
                uplink.get(
                    "oper_state",
                    ""
                )
            ).upper() == "UP"
        )

        domains = defaultdict(float)

        for uplink in uplinks:

            if str(
                uplink.get(
                    "oper_state",
                    ""
                )
            ).upper() != "UP":
                continue

            domain = uplink.get(
                "failure_domain",
                "UNKNOWN"
            )

            domains[domain] += safe_float(
                uplink.get(
                    "capacity_gbps"
                )
            )

        largest_failure_domain = (
            max(domains.values())
            if domains
            else 0
        )

        resilient_capacity = max(
            active_capacity
            - largest_failure_domain,
            0
        )

        # Tráfego P95 agregado do dispositivo
        device_interfaces = (
            interfaces_by_device.get(
                hostname,
                []
            )
        )

        p95_total_in = sum(
            x["p95_in_gbps"]
            for x in device_interfaces
        )

        p95_total_out = sum(
            x["p95_out_gbps"]
            for x in device_interfaces
        )

        p95_total_active = max(
            p95_total_in,
            p95_total_out
        )

        if active_capacity > 0:

            active_utilization = (
                p95_total_active
                / active_capacity
                * 100
            )

        else:

            active_utilization = 0

        if resilient_capacity > 0:

            resilient_utilization = (
                p95_total_active
                / resilient_capacity
                * 100
            )

        else:

            resilient_utilization = 0

        summaries.append(
            {
                "hostname": hostname,
                "ip": device.get(
                    "ip",
                    ""
                ),
                "vendor": device.get(
                    "vendor",
                    ""
                ),
                "device_type": device.get(
                    "device_type",
                    ""
                ),
                "installed_capacity": installed_capacity,
                "active_capacity": active_capacity,
                "largest_failure_domain": largest_failure_domain,
                "resilient_capacity": resilient_capacity,
                "p95_in_gbps": p95_total_in,
                "p95_out_gbps": p95_total_out,
                "p95_active_gbps": p95_total_active,
                "active_utilization": active_utilization,
                "resilient_utilization": resilient_utilization,
                "status": utilization_status(
                    active_utilization
                ),
            }
        )

    summaries.sort(
        key=lambda x: x["hostname"]
    )

    return summaries


# ============================================================
# ALERTAS
# ============================================================

def generate_alerts(interface_summaries):

    alerts = []

    for interface in interface_summaries:

        utilization = interface[
            "p95_utilization"
        ]

        if utilization >= 80:

            alerts.append(
                {
                    "hostname": interface[
                        "hostname"
                    ],
                    "interface": interface[
                        "interface"
                    ],
                    "alias": interface[
                        "alias"
                    ],
                    "capacity_gbps": interface[
                        "capacity_gbps"
                    ],
                    "p95_utilization": utilization,
                    "status": utilization_status(
                        utilization
                    ),
                }
            )

    alerts.sort(
        key=lambda x: x[
            "p95_utilization"
        ],
        reverse=True
    )

    return alerts


# ============================================================
# EXCEL
# ============================================================

def style_header(ws, row=1):

    for cell in ws[row]:

        cell.font = Font(
            bold=True,
            color="FFFFFF"
        )

        cell.fill = PatternFill(
            "solid",
            fgColor="404040"
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )


def auto_width(ws):

    for column in ws.columns:

        max_length = 0

        column_letter = get_column_letter(
            column[0].column
        )

        for cell in column:

            value = cell.value

            if value is None:
                continue

            max_length = max(
                max_length,
                len(str(value))
            )

        ws.column_dimensions[
            column_letter
        ].width = min(
            max_length + 2,
            45
        )


def add_utilization_formatting(
    ws,
    column_letter,
    start_row,
    end_row
):

    if end_row < start_row:
        return

    cell_range = (
        f"{column_letter}{start_row}:"
        f"{column_letter}{end_row}"
    )

    # >= 95
    ws.conditional_formatting.add(
        cell_range,
        CellIsRule(
            operator="greaterThanOrEqual",
            formula=["95"],
            fill=PatternFill(
                "solid",
                fgColor="F4CCCC"
            )
        )
    )

    # >= 90
    ws.conditional_formatting.add(
        cell_range,
        CellIsRule(
            operator="between",
            formula=["90", "94.999"],
            fill=PatternFill(
                "solid",
                fgColor="FCE5CD"
            )
        )
    )

    # >= 80
    ws.conditional_formatting.add(
        cell_range,
        CellIsRule(
            operator="between",
            formula=["80", "89.999"],
            fill=PatternFill(
                "solid",
                fgColor="FFF2CC"
            )
        )
    )

    # >= 70
    ws.conditional_formatting.add(
        cell_range,
        CellIsRule(
            operator="between",
            formula=["70", "79.999"],
            fill=PatternFill(
                "solid",
                fgColor="D9EAD3"
            )
        )
    )


# ============================================================
# ABA RESUMO
# ============================================================

def create_summary_sheet(
    wb,
    device_summaries
):

    ws = wb.active
    ws.title = "Resumo"

    headers = [
        "Hostname",
        "IP",
        "Vendor",
        "Device Type",
        "Capacidade Instalada (Gbps)",
        "Capacidade Ativa (Gbps)",
        "Maior Domínio de Falha (Gbps)",
        "Capacidade Resiliente (Gbps)",
        "P95 IN (Gbps)",
        "P95 OUT (Gbps)",
        "P95 Tráfego Ativo (Gbps)",
        "Utilização Ativa P95 (%)",
        "Utilização Resiliente P95 (%)",
        "Status",
    ]

    ws.append(headers)
    style_header(ws)

    for device in device_summaries:

        ws.append(
            [
                device["hostname"],
                device["ip"],
                device["vendor"],
                device["device_type"],
                device["installed_capacity"],
                device["active_capacity"],
                device["largest_failure_domain"],
                device["resilient_capacity"],
                device["p95_in_gbps"],
                device["p95_out_gbps"],
                device["p95_active_gbps"],
                device["active_utilization"],
                device["resilient_utilization"],
                device["status"],
            ]
        )

    for row in ws.iter_rows(
        min_row=2
    ):

        for cell in row:
            cell.alignment = Alignment(
                vertical="center"
            )

    add_utilization_formatting(
        ws,
        "L",
        2,
        ws.max_row
    )

    add_utilization_formatting(
        ws,
        "M",
        2,
        ws.max_row
    )

    ws.freeze_panes = "A2"

    auto_width(ws)


# ============================================================
# ABA INTERFACES
# ============================================================

def create_interfaces_sheet(
    wb,
    interface_summaries
):

    ws = wb.create_sheet(
        "Interfaces"
    )

    headers = [
        "Hostname",
        "IP",
        "ifIndex",
        "Interface",
        "Alias",
        "Failure Domain",
        "Capacidade (Gbps)",
        "Amostras",
        "Última Coleta",
        "IN Atual (Gbps)",
        "OUT Atual (Gbps)",
        "IN Atual (%)",
        "OUT Atual (%)",
        "Utilização Atual (%)",
        "P95 IN (Gbps)",
        "P95 OUT (Gbps)",
        "P95 IN (%)",
        "P95 OUT (%)",
        "P95 Utilização (%)",
        "P99 Utilização (%)",
        "Máxima Utilização (%)",
        "Headroom (Gbps)",
        "Status",
    ]

    ws.append(headers)
    style_header(ws)

    for item in interface_summaries:

        ws.append(
            [
                item["hostname"],
                item["ip"],
                item["ifIndex"],
                item["interface"],
                item["alias"],
                item["failure_domain"],
                item["capacity_gbps"],
                item["sample_count"],
                format_local_timestamp(
                    item["last_timestamp"]
                ),
                item["last_in_gbps"],
                item["last_out_gbps"],
                item["last_in_utilization"],
                item["last_out_utilization"],
                item["last_utilization"],
                item["p95_in_gbps"],
                item["p95_out_gbps"],
                item["p95_in_utilization"],
                item["p95_out_utilization"],
                item["p95_utilization"],
                item["p99_utilization"],
                item["max_utilization"],
                item["headroom_gbps"],
                utilization_status(
                    item["p95_utilization"]
                ),
            ]
        )

    # Formatação numérica
    for row in ws.iter_rows(
        min_row=2,
        min_col=7
    ):

        for cell in row:

            if cell.column in [
                7,
                10,
                11,
                15,
                16,
                22,
            ]:

                cell.number_format = "0.00"

            elif cell.column in [
                12,
                13,
                14,
                17,
                18,
                19,
                20,
                21,
            ]:

                cell.number_format = "0.00"

    # Utilização atual
    add_utilization_formatting(
        ws,
        "N",
        2,
        ws.max_row
    )

    # P95
    add_utilization_formatting(
        ws,
        "S",
        2,
        ws.max_row
    )

    # P99
    add_utilization_formatting(
        ws,
        "T",
        2,
        ws.max_row
    )

    # Máxima
    add_utilization_formatting(
        ws,
        "U",
        2,
        ws.max_row
    )

    ws.freeze_panes = "A2"

    auto_width(ws)


# ============================================================
# ABA TRÁFEGO
# ============================================================

def create_traffic_sheet(
    wb,
    traffic_samples
):

    ws = wb.create_sheet(
        "Trafego"
    )

    headers = [
        "Data/Hora",
        "Hostname",
        "IP",
        "ifIndex",
        "Interface",
        "Alias",
        "Failure Domain",
        "Capacidade (Gbps)",
        "IN (Gbps)",
        "OUT (Gbps)",
        "IN (%)",
        "OUT (%)",
        "Utilização (%)",
        "Intervalo (s)",
    ]

    ws.append(headers)
    style_header(ws)

    traffic_samples.sort(
        key=lambda x: x["timestamp"]
    )

    for sample in traffic_samples:

        ws.append(
            [
                format_local_timestamp(
                    sample["timestamp"]
                ),
                sample["hostname"],
                sample["ip"],
                sample["ifIndex"],
                sample["interface"],
                sample["alias"],
                sample["failure_domain"],
                sample["capacity_gbps"],
                sample["in_gbps"],
                sample["out_gbps"],
                sample["in_utilization"],
                sample["out_utilization"],
                sample["utilization"],
                sample["elapsed_seconds"],
            ]
        )

    for row in ws.iter_rows(
        min_row=2
    ):

        for cell in row:

            if cell.column in [
                8,
                9,
                10,
            ]:

                cell.number_format = "0.00"

            elif cell.column in [
                11,
                12,
                13,
            ]:

                cell.number_format = "0.00"

    add_utilization_formatting(
        ws,
        "M",
        2,
        ws.max_row
    )

    ws.freeze_panes = "A2"

    auto_width(ws)


# ============================================================
# ABA AMOSTRAS
# ============================================================

def create_samples_sheet(
    wb,
    samples
):

    ws = wb.create_sheet(
        "Amostras"
    )

    headers = [
        "Data/Hora Brasília",
        "Hostname",
        "IP",
        "ifIndex",
        "Interface",
        "Alias",
        "Capacidade (Gbps)",
        "Oper Status",
        "Oper State",
        "IN Octets",
        "OUT Octets",
        "Failure Domain",
    ]

    ws.append(headers)
    style_header(ws)

    samples.sort(
        key=lambda x: x["_timestamp"]
    )

    for sample in samples:

        ws.append(
            [
                format_local_timestamp(
                    sample["_timestamp"]
                ),
                sample.get(
                    "hostname",
                    ""
                ),
                sample.get(
                    "ip",
                    ""
                ),
                sample.get(
                    "ifIndex",
                    ""
                ),
                sample.get(
                    "interface",
                    ""
                ),
                sample.get(
                    "alias",
                    ""
                ),
                sample.get(
                    "capacity_gbps",
                    0
                ),
                sample.get(
                    "oper_status",
                    ""
                ),
                sample.get(
                    "oper_state",
                    ""
                ),
                sample.get(
                    "in_octets",
                    0
                ),
                sample.get(
                    "out_octets",
                    0
                ),
                sample.get(
                    "failure_domain",
                    ""
                ),
            ]
        )

    ws.freeze_panes = "A2"

    auto_width(ws)


# ============================================================
# ABA ALERTAS
# ============================================================

def create_alerts_sheet(
    wb,
    alerts
):

    ws = wb.create_sheet(
        "Alertas"
    )

    headers = [
        "Hostname",
        "Interface",
        "Alias",
        "Capacidade (Gbps)",
        "P95 Utilização (%)",
        "Status",
    ]

    ws.append(headers)
    style_header(ws)

    for alert in alerts:

        ws.append(
            [
                alert["hostname"],
                alert["interface"],
                alert["alias"],
                alert["capacity_gbps"],
                alert["p95_utilization"],
                alert["status"],
            ]
        )

    for row in ws.iter_rows(
        min_row=2
    ):

        row[3].number_format = "0.00"
        row[4].number_format = "0.00"

    add_utilization_formatting(
        ws,
        "E",
        2,
        ws.max_row
    )

    ws.freeze_panes = "A2"

    auto_width(ws)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("CAPACITY MONITOR - ANALYZER")
    print("=" * 70)

    print()

    print(
        f"[INFO] Samples: {SAMPLES_FILE}"
    )

    print(
        f"[INFO] Inventory: {INVENTORY_FILE}"
    )

    print(
        f"[INFO] Timezone relatório: "
        f"America/Sao_Paulo"
    )

    print()

    # --------------------------------------------------------
    # INVENTÁRIO
    # --------------------------------------------------------

    inventory = load_inventory()

    print(
        f"[OK] Dispositivos no inventário: "
        f"{len(inventory)}"
    )

    # --------------------------------------------------------
    # AMOSTRAS
    # --------------------------------------------------------

    samples = load_samples()

    print(
        f"[OK] Amostras carregadas: "
        f"{len(samples)}"
    )

    if not samples:

        print(
            "[ERRO] Nenhuma amostra válida encontrada."
        )

        return

    # --------------------------------------------------------
    # TRÁFEGO
    # --------------------------------------------------------

    traffic_samples = calculate_traffic(
        samples
    )

    print(
        f"[OK] Intervalos de tráfego calculados: "
        f"{len(traffic_samples)}"
    )

    # --------------------------------------------------------
    # INTERFACES
    # --------------------------------------------------------

    interface_summaries = (
        calculate_interface_summary(
            traffic_samples
        )
    )

    print(
        f"[OK] Interfaces analisadas: "
        f"{len(interface_summaries)}"
    )

    # --------------------------------------------------------
    # DISPOSITIVOS
    # --------------------------------------------------------

    device_summaries = (
        calculate_device_summary(
            inventory,
            interface_summaries
        )
    )

    # --------------------------------------------------------
    # ALERTAS
    # --------------------------------------------------------

    alerts = generate_alerts(
        interface_summaries
    )

    # --------------------------------------------------------
    # CONSOLE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("UTILIZAÇÃO DOS UPLINKS")
    print("=" * 70)

    for item in interface_summaries:

        print(
            f"{item['hostname']:<18} "
            f"{item['interface']:<20} "
            f"{item['capacity_gbps']:>6.2f}G | "
            f"IN {item['last_in_gbps']:>6.2f}G "
            f"({item['last_in_utilization']:>6.2f}%) | "
            f"OUT {item['last_out_gbps']:>6.2f}G "
            f"({item['last_out_utilization']:>6.2f}%) | "
            f"P95 {item['p95_utilization']:>6.2f}% | "
            f"{utilization_status(item['p95_utilization'])}"
        )

    # --------------------------------------------------------
    # EXCEL
    # --------------------------------------------------------

    wb = Workbook()

    create_summary_sheet(
        wb,
        device_summaries
    )

    create_interfaces_sheet(
        wb,
        interface_summaries
    )

    create_traffic_sheet(
        wb,
        traffic_samples
    )

    create_samples_sheet(
        wb,
        samples
    )

    create_alerts_sheet(
        wb,
        alerts
    )

    # --------------------------------------------------------
    # SALVAR
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(REPORT_FILE),
        exist_ok=True
    )

    wb.save(
        REPORT_FILE
    )

    print()
    print("=" * 70)

    print(
        f"[OK] Relatório gerado:"
    )

    print(
        REPORT_FILE
    )

    print("=" * 70)

    print()
    print(
        f"[INFO] Alertas encontrados: "
        f"{len(alerts)}"
    )

    print()
    print(
        "Horário apresentado no relatório: "
        "America/Sao_Paulo"
    )


if __name__ == "__main__":
    main()

