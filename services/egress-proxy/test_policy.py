"""Unit tests for the egress policy (pure logic, no network)."""

from __future__ import annotations

import unittest

from policy import Allowlist, check, is_public


class TestIsPublic(unittest.TestCase):
    def test_public_ipv4(self):
        self.assertTrue(is_public("8.8.8.8"))
        self.assertTrue(is_public("1.1.1.1"))
        self.assertTrue(is_public("93.184.216.34"))

    def test_documentation_ipv4_denied(self):
        for ip in ("192.0.2.1", "198.51.100.1", "203.0.113.9"):
            self.assertFalse(is_public(ip), ip)

    def test_private_ipv4(self):
        for ip in ("10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
                   "127.0.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1", "224.0.0.1"):
            self.assertFalse(is_public(ip), ip)

    def test_ipv6(self):
        self.assertTrue(is_public("2606:4700:4700::1111"))  # Cloudflare
        self.assertFalse(is_public("::1"))
        self.assertFalse(is_public("fe80::1"))
        self.assertFalse(is_public("fc00::1"))

    def test_ipv4_mapped_ipv6(self):
        # ::ffff:192.168.1.1 must be treated as the private 192.168.1.1
        self.assertFalse(is_public("::ffff:192.168.1.1"))


class TestAllowlist(unittest.TestCase):
    def test_empty_allows_everything(self):
        self.assertTrue(Allowlist().allows("anything.example.com"))

    def test_exact_and_subdomain(self):
        allow = Allowlist(["greenhouse.io", "cdn.example.com"])
        self.assertTrue(allow.allows("greenhouse.io"))
        self.assertTrue(allow.allows("boards.greenhouse.io"))
        self.assertFalse(allow.allows("evil.test"))
        self.assertFalse(allow.allows("notgreenhouse.io"))

    def test_case_and_dot_insensitive(self):
        allow = Allowlist(["Example.COM"])
        self.assertTrue(allow.allows("example.com"))
        self.assertTrue(allow.allows("www.example.com."))


class TestCheck(unittest.TestCase):
    @staticmethod
    def _resolver(ips):
        def _resolve(host, port):
            return ips

        return _resolve

    def test_public_host_allowed(self):
        allowed, reason, ips = check("example.com", 443, resolver=self._resolver(["93.184.216.34"]))
        self.assertTrue(allowed, reason)
        self.assertEqual(ips, ["93.184.216.34"])

    def test_private_ip_denied(self):
        allowed, reason, _ = check("internal.test", 443, resolver=self._resolver(["10.0.0.5"]))
        self.assertFalse(allowed)
        self.assertIn("blocked", reason)

    def test_dns_rebinding_denied(self):
        # One public + one private resolution: the private one must cause a denial.
        allowed, reason, _ = check(
            "rebind.test", 443, resolver=self._resolver(["93.184.216.34", "127.0.0.1"])
        )
        self.assertFalse(allowed)
        self.assertIn("blocked", reason)

    def test_allowlist_enforced(self):
        allow = Allowlist(["good.example.com"])
        allowed, reason, _ = check(
            "evil.test", 443, allowlist=allow, resolver=self._resolver(["93.184.216.34"])
        )
        self.assertFalse(allowed)
        self.assertIn("not allowlisted", reason)

    def test_dns_failure_denied(self):
        import socket

        def _fail(host, port):
            raise socket.gaierror("no such host")

        allowed, reason, _ = check("nope.test", 443, resolver=_fail)
        self.assertFalse(allowed)
        self.assertIn("dns", reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
