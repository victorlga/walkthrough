from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse


class LspError(Exception):
    pass


@dataclass(frozen=True)
class Location:
    uri: str
    line0: int
    char: int


def uri_to_path(uri: str) -> Optional[Path]:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path)).resolve()


def normalize_locations(result) -> List[Location]:
    if not result:
        return []
    items = result if isinstance(result, list) else [result]
    out = []
    for item in items:
        uri = item.get("targetUri") or item.get("uri")
        rng = item.get("targetSelectionRange") or item.get("range")
        if uri and rng:
            out.append(Location(uri=uri, line0=rng["start"]["line"], char=rng["start"]["character"]))
    return out


TOKEN_TYPES = ["namespace", "type", "class", "enum", "interface", "struct", "typeParameter", "parameter",
               "variable", "property", "enumMember", "event", "function", "method", "macro", "keyword",
               "modifier", "comment", "string", "number", "regexp", "operator", "decorator"]
TOKEN_MODIFIERS = ["declaration", "definition", "readonly", "static", "deprecated", "abstract", "async",
                   "modification", "documentation", "defaultLibrary"]

CLIENT_CAPABILITIES = {
    "textDocument": {
        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
        "callHierarchy": {"dynamicRegistration": False},
        "definition": {"linkSupport": True},
        "implementation": {"linkSupport": True},
        "references": {},
        "semanticTokens": {"requests": {"full": True}, "tokenTypes": TOKEN_TYPES, "tokenModifiers": TOKEN_MODIFIERS,
                           "formats": ["relative"]},
    },
    "workspace": {"configuration": True, "workspaceFolders": True},
    "window": {"workDoneProgress": True},
}


