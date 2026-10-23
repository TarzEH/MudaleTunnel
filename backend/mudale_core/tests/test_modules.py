"""Tests for the module registry (use/set/run system)."""

from __future__ import annotations

import pytest

from mudale_core.modules import (
    MODULE_REGISTRY,
    Module,
    ModuleOption,
    build_tunnel_spec,
    get_module,
    list_modules,
)
from mudale_engine.enums import TunnelKind

# ── Registry completeness ─────────────────────────────────────────────

EXPECTED_MODULES = [
    "tunnel/ssh_local",
    "tunnel/ssh_dynamic",
    "tunnel/ssh_remote",
    "tunnel/ssh_remote_dynamic",
    "tunnel/ligolo",
    "scan/nmap",
    "pivot/auto",
]


class TestRegistryCompleteness:
    def test_all_expected_modules_registered(self):
        for name in EXPECTED_MODULES:
            assert name in MODULE_REGISTRY, f"{name} missing from MODULE_REGISTRY"

    def test_registry_has_exactly_seven_entries(self):
        assert len(MODULE_REGISTRY) == 7

    def test_get_module_returns_module_for_each(self):
        for name in EXPECTED_MODULES:
            mod = get_module(name)
            assert mod is not None
            assert mod.full_name == name

    def test_get_module_returns_none_for_unknown(self):
        assert get_module("tunnel/nonexistent") is None
        assert get_module("") is None

    def test_get_module_returns_fresh_instances(self):
        a = get_module("tunnel/ssh_local")
        b = get_module("tunnel/ssh_local")
        assert a is not b, "get_module should return a new instance each call"


class TestListModules:
    def test_returns_list_of_dicts(self):
        result = list_modules()
        assert isinstance(result, list)
        assert len(result) == 7
        for entry in result:
            assert "name" in entry
            assert "type" in entry
            assert "description" in entry

    def test_types_are_correct(self):
        result = {m["name"]: m["type"] for m in list_modules()}
        assert result["tunnel/ssh_local"] == "tunnel"
        assert result["scan/nmap"] == "scan"
        assert result["pivot/auto"] == "pivot"


# ── Module metadata ───────────────────────────────────────────────────

class TestModuleMetadata:
    @pytest.mark.parametrize("name,expected_type", [
        ("tunnel/ssh_local", "tunnel"),
        ("tunnel/ssh_dynamic", "tunnel"),
        ("tunnel/ssh_remote", "tunnel"),
        ("tunnel/ssh_remote_dynamic", "tunnel"),
        ("tunnel/ligolo", "tunnel"),
        ("scan/nmap", "scan"),
        ("pivot/auto", "pivot"),
    ])
    def test_module_type(self, name, expected_type):
        mod = get_module(name)
        assert mod.type == expected_type

    def test_each_module_has_description(self):
        for name in EXPECTED_MODULES:
            mod = get_module(name)
            assert mod.description, f"{name} has empty description"


# ── Option set / get / unset ──────────────────────────────────────────

