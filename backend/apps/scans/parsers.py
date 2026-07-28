"""nmap XML output parser.

v2 parsed nmap's human-readable text with line patterns, and quietly returned
zero services whenever the output shape differed from what the patterns
expected — the scan looked successful and simply found nothing. Parsing the XML
document removes that whole failure mode: either the document parses and the
results are complete, or it does not and the scan is reported as failed.

Security note: nmap's XML is attacker-influenced — service banners are echoed
back from the target, so a host can choose what ends up in this document. It is
parsed with ``defusedxml``, which refuses entity declarations outright (closing
billion-laughs and external-entity attacks) rather than relying on stdlib parser
defaults. Every extracted string is treated as display data, truncated, stripped
of control characters, and never used to build a command line.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from xml.etree import ElementTree

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as defused_fromstring

logger = logging.getLogger(__name__)

#: Cap on how many services a single scan may contribute, so a hostile or
#: enormous result set cannot exhaust memory or the database.
MAX_SERVICES_PER_SCAN = 50_000

#: Banner fields are echoed from the target; truncate them to the column widths.
MAX_PRODUCT = 128
MAX_VERSION = 128
MAX_EXTRA = 256
MAX_SERVICE_NAME = 64
MAX_HOSTNAME = 253


class NmapParseError(Exception):
    """The output was not a parseable nmap XML document."""


@dataclass
class ParsedService:
    host: str
    port: int
    protocol: str
    state: str
    service_name: str = ""
    product: str = ""
    version: str = ""
    extra_info: str = ""
    hostname: str = ""


@dataclass
class ParsedScan:
    services: list[ParsedService] = field(default_factory=list)
    hosts_up: int = 0
    hosts_total: int = 0
    #: True when nmap reported a run-level error inside an otherwise valid doc.
    had_errors: bool = False

    @property
    def service_count(self) -> int:
        return len(self.services)


def parse_nmap_xml(xml_text: str) -> ParsedScan:
    """Parse nmap ``-oX -`` output into structured results."""
    if not xml_text or not xml_text.strip():
        raise NmapParseError("nmap produced no output")

    try:
        root = defused_fromstring(xml_text)
    except DefusedXmlException as exc:
        raise NmapParseError(f"nmap output contained a forbidden XML construct: {exc}") from exc
    except ElementTree.ParseError as exc:
        raise NmapParseError(f"nmap output was not valid XML: {exc}") from exc

    if root.tag != "nmaprun":
        raise NmapParseError(f"Expected an <nmaprun> document, got <{root.tag}>")

    result = ParsedScan()

    runstats = root.find("runstats/hosts")
    if runstats is not None:
        result.hosts_up = _int_attr(runstats, "up")
        result.hosts_total = _int_attr(runstats, "total")

    for host in root.findall("host"):
        address = _primary_address(host)
        if address is None:
            # A host block with no usable address is not something we can
            # attribute findings to; skip it rather than invent one.
            continue

        hostname = _primary_hostname(host)

        for port in host.findall("ports/port"):
            if len(result.services) >= MAX_SERVICES_PER_SCAN:
                logger.warning(
                    "nmap result truncated at %d services", MAX_SERVICES_PER_SCAN
                )
                result.had_errors = True
                return result

            parsed = _parse_port(port, address, hostname)
            if parsed is not None:
                result.services.append(parsed)

    return result


# ── Internals ───────────────────────────────────────────────────────────


def _parse_port(port_el, address: str, hostname: str) -> ParsedService | None:
    try:
        port_number = int(port_el.get("portid", ""))
    except ValueError:
        return None
    if not 1 <= port_number <= 65535:
        return None

    state_el = port_el.find("state")
    state = (state_el.get("state", "") if state_el is not None else "").strip()
    if not state:
        return None

    service_el = port_el.find("service")
    if service_el is not None:
        service_name = _clean(service_el.get("name"), MAX_SERVICE_NAME)
        product = _clean(service_el.get("product"), MAX_PRODUCT)
        version = _clean(service_el.get("version"), MAX_VERSION)
        extra_info = _clean(service_el.get("extrainfo"), MAX_EXTRA)
    else:
        service_name = product = version = extra_info = ""

    return ParsedService(
        host=address,
        port=port_number,
        protocol=(port_el.get("protocol") or "tcp").lower(),
        state=state,
        service_name=service_name,
        product=product,
        version=version,
        extra_info=extra_info,
        hostname=hostname,
    )


def _primary_address(host_el) -> str | None:
    """The host's IP. Prefers IPv4, falls back to IPv6, ignores MAC entries."""
    fallback: str | None = None
    for address_el in host_el.findall("address"):
        addr_type = address_el.get("addrtype", "")
        value = (address_el.get("addr") or "").strip()
        if not value or addr_type not in {"ipv4", "ipv6"}:
            continue
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            continue
        if parsed.version == 4:
            return str(parsed)
        fallback = fallback or str(parsed)
    return fallback


def _primary_hostname(host_el) -> str:
    for hostname_el in host_el.findall("hostnames/hostname"):
        name = _clean(hostname_el.get("name"), MAX_HOSTNAME)
        if name:
            return name
    return ""


def _clean(value: str | None, max_length: int) -> str:
    """Normalise an attacker-influenced string for safe storage and display.

    Control characters are stripped so a crafted banner cannot inject line
    breaks or terminal escapes into logs and CLI output.
    """
    if not value:
        return ""
    cleaned = "".join(char for char in value if char.isprintable())
    return cleaned.strip()[:max_length]


def _int_attr(element, name: str) -> int:
    try:
        return int(element.get(name, "0"))
    except (TypeError, ValueError):
        return 0
