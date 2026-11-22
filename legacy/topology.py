import re


def detect_failure_domain(
    vendor: str,
    interface: str,
) -> str:

    vendor = vendor.lower()
    interface = interface.strip()

    # =========================================================
    # HUAWEI
    #
    # ethernet0/8/0
    # ethernet0/8/1
    #
    # ethernet0/9/0
    # ethernet0/9/1
    #
    # O segundo campo representa o slot/placa.
    # =========================================================

    if vendor == "huawei":

        match = re.match(
            r"^[a-z]+(\d+)/(\d+)/(\d+)$",
            interface.lower()
        )

        if match:

            frame = match.group(1)
            slot = match.group(2)

            return f"SLOT_{frame}_{slot}"

    # =========================================================
    # ZTE
    #
    # xgei-1/10/1
    # xgei-1/11/1
    #
    # O segundo campo representa a placa/slot.
    # =========================================================

    if vendor == "zte":

        match = re.match(
            r"^[a-z]+-(\d+)/(\d+)/(\d+)$",
            interface.lower()
        )

        if match:

            rack = match.group(1)
            slot = match.group(2)

            return f"SLOT_{rack}_{slot}"

    # =========================================================
    # CISCO
    #
    # Te4/1/2
    # Te5/1/2
    #
    # Primeiro número pode representar o módulo/slot.
    # =========================================================

    if vendor == "cisco":

        match = re.match(
            r"^(?:Te|Hu|Fo)(\d+)/",
            interface,
            re.IGNORECASE
        )

        if match:

            slot = match.group(1)

            return f"SLOT_{slot}"

        # Port-channel não deve ser tratado como
        # domínio físico de falha aqui.
        if interface.lower().startswith(
            ("po", "port-channel")
        ):
            return "LOGICAL_AGGREGATE"

    return "UNKNOWN"