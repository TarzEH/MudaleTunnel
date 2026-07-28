"""nmap XML parser tests, including hostile-input handling."""

from __future__ import annotations

import pytest

from apps.scans.parsers import NmapParseError, parse_nmap_xml

SAMPLE = """<?xml version="1.0"?>
<nmaprun scanner="nmap" version="7.94">
  <host>
    <status state="up"/>
    <address addr="10.4.9.5" addrtype="ipv4"/>
    <address addr="00:0c:29:11:22:33" addrtype="mac"/>
    <hostnames><hostname name="sql01.corp.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="1433">
        <state state="open"/>
        <service name="ms-sql-s" product="Microsoft SQL Server" version="15.00.2000"
                 extrainfo="SP0"/>
      </port>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9p1"/>
      </port>
      <port protocol="tcp" portid="8080">
        <state state="filtered"/>
      </port>
    </ports>
  </host>
  <runstats><hosts up="1" down="253" total="254"/></runstats>
</nmaprun>
"""


def test_services_are_extracted():
    result = parse_nmap_xml(SAMPLE)
    assert result.service_count == 3
    sql = next(s for s in result.services if s.port == 1433)
    assert sql.host == "10.4.9.5"
    assert sql.protocol == "tcp"
    assert sql.state == "open"
    assert sql.service_name == "ms-sql-s"
    assert sql.product == "Microsoft SQL Server"
    assert sql.version == "15.00.2000"
    assert sql.extra_info == "SP0"
    assert sql.hostname == "sql01.corp.local"


def test_run_statistics_are_extracted():
    result = parse_nmap_xml(SAMPLE)
    assert result.hosts_up == 1
    assert result.hosts_total == 254


def test_ports_without_a_service_element_are_kept():
    """A filtered port with no service block is still a finding."""
    result = parse_nmap_xml(SAMPLE)
    filtered = next(s for s in result.services if s.port == 8080)
    assert filtered.state == "filtered"
    assert filtered.service_name == ""


def test_mac_addresses_are_not_used_as_the_host():
    assert all(s.host == "10.4.9.5" for s in parse_nmap_xml(SAMPLE).services)


def test_ipv4_is_preferred_over_ipv6():
    xml = """<nmaprun>
      <host>
        <address addr="2001:db8::1" addrtype="ipv6"/>
        <address addr="10.4.9.5" addrtype="ipv4"/>
        <ports><port protocol="tcp" portid="80"><state state="open"/></port></ports>
      </host>
    </nmaprun>"""
    assert parse_nmap_xml(xml).services[0].host == "10.4.9.5"


def test_ipv6_only_host_is_supported():
    xml = """<nmaprun>
      <host>
        <address addr="2001:db8::1" addrtype="ipv6"/>
        <ports><port protocol="tcp" portid="80"><state state="open"/></port></ports>
      </host>
    </nmaprun>"""
    assert parse_nmap_xml(xml).services[0].host == "2001:db8::1"


def test_empty_scan_is_not_an_error():
    """Nothing found is a valid result, distinct from a failed scan."""
    xml = '<nmaprun><runstats><hosts up="0" down="256" total="256"/></runstats></nmaprun>'
    result = parse_nmap_xml(xml)
    assert result.service_count == 0
    assert result.hosts_up == 0


# ── Failure modes ───────────────────────────────────────────────────────


@pytest.mark.parametrize("payload", ["", "   ", "\n"])
def test_empty_output_raises(payload):
    with pytest.raises(NmapParseError, match="no output"):
        parse_nmap_xml(payload)


def test_malformed_xml_raises_instead_of_returning_nothing():
    """The v2 failure mode: a broken parse must not look like a clean empty scan."""
    with pytest.raises(NmapParseError, match="not valid XML"):
        parse_nmap_xml("<nmaprun><host>truncated...")


def test_wrong_document_type_raises():
    with pytest.raises(NmapParseError, match="Expected an <nmaprun>"):
        parse_nmap_xml("<html><body>not nmap</body></html>")


# ── Hostile input ───────────────────────────────────────────────────────


def test_entity_expansion_is_refused():
    """Banners come from the target, so the document is attacker-influenced.

    A billion-laughs payload must not expand.
    """
    xml = """<?xml version="1.0"?>
    <!DOCTYPE nmaprun [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
      <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
    ]>
    <nmaprun><host><address addr="10.4.9.5" addrtype="ipv4"/>
    <ports><port protocol="tcp" portid="80"><state state="open"/>
    <service name="&lol3;"/></port></ports></host></nmaprun>"""
    with pytest.raises(NmapParseError):
        parse_nmap_xml(xml)


def test_control_characters_in_a_banner_are_stripped():
    """A crafted banner must not inject line breaks into logs or CLI output.

    XML 1.0 already forbids most control characters, so an ESC (``&#27;``)
    cannot even reach us — the document fails to parse. Newline and tab *are*
    legal, which makes them the real injection risk, and they are stripped here.
    """
    xml = (
        '<nmaprun><host><address addr="10.4.9.5" addrtype="ipv4"/><ports>'
        '<port protocol="tcp" portid="80"><state state="open"/>'
        '<service name="http" product="Evil&#10;Server&#9;padded"/>'
        "</port></ports></host></nmaprun>"
    )
    product = parse_nmap_xml(xml).services[0].product
    assert "\n" not in product
    assert "\t" not in product
    assert "Evil" in product


def test_xml_forbidden_control_characters_fail_the_parse():
    """An ESC-injection attempt is rejected as malformed rather than sanitised."""
    xml = (
        '<nmaprun><host><address addr="10.4.9.5" addrtype="ipv4"/><ports>'
        '<port protocol="tcp" portid="80"><state state="open"/>'
        '<service name="http" product="Evil&#27;[2J"/>'
        "</port></ports></host></nmaprun>"
    )
    with pytest.raises(NmapParseError, match="not valid XML"):
        parse_nmap_xml(xml)


def test_oversized_banner_is_truncated():
    xml = (
        '<nmaprun><host><address addr="10.4.9.5" addrtype="ipv4"/><ports>'
        '<port protocol="tcp" portid="80"><state state="open"/>'
        f'<service name="http" product="{"A" * 5000}"/>'
        "</port></ports></host></nmaprun>"
    )
    assert len(parse_nmap_xml(xml).services[0].product) <= 128


@pytest.mark.parametrize("portid", ["0", "70000", "-1", "notanumber", ""])
def test_impossible_port_numbers_are_dropped(portid):
    xml = (
        '<nmaprun><host><address addr="10.4.9.5" addrtype="ipv4"/><ports>'
        f'<port protocol="tcp" portid="{portid}"><state state="open"/></port>'
        "</ports></host></nmaprun>"
    )
    assert parse_nmap_xml(xml).service_count == 0


def test_host_without_a_usable_address_is_skipped():
    xml = """<nmaprun><host>
      <address addr="00:0c:29:11:22:33" addrtype="mac"/>
      <ports><port protocol="tcp" portid="80"><state state="open"/></port></ports>
    </host></nmaprun>"""
    assert parse_nmap_xml(xml).service_count == 0


def test_malformed_address_is_skipped():
    xml = """<nmaprun><host>
      <address addr="999.999.999.999" addrtype="ipv4"/>
      <ports><port protocol="tcp" portid="80"><state state="open"/></port></ports>
    </host></nmaprun>"""
    assert parse_nmap_xml(xml).service_count == 0
