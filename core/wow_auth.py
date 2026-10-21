"""Проверка действующего аккаунта через SRP6 authserver WoW 3.3.5a.

Пароль не передаётся серверу и не записывается на диск. M2 подтверждает,
что удалённая сторона действительно знает проверочное значение аккаунта.
"""
import hashlib
import hmac
import secrets
import socket
import struct


N = int('894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7', 16)
G = 7


class AuthError(Exception):
    """Безопасное для отображения пользователю сообщение."""


def _sha(*parts):
    return hashlib.sha1(b''.join(parts)).digest()


def _read(sock, size):
    result = bytearray()
    while len(result) < size:
        block = sock.recv(size - len(result))
        if not block:
            raise AuthError('Сервер входа закрыл соединение. Попробуйте ещё раз.')
        result.extend(block)
    return bytes(result)


def _check_result(code):
    if code:
        message = {
            3: 'Учётная запись заблокирована.',
            4: 'Неверный логин или пароль.',
            5: 'Неверный логин или пароль.',
            6: 'Учётная запись уже используется. Попробуйте позже.',
            8: 'Сервер входа занят. Попробуйте позже.',
            9: 'Сервер не принимает эту версию входа. Обновите лаунчер.',
            12: 'Действует временная блокировка учётной записи.',
            16: 'Вход ограничен настройками безопасности аккаунта.',
        }.get(code, 'Сервер отклонил вход. Проверьте аккаунт через Telegram-бота.')
        raise AuthError(message)


def _session_key(shared):
    # AzerothCore пропускает начальные нулевые байты S и выравнивает до пары.
    offset = 0
    while offset < len(shared) and shared[offset] == 0:
        offset += 1
    offset += offset % 2
    left = _sha(shared[offset::2])
    right = _sha(shared[offset + 1::2])
    return b''.join(bytes((a, b)) for a, b in zip(left, right))


def _proof(username, password, server_public, salt, private=None):
    b_value = int.from_bytes(server_public, 'little')
    if not 0 < b_value < N:
        raise AuthError('Некорректный ответ сервера входа.')
    private = private or int.from_bytes(secrets.token_bytes(32), 'little')
    public = pow(G, private, N).to_bytes(32, 'little')
    u = int.from_bytes(_sha(public, server_public), 'little')
    if not u:
        raise AuthError('Некорректный ответ сервера входа.')
    x = int.from_bytes(_sha(salt, _sha(username, b':', password)), 'little')
    shared = pow((b_value - 3 * pow(G, x, N)) % N, private + u * x, N)
    key = _session_key(shared.to_bytes(32, 'little'))
    ng = bytes(a ^ b for a, b in zip(_sha(N.to_bytes(32, 'little')), _sha(bytes((G,)))))
    m1 = _sha(ng, _sha(username), salt, public, server_public, key)
    return public, m1, _sha(public, m1, key)


def authenticate(username, password, host, port=3724, timeout=12, token=''):
    """Выполнить только вход, не подключаясь к игровому миру."""
    if not isinstance(username, str) or not isinstance(password, str):
        raise AuthError('Введите логин и пароль.')
    username = username.strip().upper()
    if not 1 <= len(username) <= 32 or not 1 <= len(password) <= 32:
        raise AuthError('Введите логин и пароль длиной до 32 символов.')
    try:
        user = username.encode('ascii')
        secret = password.upper().encode('ascii')
    except UnicodeError:
        raise AuthError('Используйте латинские символы в логине и пароле.') from None
    body = (b'WoW\x00' + bytes((3, 3, 5)) + struct.pack('<H', 12340)
            + b'68x\x00' + b'niW\x00' + b'URur' + bytes(8) + bytes((len(user),)) + user)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(struct.pack('<BBH', 0, 8, len(body)) + body)
            header = _read(sock, 3)
            if header[:2] != b'\x00\x00':
                raise AuthError('Не удалось распознать ответ сервера входа.')
            _check_result(header[2])
            server_public = _read(sock, 32)
            g_length = _read(sock, 1)[0]
            if g_length != 1 or _read(sock, g_length) != bytes((G,)):
                raise AuthError('Неподдерживаемые параметры сервера входа.')
            n_length = _read(sock, 1)[0]
            if n_length != 32 or _read(sock, n_length) != N.to_bytes(32, 'little'):
                raise AuthError('Неподдерживаемые параметры сервера входа.')
            salt = _read(sock, 32)
            _read(sock, 16)  # Проверка сборки клиента, не пароль.
            flags = _read(sock, 1)[0]
            if flags & ~4:
                raise AuthError('Этот способ дополнительной защиты не поддерживается лаунчером.')
            extra = b''
            if flags & 4:
                _read(sock, 1)
                if not token.isascii() or not token.isdigit() or len(token) != 6:
                    raise AuthError('Введите шестизначный код аутентификатора.')
                extra = bytes((6,)) + token.encode('ascii')
            public, m1, expected_m2 = _proof(user, secret, server_public, salt)
            sock.sendall(b'\x01' + public + m1 + bytes(20) + bytes((0, flags)) + extra)
            command, result = _read(sock, 2)
            if command != 1:
                raise AuthError('Не удалось распознать ответ сервера входа.')
            _check_result(result)
            m2 = _read(sock, 20)
            if not hmac.compare_digest(m2, expected_m2):
                raise AuthError('Не удалось подтвердить подлинность сервера входа.')
            _read(sock, 10)
    except OSError:
        raise AuthError('Сервер входа недоступен. Проверьте подключение и попробуйте ещё раз.') from None
    return username
