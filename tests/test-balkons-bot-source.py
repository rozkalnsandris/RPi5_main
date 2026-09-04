#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "ops/lib/balkons-bot.py"
source = SOURCE_PATH.read_text(encoding="utf-8")
tree = ast.parse(source)

assert "<REDACTED_" not in source
assert "/home/" not in source
assert not re.search(r"\b192\.168\.\d{1,3}\.\d{1,3}\b", source)
assert "CREDENTIALS_DIRECTORY" in source
assert "callback_api.VERSION2" in source
assert "CallbackAPIVersion" in source
assert '"telegram-token"' in source
assert '"telegram-chat-id"' in source
assert '"mqtt-host"' in source
assert '"mqtt-username"' in source
assert '"mqtt-secret"' in source
assert '"update_id"' in source
assert '"chat_id"' in source
assert '"balkons/cmd"' in source
assert '"balkons/telegram_out"' in source
assert "Komanda no TG:" not in source
assert "MQTT->TG:" not in source
assert "str(exc)" not in source
assert "repr(exc)" not in source

functions = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
on_connect = functions["on_connect_v2"]
assert [arg.arg for arg in on_connect.args.args] == [
    "client",
    "userdata",
    "connect_flags",
    "reason_code",
    "properties",
]
legacy_connect = functions["on_connect_v1"]
assert [arg.arg for arg in legacy_connect.args.args] == ["client", "userdata", "flags", "rc"]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None

loop_timeout_assignments = [
    node
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(
        isinstance(target, ast.Name) and target.id == "MQTT_LOOP_TIMEOUT_S"
        for target in node.targets
    )
]
assert len(loop_timeout_assignments) == 1
loop_timeout_value = loop_timeout_assignments[0].value
assert isinstance(loop_timeout_value, ast.Constant)
assert isinstance(loop_timeout_value.value, (int, float))
assert 0 < loop_timeout_value.value <= 0.1
assert ".loop_start()" not in source

mqtt_network_loop = functions["_mqtt_network_loop"]
loop_forever_calls = [
    node
    for node in ast.walk(mqtt_network_loop)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "loop_forever"
]
assert len(loop_forever_calls) == 1
loop_forever_call = loop_forever_calls[0]
timeout_arg = _keyword(loop_forever_call, "timeout")
retry_arg = _keyword(loop_forever_call, "retry_first_connection")
assert isinstance(timeout_arg, ast.Name) and timeout_arg.id == "MQTT_LOOP_TIMEOUT_S"
assert isinstance(retry_arg, ast.Constant) and retry_arg.value is True

start_mqtt = functions["_start_mqtt"]
thread_calls = [
    node
    for node in ast.walk(start_mqtt)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id == "threading"
    and node.func.attr == "Thread"
]
assert len(thread_calls) == 1
thread_call = thread_calls[0]
target_arg = _keyword(thread_call, "target")
daemon_arg = _keyword(thread_call, "daemon")
name_arg = _keyword(thread_call, "name")
assert isinstance(target_arg, ast.Name) and target_arg.id == "_mqtt_network_loop"
assert isinstance(daemon_arg, ast.Constant) and daemon_arg.value is True
assert isinstance(name_arg, ast.Constant) and name_arg.value == "balkons-mqtt"

sensitive_names = {
    "BOT_TOKEN",
    "CHAT_ID",
    "MQTT_USER",
    "MQTT_PASS",
    "MQTT_PASSWORD",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
}
for node in ast.walk(tree):
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        continue
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    value = node.value
    for target in targets:
        if isinstance(target, ast.Name) and target.id in sensitive_names:
            assert not (isinstance(value, ast.Constant) and isinstance(value.value, str))

expected_command_literals = {
    "laist",
    "stop",
    "mitrums",
    "statuss",
    "raw",
}
constants = {
    node.value
    for node in ast.walk(tree)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
}
assert expected_command_literals <= constants

print("Balkons bot source tests: PASS")
