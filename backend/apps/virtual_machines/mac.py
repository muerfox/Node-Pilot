import random


def generate_mac_address() -> str:
    """Generates a locally-administered, unicast MAC in the QEMU/KVM
    vendor-neutral private range (52:54:00 is the traditional QEMU OUI)."""
    octets = [0x52, 0x54, 0x00, random.randint(0, 0x7F), random.randint(0, 0xFF), random.randint(0, 0xFF)]
    return ":".join(f"{octet:02x}" for octet in octets)
