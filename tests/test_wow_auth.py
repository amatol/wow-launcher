"""Серверная сторона SRP6 независимо проверяет клиентский обмен."""
import hashlib
import socket
import threading
import unittest
from unittest.mock import patch

from core.wow_auth import authenticate, AuthError, G, N, _session_key


def sha(*items):
    return hashlib.sha1(b''.join(items)).digest()


def read(sock, size):
    data = b''
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise AssertionError('Unexpected EOF')
        data += part
    return data


class WowAuthTests(unittest.TestCase):
    def exchange(self, password='Password1', tamper=False, challenge_result=0, flags=0, token='', server_password='PASSWORD1'):
        client, server = socket.socketpair()
        errors = []
        packets = []

        def serve():
            try:
                with server:
                    header = read(server, 4)
                    self.assertEqual(header[:2], b'\0\x08')
                    body = read(server, int.from_bytes(header[2:], 'little'))
                    self.assertEqual(body[:4], b'WoW\0')
                    self.assertEqual(body[7:9], (12340).to_bytes(2, 'little'))
                    self.assertEqual(body[30:], b'TESTUSER')
                    packets.append(header + body)
                    if challenge_result:
                        server.sendall(bytes((0, 0, challenge_result)))
                        return
                    salt = bytes(range(32))
                    b = 123456789
                    x = int.from_bytes(sha(salt, sha(('TESTUSER:' + server_password).encode('utf-8'))), 'little')
                    v = pow(G, x, N)
                    public_b = ((3 * v + pow(G, b, N)) % N).to_bytes(32, 'little')
                    challenge = (bytes(3) + public_b + bytes((1, G, 32))
                                 + N.to_bytes(32, 'little') + salt + bytes(16) + bytes((flags,)))
                    if flags & 4:
                        challenge += bytes((1,))
                    # Фрагментация на настоящем сокете, а не один recv на пакет.
                    for pos in range(0, len(challenge), 7):
                        server.sendall(challenge[pos:pos + 7])
                    packet = read(server, 75)
                    if flags & 4:
                        count = read(server, 1)[0]
                        self.assertEqual(read(server, count), b'123456')
                    packets.append(packet)
                    a = packet[1:33]
                    u = int.from_bytes(sha(a, public_b), 'little')
                    shared = pow(int.from_bytes(a, 'little') * pow(v, u, N), b, N)
                    key = _session_key(shared.to_bytes(32, 'little'))
                    ng = bytes(i ^ j for i, j in zip(sha(N.to_bytes(32, 'little')), sha(bytes((G,)))))
                    m1 = sha(ng, sha(b'TESTUSER'), salt, a, public_b, key)
                    if packet[33:53] != m1:
                        server.sendall(b'\1\5')
                        return
                    m2 = sha(a, m1, key)
                    if tamper:
                        m2 = bytes(20)
                    server.sendall(b'\1\0' + m2 + bytes(10))
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with patch('core.wow_auth.socket.create_connection', return_value=client):
                return authenticate(' testuser ', password, 'example.test', token=token)
        finally:
            client.close()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            if errors:
                raise errors[0]
            self.assertNotIn(b'PASSWORD1', b''.join(packets))

    def test_success_and_fragmented_packets(self):
        self.assertEqual(self.exchange(), 'TESTUSER')

    def test_wrong_password(self):
        with self.assertRaisesRegex(AuthError, 'Неверный логин или пароль'):
            self.exchange(password='incorrect')

    def test_wrong_server_proof_is_rejected(self):
        with self.assertRaisesRegex(AuthError, 'подлинность'):
            self.exchange(tamper=True)

    def test_banned_and_unknown_accounts(self):
        for code, message in ((3, 'заблокирована'), (4, 'Неверный логин'), (12, 'временная блокировка')):
            with self.subTest(code=code), self.assertRaisesRegex(AuthError, message):
                self.exchange(challenge_result=code)

    def test_authenticator(self):
        self.assertEqual(self.exchange(flags=4, token='123456'), 'TESTUSER')

    def test_password_preserves_non_latin_case_as_azerothcore_does(self):
        self.assertEqual(self.exchange(password='Парольéabc', server_password='ПарольéABC'), 'TESTUSER')

    def test_leading_zero_shared_secret(self):
        shared = b'\0\0' + bytes(range(2, 32))
        left, right = sha(shared[2::2]), sha(shared[3::2])
        self.assertEqual(_session_key(shared), b''.join(bytes((a, b)) for a, b in zip(left, right)))
        self.assertEqual(_session_key(b'\0' + bytes(range(1, 32))), _session_key(shared))


if __name__ == '__main__':
    unittest.main()
