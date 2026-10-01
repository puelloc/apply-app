import email
import imaplib
import socketserver
import threading
import unittest

import mock_imap


class TestMockImap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mock_imap.PORT = 19143
        mock_imap.ALIAS = "jobs+job1@example.invalid"
        mock_imap.VERIFY_URL = "https://acme.com/verify?t=canary"
        cls.server = socketserver.ThreadingTCPServer(("127.0.0.1", mock_imap.PORT), mock_imap.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_login_search_fetch(self):
        conn = imaplib.IMAP4("127.0.0.1", mock_imap.PORT)
        conn.login("user", "pass")
        conn.select("INBOX")
        status, data = conn.search(None, "TO", '"jobs+job1@example.invalid"')
        self.assertEqual(status, "OK")
        ids = data[0].split()
        self.assertTrue(ids)
        status, msgdata = conn.fetch(ids[0], "(RFC822)")
        msg = email.message_from_bytes(msgdata[0][1])
        self.assertEqual(msg["To"], "jobs+job1@example.invalid")
        self.assertIn("https://acme.com/verify?t=canary", msg.get_payload(decode=True).decode())
        conn.logout()


if __name__ == "__main__":
    unittest.main(verbosity=2)
