"""
Clean Python API for m1n1 hypervisor research sessions.

Wraps m1n1 proxy connection and provides high-level interface
for Stage-2 manipulation, hooking, and exploit primitives.
"""


class HypervisorSession:
    """
    Represents a connection to an m1n1 hypervisor instance
    running on a target Apple Silicon device.
    """

    def __init__(self, serial="/dev/cu.usbmodem*"):
        self.serial = serial
        self.__connect()

    def __connect(self):
        """Establish proxy connection to m1n1 over USB-C serial."""
        raise NotImplementedError

    def readmem(self, gpa, size):
        """Read guest physical memory."""
        raise NotImplementedError

    def writemem(self, gpa, data):
        """Write guest physical memory."""
        raise NotImplementedError

    def vatop(self, guest_va, cr3):
        """Walk guest page tables to translate VA -> PA."""
        raise NotImplementedError

    def get_log(self):
        """Read m1n1 trace log buffer."""
        raise NotImplementedError

    def alloc_page(self):
        """Allocate a 4KB page from m1n1's heap."""
        raise NotImplementedError

    def stage2_swap(self, gpa, new_hpa):
        """Swap Stage-2 mapping. Returns old HP address."""
        from m1n1.stage2 import stage2_page_swap
        return stage2_page_swap(self, gpa, new_hpa)