class TestSetGetUnset:
    def test_set_and_get_string_option(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.set_option("RHOST", "10.0.0.1")
        assert err is None
        assert mod.get_option("RHOST") == "10.0.0.1"

    def test_get_returns_default_when_unset(self):
        mod = get_module("tunnel/ssh_local")
        assert mod.get_option("LHOST") == "127.0.0.1"

    def test_get_returns_none_for_unknown_option(self):
        mod = get_module("tunnel/ssh_local")
        assert mod.get_option("DOES_NOT_EXIST") is None

    def test_unset_clears_value(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        assert mod.get_option("RHOST") == "10.0.0.1"
        err = mod.unset_option("RHOST")
        assert err is None
        # After unset, falls back to default (None for RHOST)
        assert mod.get_option("RHOST") is None

    def test_unset_unknown_option_returns_error(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.unset_option("BOGUS")
        assert err is not None
        assert "Unknown option" in err

    def test_set_unknown_option_returns_error(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.set_option("BOGUS", "whatever")
        assert err is not None
        assert "Unknown option" in err


# ── Case-insensitive option lookup ────────────────────────────────────

class TestCaseInsensitiveLookup:
    """_find_option is case-insensitive for locating the option definition,
    so set/get/unset accept lowercase names without error.  However, _values
    stores using the caller's raw casing, so cross-case set-then-get does
    NOT round-trip (e.g. set("rhost") then get("RHOST") misses).  The tests
    below document that actual behaviour."""

    def test_set_accepts_lowercase_name(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.set_option("rhost", "10.0.0.1")
        assert err is None  # no "Unknown option" error
        # Retrieval with the *same* casing works:
        assert mod.get_option("rhost") == "10.0.0.1"

    def test_get_accepts_lowercase_name(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        # get_option("rhost") finds the option definition, but _values key
        # is "RHOST" so it falls back to default (None).
        assert mod.get_option("rhost") is None

    def test_unset_accepts_lowercase_name(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("rhost", "10.0.0.1")
        err = mod.unset_option("rhost")
        assert err is None
        # After unset with matching casing, value is cleared:
        assert mod.get_option("rhost") is None


# ── Type coercion ─────────────────────────────────────────────────────

class TestTypeCoercion:
    def test_int_coercion(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.set_option("LPORT", "8080")
        assert err is None
        assert mod.get_option("LPORT") == 8080
        assert isinstance(mod.get_option("LPORT"), int)

    def test_int_coercion_rejects_non_numeric(self):
        mod = get_module("tunnel/ssh_local")
        err = mod.set_option("LPORT", "abc")
        assert err is not None
        assert "integer" in err

    def test_bool_coercion_true_variants(self):
        mod = get_module("tunnel/ssh_local")
        for truthy in ("true", "True", "TRUE", "yes", "Yes", "1"):
            mod.set_option("STRICT_HOST_KEY", truthy)
            assert mod.get_option("STRICT_HOST_KEY") is True, f"Failed for {truthy!r}"

    def test_bool_coercion_false_variants(self):
        mod = get_module("tunnel/ssh_local")
        for falsy in ("false", "False", "no", "0", "anything_else"):
            mod.set_option("STRICT_HOST_KEY", falsy)
            assert mod.get_option("STRICT_HOST_KEY") is False, f"Failed for {falsy!r}"


# ── Choice validation ─────────────────────────────────────────────────

class TestChoiceValidation:
    def test_valid_choice_accepted(self):
        mod = get_module("scan/nmap")
        err = mod.set_option("PROFILE", "quick")
        assert err is None
        assert mod.get_option("PROFILE") == "quick"

    def test_invalid_choice_rejected(self):
        mod = get_module("scan/nmap")
        err = mod.set_option("PROFILE", "ultra_deep")
        assert err is not None
        assert "Invalid value" in err
        assert "Choices:" in err

    def test_all_scan_profiles_valid(self):
        mod = get_module("scan/nmap")
        for profile in ("discovery", "quick", "standard", "full", "udp_top"):
            err = mod.set_option("PROFILE", profile)
            assert err is None, f"Profile {profile!r} should be valid"


# ── Validate (required options) ───────────────────────────────────────

class TestValidate:
    def test_all_required_set_returns_empty(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        mod.set_option("LPORT", "8080")
        mod.set_option("TARGET_HOST", "192.168.1.1")
        mod.set_option("TARGET_PORT", "80")
        # USERNAME has a default "root" — satisfies required
        errors = mod.validate()
        assert errors == []

    def test_missing_required_returns_errors(self):
        mod = get_module("tunnel/ssh_local")
        # Don't set RHOST (required, no default)
        errors = mod.validate()
        assert any("RHOST" in e for e in errors)

    def test_required_with_default_passes(self):
        """USERNAME is required but has default 'root' — should pass."""
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        mod.set_option("LPORT", "8080")
        mod.set_option("TARGET_HOST", "192.168.1.1")
        mod.set_option("TARGET_PORT", "80")
        errors = mod.validate()
        assert not any("USERNAME" in e for e in errors)

    def test_required_set_to_empty_string_fails(self):
        mod = get_module("scan/nmap")
        mod.set_option("TARGET", "")
        errors = mod.validate()
        assert any("TARGET" in e for e in errors)

    def test_nmap_valid(self):
        mod = get_module("scan/nmap")
        mod.set_option("TARGET", "10.0.0.0/24")
        # PROFILE has default "standard"
        errors = mod.validate()
        assert errors == []


# ── Options table ─────────────────────────────────────────────────────

class TestOptionsTable:
    def test_returns_list_of_dicts_with_expected_keys(self):
        mod = get_module("tunnel/ssh_local")
        table = mod.get_options_table()
        assert isinstance(table, list)
        assert len(table) > 0
        for row in table:
            assert set(row.keys()) == {"name", "current", "required", "description"}

    def test_shows_set_value(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        table = {r["name"]: r for r in mod.get_options_table()}
        assert table["RHOST"]["current"] == "10.0.0.1"

    def test_shows_default_when_unset(self):
        mod = get_module("tunnel/ssh_local")
        table = {r["name"]: r for r in mod.get_options_table()}
        assert table["LHOST"]["current"] == "127.0.0.1"

    def test_shows_empty_when_no_value_or_default(self):
        mod = get_module("tunnel/ssh_local")
        table = {r["name"]: r for r in mod.get_options_table()}
        # RHOST has no default
        assert table["RHOST"]["current"] == ""

    def test_required_flag(self):
        mod = get_module("tunnel/ssh_local")
        table = {r["name"]: r for r in mod.get_options_table()}
        assert table["RHOST"]["required"] == "yes"
        assert table["IDENTITY"]["required"] == "no"


# ── build_tunnel_spec ─────────────────────────────────────────────────

def _populated_ssh_module(name: str, **extra) -> Module:
    """Helper: create an SSH-based tunnel module with standard options set."""
    mod = get_module(name)
    mod.set_option("RHOST", "10.0.0.1")
    mod.set_option("USERNAME", "admin")
    mod.set_option("RPORT", "2222")
    mod.set_option("IDENTITY", "/tmp/id_rsa")
    for k, v in extra.items():
        mod.set_option(k, v)
    return mod


class TestBuildTunnelSpecSshLocal:
    def test_kind_is_ssh_local(self):
        mod = _populated_ssh_module(
            "tunnel/ssh_local",
            LPORT="8080", TARGET_HOST="192.168.1.1", TARGET_PORT="80",
        )
        kind, spec = build_tunnel_spec(mod)
        assert kind == TunnelKind.SSH_LOCAL

    def test_endpoint_fields(self):
        mod = _populated_ssh_module(
            "tunnel/ssh_local",
            LPORT="8080", TARGET_HOST="192.168.1.1", TARGET_PORT="80",
        )
        _, spec = build_tunnel_spec(mod)
        ep = spec["endpoint"]
        assert ep["user"] == "admin"
        assert ep["host"] == "10.0.0.1"
        assert ep["port"] == 2222
        assert ep["identity_file"] == "/tmp/id_rsa"

    def test_spec_fields(self):
        mod = _populated_ssh_module(
            "tunnel/ssh_local",
            LHOST="0.0.0.0", LPORT="8080",
            TARGET_HOST="192.168.1.1", TARGET_PORT="80",
        )
        _, spec = build_tunnel_spec(mod)
        assert spec["local_bind"] == "0.0.0.0"
        assert spec["local_port"] == 8080
        assert spec["target_host"] == "192.168.1.1"
        assert spec["target_port"] == 80


class TestBuildTunnelSpecSshDynamic:
    def test_kind_and_fields(self):
        mod = _populated_ssh_module("tunnel/ssh_dynamic", LPORT="1080")
        kind, spec = build_tunnel_spec(mod)
        assert kind == TunnelKind.SSH_DYNAMIC
        assert spec["local_port"] == 1080
        assert spec["local_bind"] == "127.0.0.1"
        assert "endpoint" in spec


class TestBuildTunnelSpecSshRemote:
    def test_kind_and_fields(self):
        mod = _populated_ssh_module(
            "tunnel/ssh_remote",
            REMOTE_PORT="9090", TARGET_HOST="127.0.0.1", TARGET_PORT="3000",
        )
        kind, spec = build_tunnel_spec(mod)
        assert kind == TunnelKind.SSH_REMOTE
        assert spec["remote_port"] == 9090
        assert spec["remote_bind"] == "127.0.0.1"
        assert spec["target_host"] == "127.0.0.1"
        assert spec["target_port"] == 3000


class TestBuildTunnelSpecSshRemoteDynamic:
    def test_kind_and_fields(self):
        mod = _populated_ssh_module("tunnel/ssh_remote_dynamic", REMOTE_PORT="1080")
        kind, spec = build_tunnel_spec(mod)
        assert kind == TunnelKind.SSH_REMOTE_DYNAMIC
        assert spec["remote_port"] == 1080
        assert spec["remote_bind"] == "127.0.0.1"


class TestBuildTunnelSpecLigolo:
    def test_kind_and_fields(self):
        mod = get_module("tunnel/ligolo")
        mod.set_option("AGENT_ADDR", "10.0.0.50")
        mod.set_option("LISTEN_PORT", "11601")
        mod.set_option("TUN_NAME", "pivot0")
        mod.set_option("SELFCERT", "true")
        kind, spec = build_tunnel_spec(mod)
        assert kind == TunnelKind.LIGOLO
        assert spec["agent_addr"] == "10.0.0.50"
        assert spec["listen_port"] == 11601
        assert spec["tun_name"] == "pivot0"
        assert spec["selfcert"] is True

    def test_selfcert_false(self):
        mod = get_module("tunnel/ligolo")
        mod.set_option("AGENT_ADDR", "10.0.0.50")
        mod.set_option("SELFCERT", "false")
        _, spec = build_tunnel_spec(mod)
        assert spec["selfcert"] is False


class TestBuildTunnelSpecEndpointNoIdentity:
    def test_identity_omitted_when_not_set(self):
        mod = get_module("tunnel/ssh_local")
        mod.set_option("RHOST", "10.0.0.1")
        mod.set_option("LPORT", "8080")
        mod.set_option("TARGET_HOST", "192.168.1.1")
        mod.set_option("TARGET_PORT", "80")
        _, spec = build_tunnel_spec(mod)
        assert "identity_file" not in spec["endpoint"]


class TestBuildTunnelSpecErrors:
    def test_raises_for_non_tunnel_module(self):
        """scan/nmap and pivot/auto are not tunnel modules and should raise."""
        mod = get_module("scan/nmap")
        mod.set_option("TARGET", "10.0.0.0/24")
        with pytest.raises(ValueError, match="Unknown tunnel module"):
            build_tunnel_spec(mod)

    def test_raises_for_pivot_auto(self):
        mod = get_module("pivot/auto")
        mod.set_option("TUNNEL_ID", "1")
        mod.set_option("TARGET", "10.0.0.0/24")
        with pytest.raises(ValueError, match="Unknown tunnel module"):
            build_tunnel_spec(mod)


# ── ModuleOption / Module dataclass direct construction ───────────────

class TestModuleOptionDataclass:
    def test_defaults(self):
        opt = ModuleOption(name="FOO", description="A test option")
        assert opt.required is False
        assert opt.default is None
        assert opt.choices is None
        assert opt.value_type == "str"


class TestModuleDataclassDirectConstruction:
    def test_empty_module(self):
        mod = Module(type="test", name="empty", full_name="test/empty",
                     description="An empty module")
        assert mod.validate() == []
        assert mod.get_options_table() == []

    def test_set_overrides_default(self):
        mod = Module(
            type="test", name="t", full_name="test/t", description="",
            options=[ModuleOption("PORT", "port", default="80", value_type="int")],
        )
        assert mod.get_option("PORT") == "80"  # default is str "80"
        mod.set_option("PORT", "9090")
        assert mod.get_option("PORT") == 9090  # coerced to int