class LspServer:
    def __init__(self, command: List[str], root: Path, initialization_options: Optional[dict] = None,
                 timeout: float = 60.0, init_timeout: float = 600.0):
        self.command = command
        self.root = root.resolve()
        self.initialization_options = initialization_options
        self.timeout = timeout
        self.init_timeout = init_timeout
        self.capabilities: Dict = {}
        self.token_types: List[str] = []
        self.opened: set = set()
        self.next_id = 0
        self.responses: Dict[int, dict] = {}
        self.alive = False
        self.condition = threading.Condition()
        self.stderr_lines: deque = deque(maxlen=40)
        self.process: Optional[subprocess.Popen] = None
        self.threads: List[threading.Thread] = []

    def start(self) -> None:
        try:
            self.process = subprocess.Popen(self.command, cwd=self.root, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as error:
            raise LspError(f"{self.command[0]} is not installed") from error
        self.alive = True
        self.threads = [threading.Thread(target=self.read_loop, daemon=True),
                        threading.Thread(target=self.drain_stderr, daemon=True)]
        for thread in self.threads:
            thread.start()
        root_uri = self.root.as_uri()
        result = self.request("initialize", {
            "processId": os.getpid(), "rootUri": root_uri, "rootPath": str(self.root),
            "workspaceFolders": [{"uri": root_uri, "name": self.root.name}],
            "capabilities": CLIENT_CAPABILITIES, "initializationOptions": self.initialization_options,
        }, timeout=self.init_timeout)
        self.capabilities = result.get("capabilities", {})
        legend = (self.capabilities.get("semanticTokensProvider") or {}).get("legend") or {}
        self.token_types = legend.get("tokenTypes", [])
        self.notify("initialized", {})

    def supports(self, capability: str) -> bool:
        return bool(self.capabilities.get(capability))

    def send(self, message: dict) -> None:
        body = json.dumps(message).encode()
        try:
            self.process.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError) as error:
            raise LspError(f"{self.command[0]} exited: {self.stderr_tail()}") from error

    def read_loop(self) -> None:
        stream = self.process.stdout
        try:
            while True:
                length = None
                while True:
                    line = stream.readline()
                    if not line:
                        return
                    line = line.strip()
                    if not line:
                        break
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                message = json.loads(stream.read(length))
                if "method" in message and "id" in message:
                    self.answer_server_request(message)
                elif "id" in message:
                    with self.condition:
                        self.responses[message["id"]] = message
                        self.condition.notify_all()
        finally:
            with self.condition:
                self.alive = False
                self.condition.notify_all()

    def drain_stderr(self) -> None:
        for line in self.process.stderr:
            self.stderr_lines.append(line.decode(errors="replace").rstrip())

    def stderr_tail(self) -> str:
        return "\n".join(self.stderr_lines)

    def answer_server_request(self, message: dict) -> None:
        method = message["method"]
        result = None
        if method == "workspace/configuration":
            result = [{} for _ in message["params"].get("items", [])]
        elif method == "workspace/workspaceFolders":
            result = [{"uri": self.root.as_uri(), "name": self.root.name}]
        self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def request(self, method: str, params, timeout: Optional[float] = None):
        with self.condition:
            self.next_id += 1
            request_id = self.next_id
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.time() + (timeout or self.timeout)
        with self.condition:
            while request_id not in self.responses:
                if not self.alive:
                    raise LspError(f"{self.command[0]} exited during {method}: {self.stderr_tail()}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise LspError(f"{method} timed out after {timeout or self.timeout:.0f}s")
                self.condition.wait(remaining)
            response = self.responses.pop(request_id)
        if "error" in response:
            raise LspError(f"{method} failed: {response['error'].get('message')}")
        return response.get("result")

    def request_many(self, method: str, params_list: list, chunk: int = 200) -> list:
        results = []
        for offset in range(0, len(params_list), chunk):
            part = params_list[offset:offset + chunk]
            with self.condition:
                first = self.next_id + 1
                self.next_id += len(part)
            for number, params in enumerate(part):
                self.send({"jsonrpc": "2.0", "id": first + number, "method": method, "params": params})
            deadline = time.time() + self.timeout
            for request_id in range(first, first + len(part)):
                with self.condition:
                    while request_id not in self.responses:
                        if not self.alive:
                            raise LspError(f"{self.command[0]} exited during {method}: {self.stderr_tail()}")
                        remaining = deadline - time.time()
                        if remaining <= 0:
                            raise LspError(f"{method} batch timed out after {self.timeout:.0f}s")
                        self.condition.wait(remaining)
                    response = self.responses.pop(request_id)
                results.append(None if "error" in response else response.get("result"))
        return results

    def notify(self, method: str, params) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def open(self, path: Path, language_id: str) -> None:
        path = path.resolve()
        if path in self.opened:
            return
        text = path.read_text(errors="replace")
        self.notify("textDocument/didOpen", {"textDocument": {
            "uri": path.as_uri(), "languageId": language_id, "version": 1, "text": text}})
        self.opened.add(path)

    def position(self, path: Path, line0: int, char: int) -> dict:
        return {"textDocument": {"uri": path.resolve().as_uri()}, "position": {"line": line0, "character": char}}

    def document_symbols(self, path: Path) -> list:
        return self.request("textDocument/documentSymbol", {"textDocument": {"uri": path.resolve().as_uri()}}) or []

    def semantic_tokens(self, path: Path) -> Optional[List[int]]:
        if not self.supports("semanticTokensProvider"):
            return None
        result = self.request("textDocument/semanticTokens/full", {"textDocument": {"uri": path.resolve().as_uri()}})
        return (result or {}).get("data")

    def definition(self, path: Path, line0: int, char: int) -> List[Location]:
        return normalize_locations(self.request("textDocument/definition", self.position(path, line0, char)))

    def definitions(self, path: Path, positions: list) -> List[List[Location]]:
        params = [self.position(path, line0, char) for line0, char in positions]
        return [normalize_locations(result) for result in self.request_many("textDocument/definition", params)]

    def implementation(self, path: Path, line0: int, char: int) -> List[Location]:
        if not self.supports("implementationProvider"):
            return []
        return normalize_locations(self.request("textDocument/implementation", self.position(path, line0, char)))

    def prepare_call_hierarchy(self, path: Path, line0: int, char: int) -> List[dict]:
        if not self.supports("callHierarchyProvider"):
            return []
        return self.request("textDocument/prepareCallHierarchy", self.position(path, line0, char)) or []

    def incoming_calls(self, item: dict) -> List[dict]:
        return self.request("callHierarchy/incomingCalls", {"item": item}) or []

    def references(self, path: Path, line0: int, char: int) -> List[Location]:
        params = self.position(path, line0, char)
        params["context"] = {"includeDeclaration": False}
        return normalize_locations(self.request("textDocument/references", params))

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            if self.alive:
                self.request("shutdown", None, timeout=10)
                self.notify("exit", None)
        except LspError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for thread in self.threads:
            thread.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
