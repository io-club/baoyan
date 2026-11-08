#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request


NACOS_URL = os.getenv("NACOS_URL", "http://127.0.0.1:28848/nacos")
NACOS_GROUP = "BAOYAN_GROUP"
NACOS_DATA_ID = "baoyan-platform.yaml"
OPENHANDS_URL = os.getenv("OPENHANDS_URL", "http://127.0.0.1:18000")
OPENHANDS_KEY = os.environ["OPENHANDS_LOCAL_BACKEND_API_KEY"]

def request(url: str, *, method: str = "GET", data: bytes | None = None, headers=None):
    request_headers = {"X-Session-API-Key": OPENHANDS_KEY}
    request_headers.update(headers or {})
    req = urllib.request.Request(
        url, data=data, method=method, headers=request_headers
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def read_nacos_settings():
    query = urllib.parse.urlencode(
        {"dataId": NACOS_DATA_ID, "group": NACOS_GROUP}
    )
    with urllib.request.urlopen(f"{NACOS_URL}/v1/cs/configs?{query}", timeout=30) as response:
        content = response.read().decode("utf-8")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required on the host") from exc
    document = yaml.safe_load(content) or {}
    settings = (document.get("baoyan") or {}).get("llm") or {}
    api_key = str(settings.get("api-key") or "").strip()
    model = str(settings.get("model") or "").strip()
    base_url = str(settings.get("base-url") or "").strip()
    if not api_key or not model or not base_url:
        raise RuntimeError("Nacos LLM settings are incomplete")
    return {"api_key": api_key, "model": model, "base_url": base_url}


def configure():
    guidance_url=os.getenv('PLATFORM_GUIDANCE_URL','http://gateway:8080/api/platform/agent-guidance')
    guidance=request(guidance_url,headers={'X-Agent-Key':OPENHANDS_KEY})
    if not guidance.get('version') or not guidance.get('system_prompt'):
        raise RuntimeError('Platform guidance is incomplete')
    existing=request(f"{OPENHANDS_URL}/api/settings")
    suffix=existing.get('agent_settings',{}).get('agent_context',{}).get('system_message_suffix') or ''
    retained_suffix=re.sub(r'<BAOYAN_PLATFORM_API_V\d+>.*?</BAOYAN_PLATFORM_API_V\d+>', '', suffix, flags=re.S).strip()
    llm = read_nacos_settings()
    agent_model=llm['model'] if '/' in llm['model'] else 'openai/'+llm['model']
    profile = {
        "llm": {
            "model": agent_model,
            "api_key": llm["api_key"],
            "base_url": llm["base_url"],
            "auth_type": "api_key",
            "stream": True,
            "native_tool_calling": True,
            "drop_params": True,
        },
        "include_secrets": True,
    }
    request(
        f"{OPENHANDS_URL}/api/profiles/default",
        method="POST",
        data=json.dumps(profile).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    request(
        f"{OPENHANDS_URL}/api/profiles/default/activate",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    payload = {
        "agent_settings_diff": {
            "llm": {
                "model": agent_model,
                "api_key": llm["api_key"],
                "base_url": llm["base_url"],
                "auth_type": "api_key",
                "stream": True,
                "native_tool_calling": True,
                "drop_params": True,
            },
            "agent_context": {"system_message_suffix": retained_suffix,"load_project_skills":True},
        },
        "conversation_settings_diff": {
            "default_runtime": "local",
            "confirmation_mode": False,
            "max_iterations": 100,
        },
    }
    request(
        f"{OPENHANDS_URL}/api/settings",
        method="PATCH",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    for _ in range(30):
        settings = request(f"{OPENHANDS_URL}/api/settings")
        profiles = request(f"{OPENHANDS_URL}/api/profiles")
        if (
            settings.get("llm_api_key_is_set")
            and profiles.get("active_profile") == "default"
            and (settings.get("agent_settings",{}).get("agent_context",{}).get("system_message_suffix") or "") == retained_suffix
        ):
            configured_llm = settings.get("agent_settings", {}).get("llm", {})
            print(
                "OpenHands configured (platform policy injected once at launch):",
                configured_llm.get("model"),
                "key_set=",
                settings.get("llm_api_key_is_set"),
            )
            return
        time.sleep(1)
    raise RuntimeError("OpenHands did not persist the LLM settings")


if __name__ == "__main__":
    configure()

