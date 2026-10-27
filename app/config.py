"""多组 API 配置的读写与管理。

配置文件 data/config.json 中，API Key 保存为密文（enc:v1:...），
明文的获取必须显式调用 api_key_of()，避免密钥在界面各处随意流转。
"""

import json
import os
import shutil
import time

from . import paths
from .crypto_utils import default_vault

CONFIG_FILENAME = "config.json"
CONFIG_VERSION = 1
KEEP = object()  # 哨兵：表示「保持原有 API Key 不变」

DEFAULT_SETTINGS = {
    "theme": "dark",
    "proxy": "",
    "timeout": 60,
    "latency_count": 10,
    "latency_concurrency": 1,
    "latency_timeout": 30,
    "latency_target": "models",
    "speed_prompt": "请用一句话介绍人工智能。",
    "speed_max_tokens": 256,
    "speed_temperature": 0.7,
    "speed_stream": True,
    "stability_count": 10,
    "stability_concurrency": 1,
    "stability_timeout": 60,
    "stability_max_tokens": 32,
    "stability_stream": False,
    "stability_prompt": "请回复：测试",
    "report_dir": "",
    "auto_save_report": True,
}


def _now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class ConfigManager(object):
    """管理 data/config.json。"""

    def __init__(self, path=None, vault=None):
        self.path = path or paths.path_in_data(CONFIG_FILENAME)
        self.vault = vault or default_vault()
        self._data = {"version": CONFIG_VERSION, "active": "", "profiles": [], "settings": {}}
        self.load()

    # ------------------------------------------------------------- 读写
    def load(self):
        """读取配置；文件损坏时自动备份为 .bak 并重建。"""
        if not os.path.exists(self.path):
            self._data["settings"] = dict(DEFAULT_SETTINGS)
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                raw = json.load(fp)
        except (ValueError, OSError):
            try:
                shutil.copyfile(self.path, self.path + ".bak")
            except OSError:
                pass
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        settings = dict(DEFAULT_SETTINGS)
        settings.update(raw.get("settings") or {})
        profiles = raw.get("profiles")
        if not isinstance(profiles, list):
            profiles = []
            # 兼容早期只保存单组配置的版本
            if raw.get("base_url"):
                profiles.append({
                    "name": "默认",
                    "base_url": raw.get("base_url", ""),
                    "api_key": raw.get("api_key", ""),
                    "proxy": raw.get("proxy", ""),
                    "created_at": _now_text(),
                })
        cleaned = []
        for item in profiles:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "未命名").strip() or "未命名"
            cleaned.append({
                "name": name,
                "base_url": str(item.get("base_url") or "").strip(),
                "api_key": str(item.get("api_key") or ""),
                "proxy": str(item.get("proxy") or "").strip(),
                "created_at": item.get("created_at") or _now_text(),
                "last_used": item.get("last_used") or "",
            })
        self._data = {
            "version": CONFIG_VERSION,
            "active": str(raw.get("active") or ""),
            "profiles": cleaned,
            "settings": settings,
        }
        if self._data["active"] and not self.get(self._data["active"]):
            self._data["active"] = cleaned[0]["name"] if cleaned else ""
        return self._data

    def save(self):
        """原子写盘，避免中途崩溃损坏配置。"""
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------- 配置档案
    def profiles(self):
        return list(self._data.get("profiles") or [])

    def names(self):
        return [p["name"] for p in self.profiles()]

    def get(self, name):
        for item in self.profiles():
            if item["name"] == name:
                return item
        return None

    def upsert(self, name, base_url, api_key=KEEP, proxy=None, activate=True):
        """新增或更新一组配置。

        api_key 传 KEEP 时保留原值（界面上只回显脱敏内容，不需要重新输入）。
        """
        name = (name or "").strip() or "默认"
        item = self.get(name)
        if item is None:
            item = {
                "name": name,
                "base_url": "",
                "api_key": "",
                "proxy": "",
                "created_at": _now_text(),
                "last_used": "",
            }
            self._data["profiles"].append(item)
        item["base_url"] = (base_url or "").strip()
        if api_key is not KEEP:
            plain = (api_key or "").strip()
            item["api_key"] = self.vault.encrypt(plain) if plain else ""
        if proxy is not None:
            item["proxy"] = (proxy or "").strip()
        if activate:
            self.set_active(name)
        self.save()
        return item

    def rename(self, old_name, new_name):
        new_name = (new_name or "").strip()
        if not new_name or new_name == old_name:
            return False
        if self.get(new_name):
            return False
        item = self.get(old_name)
        if item is None:
            return False
        item["name"] = new_name
        if self._data.get("active") == old_name:
            self._data["active"] = new_name
        self.save()
        return True

    def delete(self, name):
        before = len(self.profiles())
        self._data["profiles"] = [p for p in self.profiles() if p["name"] != name]
        if self._data.get("active") == name:
            rest = self.names()
            self._data["active"] = rest[0] if rest else ""
        self.save()
        return len(self.profiles()) != before

    def set_active(self, name):
        if self.get(name) is None:
            return False
        self._data["active"] = name
        item = self.get(name)
        item["last_used"] = _now_text()
        return True

    def active_name(self):
        return self._data.get("active") or ""

    def active_profile(self):
        return self.get(self.active_name())

    def api_key_of(self, name=None):
        """获取某组配置的明文 API Key。"""
        item = self.get(name) if name else self.active_profile()
        if not item:
            return ""
        return self.vault.decrypt(item.get("api_key"))

    def has_key(self, name=None):
        item = self.get(name) if name else self.active_profile()
        return bool(item and item.get("api_key"))

    # ------------------------------------------------------------- 通用设置
    @property
    def settings(self):
        return self._data.setdefault("settings", dict(DEFAULT_SETTINGS))

    def setting(self, key, default=None):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key, default))

    def update_settings(self, **kwargs):
        self.settings.update(kwargs)
        self.save()

    # ------------------------------------------------------------- 便捷方法
    def client_config(self, name=None):
        """返回 (base_url, api_key, proxy, timeout)，便于直接构造 ApiClient。"""
        item = self.get(name) if name else self.active_profile()
        if not item:
            return "", "", self.setting("proxy", ""), self.setting("timeout", 60)
        return (
            item.get("base_url", ""),
            self.vault.decrypt(item.get("api_key")),
            item.get("proxy") or self.setting("proxy", ""),
            self.setting("timeout", 60),
        )
