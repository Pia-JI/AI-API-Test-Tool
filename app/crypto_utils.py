"""API Key 的本地加密存储。

设计目标：
    1. 配置文件里只出现密文，绝不出现明文 Key；
    2. 密文与本机绑定：把 data/ 目录复制到另一台电脑也无法解密，
       避免配置被顺手拷走就能直接使用他人额度。

实现方式：
    主密钥 = PBKDF2-HMAC-SHA256(机器唯一标识 + 当前用户名, 随机盐)  —— 20 万次迭代
    密文   = Fernet(主密钥) 加密后的 urlsafe-base64 字符串，前缀 "enc:v1:"

随机盐保存在 data/vault.salt 中；机器标识优先取 Windows 注册表 MachineGuid，
取不到时退化为网卡 MAC（uuid.getnode()）。
"""

import base64
import getpass
import os
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import paths

PREFIX = "enc:v1:"
SALT_FILENAME = "vault.salt"
_ITERATIONS = 200000


def _machine_guid():
    """读取 Windows 机器唯一标识，失败时退回 MAC 地址。"""
    try:
        import winreg

        access = winreg.KEY_READ
        # 32 位 Python 也能读取 64 位注册表
        access |= getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            if value:
                return str(value)
    except Exception:
        pass
    return "mac-%d" % uuid.getnode()


class KeyVault(object):
    """负责对 API Key 做加密 / 解密。"""

    def __init__(self, salt_path=None):
        self.salt_path = salt_path or paths.path_in_data(SALT_FILENAME)
        self._fernet = None

    # ------------------------------------------------------------------ 内部
    def _load_salt(self):
        if os.path.exists(self.salt_path):
            with open(self.salt_path, "rb") as fp:
                salt = fp.read()
            if len(salt) >= 16:
                return salt
        salt = os.urandom(16)
        with open(self.salt_path, "wb") as fp:
            fp.write(salt)
        return salt

    def _cipher(self):
        if self._fernet is None:
            material = ("%s|%s" % (_machine_guid(), getpass.getuser())).encode("utf-8")
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._load_salt(),
                iterations=_ITERATIONS,
            )
            key = base64.urlsafe_b64encode(kdf.derive(material))
            self._fernet = Fernet(key)
        return self._fernet

    # ------------------------------------------------------------------ 对外
    @staticmethod
    def is_encrypted(value):
        """判断字符串是否为已加密内容。"""
        return isinstance(value, str) and value.startswith(PREFIX)

    def encrypt(self, plain):
        """加密明文；空值原样返回空串。"""
        if not plain:
            return ""
        if self.is_encrypted(plain):  # 已是密文，避免二次加密
            return plain
        token = self._cipher().encrypt(plain.encode("utf-8")).decode("ascii")
        return PREFIX + token

    def decrypt(self, value):
        """解密；遇到历史明文数据时原样返回（兼容旧配置）。"""
        if not value:
            return ""
        if not self.is_encrypted(value):
            return value
        try:
            return self._cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            # 换机器或盐文件丢失时会走到这里，返回空串让用户重新填写
            return ""

    def mask(self, plain, keep=4):
        """生成用于界面展示的脱敏字符串。"""
        if not plain:
            return ""
        if len(plain) <= keep * 2:
            return "*" * len(plain)
        return "%s%s%s" % (plain[:keep], "*" * 8, plain[-keep:])


_DEFAULT_VAULT = None


def default_vault():
    """全局默认 Vault（懒加载，避免重复派生密钥）。"""
    global _DEFAULT_VAULT
    if _DEFAULT_VAULT is None:
        _DEFAULT_VAULT = KeyVault()
    return _DEFAULT_VAULT
