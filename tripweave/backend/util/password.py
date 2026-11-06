"""可复用的密码哈希与校验。"""

import hashlib
import hmac
import secrets


def hash_password(password: str, salt: bytes | None = None) -> str:
    """
    使用随机盐和 scrypt 生成密码哈希。

    :param password: 密码。
    :param salt: 随机盐。
    :return: 密码哈希。
    """
    # 如果随机盐为空，则生成随机盐
    salt = salt if salt is not None else secrets.token_bytes(16)
    # 生成密码哈希
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    验证 scrypt 密码哈希。

    :param password: 密码。
    :param stored: 存储的密码哈希。
    :return: 密码是否匹配。
    """
    try:
        algorithm, salt, _ = stored.split("$")
        if algorithm != "scrypt":
            return False
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)
    except ValueError:
        return False
