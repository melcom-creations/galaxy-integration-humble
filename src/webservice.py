"""Handle Humble account sessions, browser sign-in, and library requests."""

import ctypes
from ctypes import wintypes as w
import html
import json
import re
import asyncio
import logging
import time
from http.cookies import SimpleCookie
import aiohttp
import yarl
from galaxy.api.errors import AuthenticationRequired, AccessDenied, BackendNotAvailable, BackendTimeout, NetworkError, TooManyRequests, UnknownBackendResponse
from galaxy.http import handle_exception
from galaxy.api.errors import UnknownBackendResponse
import struct
import pathlib
import tempfile
import os
import shutil
import secrets
import sqlite3
import socket
import subprocess
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from typing import Optional
from aiohttp import web
from galaxy.api.errors import AuthenticationRequired, BackendError, BackendNotAvailable, BackendTimeout, AccessDenied, NetworkError


LIBRARY = "https://www.humblebundle.com/home/library"


def library_post(headers, body, path="/home/library"):
    dll = ctypes.WinDLL("winhttp", use_last_error=True)

    def bind(name, result, args):
        method = getattr(dll, name)
        method.restype, method.argtypes = result, args
        return method

    open_session = bind("WinHttpOpen", w.HANDLE, [w.LPCWSTR, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD])
    connect = bind("WinHttpConnect", w.HANDLE, [w.HANDLE, w.LPCWSTR, w.WORD, w.DWORD])
    open_request = bind("WinHttpOpenRequest", w.HANDLE, [w.HANDLE, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p, w.DWORD])
    option = bind("WinHttpSetOption", w.BOOL, [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD])
    query_option = bind("WinHttpQueryOption", w.BOOL, [w.HANDLE, w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.DWORD)])
    timeouts = bind("WinHttpSetTimeouts", w.BOOL, [w.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int])
    send = bind("WinHttpSendRequest", w.BOOL, [w.HANDLE, w.LPCWSTR, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_size_t])
    receive = bind("WinHttpReceiveResponse", w.BOOL, [w.HANDLE, ctypes.c_void_p])
    query = bind("WinHttpQueryHeaders", w.BOOL, [w.HANDLE, w.DWORD, w.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(w.DWORD), ctypes.c_void_p])
    read = bind("WinHttpReadData", w.BOOL, [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)])
    close = bind("WinHttpCloseHandle", w.BOOL, [w.HANDLE])

    def require(value):
        if not value:
            raise OSError(ctypes.get_last_error(), "Windows HTTP operation failed")
        return value

    handles = []
    try:
        session = require(open_session("HumbleBundle integration for GOG Galaxy", 4, None, None, 0))
        handles.append(session)
        require(timeouts(session, 10000, 10000, 20000, 20000))
        enabled = w.DWORD(1)
        require(option(session, 133, ctypes.byref(enabled), ctypes.sizeof(enabled)))
        connection = require(connect(session, "www.humblebundle.com", 443, 0))
        handles.append(connection)
        request = require(open_request(connection, "POST", path, None, LIBRARY, None, 0x00800000))
        handles.append(request)
        # Keep credentials on the original endpoint if a redirect is returned.
        policy = w.DWORD(0)
        require(option(request, 88, ctypes.byref(policy), ctypes.sizeof(policy)))
        buffer = ctypes.create_string_buffer(body)
        require(send(request, headers, len(headers), buffer, len(body), len(body), 0))
        require(receive(request, None))
        status, size = w.DWORD(), w.DWORD(4)
        require(query(request, 19 | 0x20000000, None, ctypes.byref(status), ctypes.byref(size), None))
        protocol, size = w.DWORD(), w.DWORD(4)
        require(query_option(request, 134, ctypes.byref(protocol), ctypes.byref(size)))
        header_size = w.DWORD()
        query(request, 22, None, None, ctypes.byref(header_size), None)
        raw_headers = ctypes.create_unicode_buffer(max(1, header_size.value // 2))
        require(query(request, 22, None, raw_headers, ctypes.byref(header_size), None))
        renewed = [line.split(":", 1)[1].strip() for line in raw_headers.value.split("\r\n")
                   if line.lower().startswith("set-cookie:")]
        chunks = []
        while True:
            block = ctypes.create_string_buffer(16384)
            count = w.DWORD()
            require(read(request, block, len(block), ctypes.byref(count)))
            if not count.value:
                break
            chunks.append(block.raw[:count.value])
            if sum(map(len, chunks)) > 8 * 1024 * 1024:
                raise ValueError("Library response exceeds the size limit")
        return status.value, protocol.value, b"".join(chunks).decode("utf-8", errors="replace"), renewed
    finally:
        for handle in reversed(handles):
            close(handle)


SITE = "https://www.humblebundle.com"
AUTH = "https://auth.humblebundle.com"
LIBRARY = SITE + "/home/library"
LOGIN = AUTH + "/self-service/login/browser?return_to=" + str(yarl.URL(LIBRARY)).replace(":", "%3A").replace("/", "%2F")


def is_session_cookie(name):
    if not isinstance(name, str):
        return False
    for prefix in ("__Host-", "__Secure-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name == "ory_kratos_session" or name.startswith("ory_session_")


def flight_models(document):
    """Extract JSON model records without evaluating scripts from the website."""
    streams = []
    for match in re.finditer(r'self\.__next_f\.push\((\[1,.*?\])\)', document):
        try:
            streams.append(json.loads(match.group(1))[1])
        except (ValueError, IndexError, TypeError):
            continue
    stream = "".join(streams) if streams else document
    result = {}
    for match in re.finditer(r'(?:^|\n)([0-9a-f]+):', stream):
        try:
            value, _ = json.JSONDecoder().raw_decode(stream[match.end():])
        except ValueError:
            continue
        result[match.group(1)] = value
    return result


def resolve_model(value, models, seen=()):
    if isinstance(value, str) and re.fullmatch(r'\$[0-9a-f]+', value):
        key = value[1:]
        if key in models and key not in seen:
            return resolve_model(models[key], models, seen + (key,))
    if isinstance(value, dict):
        return {key: resolve_model(item, models, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_model(item, models, seen) for item in value]
    return value


class RelaunchClient:
    def __init__(self, headers=None, credentials_callback=None):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "HumbleBundle integration for GOG Galaxy", "Accept": "application/json", **(headers or {})}, timeout=aiohttp.ClientTimeout(total=20))
        self.identity = None
        self.action = None
        self.authenticated = False
        self.credentials_callback = credentials_callback
        self._last_credentials = None
        self.items = None
        self.state = {}
        self.migration_incomplete = True
        self._refresh_lock = asyncio.Lock()
        self._refreshed_at = 0

    def load_cookies(self, cookies):
        """Keep cookie scope intact and accept only Humble session cookies."""
        accepted = []
        self.session.cookie_jar.clear(lambda cookie: is_session_cookie(cookie.key))
        for item in cookies:
            if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
                continue
            name = item.get("name", "")
            domain = item.get("domain", "").lower().lstrip(".")
            if domain not in {"humblebundle.com", "www.humblebundle.com", "auth.humblebundle.com"}:
                continue
            if not is_session_cookie(name):
                continue
            if not isinstance(item.get("value"), str) or not item["value"]:
                continue
            cookie = SimpleCookie()
            cookie[name] = item["value"]
            if str(item["domain"]).startswith('.'):
                cookie[name]["domain"] = item["domain"]
            cookie[name]["path"] = item.get("path") or "/"
            cookie[name]["secure"] = True
            self.session.cookie_jar.update_cookies(cookie, response_url=yarl.URL("https://" + domain))
            accepted.append(name)
        return accepted

    async def identity_data(self):
        with handle_exception():
            async with self.session.get(AUTH + "/sessions/whoami", allow_redirects=False) as response:
                response.raise_for_status()
                data = await response.json()
        if not data.get("active") or not isinstance(data.get("identity"), dict):
            raise AuthenticationRequired()
        self.identity = data["identity"]
        return self.identity

    async def authenticate(self, credentials):
        self.authenticated = False
        if not isinstance(credentials, dict) or not isinstance(credentials.get("cookies"), list):
            raise AuthenticationRequired()
        if not self.load_cookies(credentials["cookies"]):
            raise AuthenticationRequired()
        identity = await self.identity_data()
        if not isinstance(identity.get("id"), str) or not identity["id"]:
            raise UnknownBackendResponse("Humble identity has no identifier")
        if credentials.get("user_id") and credentials["user_id"] != identity["id"]:
            raise AuthenticationRequired()
        self.authenticated = True
        self.save_credentials()
        return identity["id"]

    def save_credentials(self):
        if not self.authenticated or self.credentials_callback is None:
            return
        cookies = []
        for cookie in self.session.cookie_jar:
            if not is_session_cookie(cookie.key):
                continue
            domain = cookie["domain"]
            if (domain, cookie.key) not in self.session.cookie_jar._host_only_cookies:
                domain = "." + domain.lstrip('.')
            cookies.append({"name": cookie.key, "value": cookie.value, "domain": domain,
                            "path": cookie["path"] or "/", "secure": True})
        payload = {"type": "ory", "user_id": self.identity["id"], "cookies": sorted(cookies, key=lambda item: (item["domain"], item["name"], item["path"]))}
        serialized = json.dumps(payload, sort_keys=True)
        if cookies and serialized != self._last_credentials:
            self.credentials_callback(payload)
            self._last_credentials = serialized

    async def library_page(self):
        with handle_exception():
            async with self.session.get(LIBRARY, headers={"Accept": "text/html"}) as response:
                response.raise_for_status()
                return await response.text()

    async def find_library_action(self, document):
        # Action identifiers change between deployments, so resolve the current one.
        scripts = dict.fromkeys(re.findall(r'<script[^>]+src="([^"?]+\.js)"', document))
        for path in scripts:
            if not path.startswith("/_next/static/chunks/") or ".." in path:
                continue
            async with self.session.get(SITE + html.unescape(path)) as response:
                response.raise_for_status()
                script = await response.text()
            match = re.search(r'createServerReference\)\("([0-9a-f]+)"[^;]{0,180}"filterUserLibrary"', script)
            if match:
                self.action = match.group(1)
                return self.action
        raise ValueError("Humble library action was not found")

    async def library_page_data(self, page=1, limit=5):
        if not self.action:
            raise ValueError("Humble library action is unavailable")
        data = aiohttp.FormData()
        state = {"results": [], "pagination": {"page": 1, "totalPages": 1, "totalDocs": 0}, "success": True}
        for key, value in {"requestId": "1", "query": "", "sort": "mostRecent", "cursor": str(page * limit), "page": str(page), "limit": str(limit), "hideRevealed": "false", "hideExpired": "false", "dateExpires": ""}.items():
            data.add_field("_1_" + key, value)
        data.add_field("0", json.dumps([state, "$K1"]), content_type="text/plain")
        payload = data()
        parts = []

        class Writer:
            async def write(self, chunk):
                parts.append(chunk)

        await payload.write(Writer())
        cookies = self.session.cookie_jar.filter_cookies(yarl.URL(LIBRARY)).output(header="", sep=";").strip()
        headers = "\r\n".join(("Cookie: " + cookies, "Next-Action: " + self.action,
            "Accept: text/x-component", "Origin: " + SITE, "Content-Type: " + payload.headers["Content-Type"])) + "\r\n"
        try:
            status, protocol, document, renewed = await asyncio.to_thread(library_post, headers, b"".join(parts))
        except OSError as error:
            if error.errno == 12002:
                raise BackendTimeout() from None
            raise NetworkError("Humble library connection failed") from None
        if status == 401:
            self.authenticated = False
            raise AuthenticationRequired()
        if status == 403:
            raise AccessDenied("Humble rejected the library request")
        if status >= 500:
            raise BackendNotAvailable()
        if status == 429:
            raise TooManyRequests()
        if status != 200:
            raise UnknownBackendResponse("Unexpected Humble library status: " + str(status))
        for header in renewed:
            parsed = SimpleCookie()
            parsed.load(header)
            for name, cookie in parsed.items():
                if is_session_cookie(name):
                    self.session.cookie_jar.update_cookies({name: cookie}, response_url=yarl.URL(LIBRARY))
        models = flight_models(document)
        for value in models.values():
            resolved = resolve_model(value, models)
            if isinstance(resolved, dict) and "success" in resolved:
                if resolved.get("success") is not True or not isinstance(resolved.get("results"), list):
                    raise UnknownBackendResponse("Humble did not return a complete library page")
                self.save_credentials()
                return resolved
        raise ValueError("Unrecognized Humble library response")

    async def refresh_library(self):
        async with self._refresh_lock:
            if self.items is not None and time.monotonic() - self._refreshed_at < 60:
                return self.items
            try:
                await self.identity_data()
            except AuthenticationRequired:
                self.authenticated = False
                raise
            document = await self.library_page()
            models = flight_models(document)
            state = {}

            def visit(value):
                if isinstance(value, dict):
                    if "hasActiveSubscription" in value and "bundleItems" in value:
                        state.update(value)
                    else:
                        for item in value.values():
                            visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)

            for model in models.values():
                visit(resolve_model(model, models))
            await self.find_library_action(document)
            records, seen = [], set()
            expected = None
            page = 1
            while True:
                data = await self.library_page_data(page, 50)
                pagination = data.get("pagination", {})
                if pagination.get("page") != page:
                    raise UnknownBackendResponse("Humble returned the wrong library page")
                total = pagination.get("totalDocs")
                pages = pagination.get("totalPages")
                if not isinstance(total, int) or not isinstance(pages, int) or total < 0 or not 1 <= pages <= 20000:
                    raise UnknownBackendResponse("Invalid Humble library pagination")
                if expected is not None and expected != total:
                    raise BackendNotAvailable("Humble library changed during synchronization; retry later")
                expected = total
                for row in data["results"]:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                        raise UnknownBackendResponse("Invalid Humble library item")
                    if row["id"] not in seen:
                        records.append(row)
                        seen.add(row["id"])
                if page >= pages:
                    break
                page += 1
            if len(records) != expected:
                raise UnknownBackendResponse("Humble library import is incomplete")
            rendered = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.I | re.S)
            self.migration_incomplete = "still moving a few things in" in html.unescape(rendered).lower()
            self.items, self.state = records, state
            self._refreshed_at = time.monotonic()
            self.save_credentials()
            logging.getLogger(__name__).info("Read %d Humble library items across %d pages", len(records), page)
            return records

    async def product_details(self, parent_id, item_id=None):
        identifier = item_id or parent_id
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', identifier):
            raise UnknownBackendResponse("Invalid Humble content identifier")
        path = "/home/library/content/" + identifier if item_id else "/home/library/" + identifier
        with handle_exception():
            async with self.session.get(SITE + path, headers={"Accept": "text/html"}) as response:
                if response.status == 404:
                    raise UnknownBackendResponse("Humble content details are unavailable")
                response.raise_for_status()
                document = await response.text()
        models = flight_models(document)
        matches = []

        def visit(value):
            if isinstance(value, dict):
                if isinstance(value.get("entitlements"), dict) and isinstance(value.get("title"), str):
                    matches.append(value)
                    return
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        for model in models.values():
            visit(resolve_model(model, models))
        self.save_credentials()
        if not matches:
            raise UnknownBackendResponse("Humble content details are unavailable")

        def file_count(item):
            total = 0
            entries = item.get("entitlements", {}).get("downloads", [])
            if not isinstance(entries, list):
                return 0
            for entitlement in entries:
                downloads = entitlement.get("downloads")
                if isinstance(downloads, list):
                    total += sum(len(download.get("downloadStruct", [])) for download in downloads)
            return total

        return max(matches, key=file_count)

    def presentation_url(self, identifier, title=None):
        for row in self.items or []:
            if row.get('contentId') == identifier or (isinstance(title, str) and str(row.get('title', '')).casefold() == title.casefold()):
                item_id = row.get('id')
                if isinstance(item_id, str) and re.fullmatch(r'[a-zA-Z0-9_-]+', item_id):
                    return SITE + '/home/library/content/' + item_id
        return LIBRARY

    async def close(self):
        await self.session.close()


KEY_TYPES = {"steam": ("steam", "Steam"), "origin": ("origin", "Origin"),
             "uplay": ("uplay", "Uplay"), "ubisoft": ("uplay", "Uplay"),
             "epic": ("epic", "Epic Games"), "gog": ("gog", "GOG"),
             "gog_keyless": ("gog", "GOG"), "battlenet": ("battlenet", "Battle.net"),
             "blizzard": ("battlenet", "Battle.net"), "blizzard_keyless": ("battlenet", "Battle.net")}


def _text(value):
    return isinstance(value, str) and value and not value.startswith('$')


def _known_games(orders):
    titles, identifiers = {}, set()
    for order in orders.values():
        for game in order.get("subproducts", []):
            machine = game.get("machine_name")
            if _text(machine):
                identifiers.add(machine)
                title = game.get("human_name")
                if _text(title):
                    titles[title.casefold()] = machine
        for game in order.get("tpkd_dict", {}).get("all_tpks", []):
            if _text(game.get("machine_name")):
                identifiers.add(game["machine_name"])
    return titles, identifiers


def _download_data(row, details, machine):
    records = []
    entries = details.get("entitlements", {}).get("downloads", [])
    for item in entries if isinstance(entries, list) else []:
        if item.get("id") != row["id"]:
            continue
        downloads = item.get("downloads")
        if not isinstance(downloads, list):
            continue
        for download in downloads:
            platform = download.get("platform")
            if platform not in {"windows", "mac", "linux"}:
                continue
            structures = []
            for file in download.get("downloadStruct", []):
                url = file.get("url")
                if not isinstance(url, dict) or not _text(url.get("web")):
                    continue
                size = file.get("size")
                if not _text(size):
                    size = str(file.get("fileSize", 0)) + " bytes"
                structures.append({"url": url, "human_size": size,
                    "name": file.get("name") or "Download", "md5": file.get("md5"),
                    "uploaded_at": file.get("uploadedAt")})
            if structures:
                records.append({"platform": platform, "machine_name": download.get("key") or machine,
                                "download_struct": structures})
    return records


async def library_orders(client, previous):
    rows = await client.refresh_library()
    titles, known = _known_games(previous)
    groups = {}
    for row in rows:
        parent = row.get("productEntitlementId")
        if not _text(parent):
            parent = row["id"]
        groups.setdefault(parent, []).append(row)
    semaphore = asyncio.Semaphore(4)

    async def convert(parent, items):
        keys = [key for row in items if isinstance(row.get("entitlements"), dict)
                for key in row["entitlements"].get("keys", [])]
        has_game_key = any(key.get("keyIntegrationId", key.get("type")) in KEY_TYPES for key in keys)
        was_game = any(row.get("contentId") in known or str(row.get("title", "")).casefold() in titles for row in items)
        # Cached game identities keep older bundles usable when their license type is unknown.
        if keys and not has_game_key and not was_game:
            return None
        downloads = [row for row in items if row.get("type") == "download_drm_free"]
        details = None
        if downloads:
            async with semaphore:
                try:
                    details = await client.product_details(parent)
                except UnknownBackendResponse:
                    details = {"entitlements": {"downloads": []}}
                    for row in downloads:
                        try:
                            content = await client.product_details(parent, row["id"])
                        except UnknownBackendResponse:
                            if not client.migration_incomplete:
                                raise
                            logging.getLogger(__name__).debug("Humble has no available download details for %s", row.get("contentId"))
                            continue
                        details["entitlements"]["downloads"].extend(content.get("entitlements", {}).get("downloads", []))
        order = {"product": {"machine_name": "humble_" + parent + "_gamebundle",
                  "category": "bundle", "human_name": items[0].get("subTitle") or items[0]["title"]},
                 "subproducts": [], "tpkd_dict": {"all_tpks": []}}
        for row in items:
            if not _text(row.get("contentId")) or not _text(row.get("title")):
                continue
            name, machine = row["title"], row["contentId"]
            if row.get("type") == "download_drm_free":
                machine = titles.get(name.casefold(), machine)
                records = _download_data(row, details or {}, machine)
                if records:
                    order["subproducts"].append({"machine_name": machine, "human_name": name,
                        "downloads": records, "library_url": SITE + "/home/library/content/" + row["id"]})
            entitlements = row.get("entitlements")
            for key in entitlements.get("keys", []) if isinstance(entitlements, dict) else []:
                integration = key.get("keyIntegrationId", key.get("type"))
                if integration not in KEY_TYPES or key.get("giftStatus") == "gifted":
                    continue
                kind, label = KEY_TYPES[integration]
                redemption = key.get("redemptionData")
                revealed = _text(key.get("redeemedAt")) or (isinstance(redemption, dict) and _text(redemption.get("keyFormatted")))
                order["tpkd_dict"]["all_tpks"].append({"machine_name": row["contentId"],
                    "human_name": name, "key_type": kind, "key_type_human_name": label,
                    "redeemed_key_val": "revealed" if revealed else None,
                    "library_url": SITE + "/home/library/content/" + row["id"]})
        return parent, order

    converted = await asyncio.gather(*(convert(parent, items) for parent, items in groups.items()))
    result = {parent: order for entry in converted if entry is not None for parent, order in [entry]}
    # Keep already verified titles while Humble is still migrating historical purchases.
    if client.migration_incomplete:
        for key, prior in previous.items():
            if key not in result:
                result[key] = prior
                continue
            current = result[key]
            known_subproducts = {game['machine_name'] for game in current['subproducts']}
            current['subproducts'].extend(game for game in prior.get('subproducts', []) if game.get('machine_name') not in known_subproducts)
            known_keys = {game['machine_name'] for game in current['tpkd_dict']['all_tpks']}
            current['tpkd_dict']['all_tpks'].extend(game for game in prior.get('tpkd_dict', {}).get('all_tpks', []) if game.get('machine_name') not in known_keys)
    logging.getLogger(__name__).info("Prepared %d Humble order groups; migration incomplete=%s", len(result), client.migration_incomplete)
    return result


MAX_SESSION_BYTES = 16 * 1024 * 1024


def decode_jsonlz4(data):
    if len(data) < 12 or data[:8] != b"mozLz40\0":
        raise ValueError("Invalid Firefox session header")
    expected = struct.unpack_from("<I", data, 8)[0]
    if expected > MAX_SESSION_BYTES:
        raise ValueError("Firefox session exceeds the size limit")
    position = 12
    output = bytearray()

    def length(initial):
        nonlocal position
        total = initial
        if initial == 15:
            while True:
                if position >= len(data):
                    raise ValueError("Truncated Firefox session block")
                extra = data[position]
                position += 1
                total += extra
                if extra != 255:
                    break
        return total

    while position < len(data):
        token = data[position]
        position += 1
        literals = length(token >> 4)
        if position + literals > len(data) or len(output) + literals > expected:
            raise ValueError("Invalid Firefox session literal length")
        output.extend(data[position:position + literals])
        position += literals
        if position == len(data):
            break
        if position + 2 > len(data):
            raise ValueError("Truncated Firefox session match")
        offset = struct.unpack_from("<H", data, position)[0]
        position += 2
        count = length(token & 15) + 4
        if offset == 0 or offset > len(output) or len(output) + count > expected:
            raise ValueError("Invalid Firefox session match")
        for _ in range(count):
            output.append(output[-offset])
    if len(output) != expected:
        raise ValueError("Firefox session length does not match its header")
    return output.decode("utf-8")


def cookie_arrays(document):
    """Decode cookie arrays without parsing form data, tab URLs, or history."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r'"cookies"\s*:\s*\[', document):
        try:
            cookies, _ = decoder.raw_decode(document[match.end() - 1:])
        except ValueError:
            continue
        if isinstance(cookies, list):
            yield from (cookie for cookie in cookies if isinstance(cookie, dict))


def session_cookies(profile):
    filenames = (profile / "sessionstore-backups" / "recovery.jsonlz4",
                 profile / "sessionstore.jsonlz4",
                 profile / "sessionstore-backups" / "recovery.baklz4")
    for filename in filenames:
        if filename.is_symlink():
            continue
        try:
            if filename.stat().st_size > MAX_SESSION_BYTES:
                continue
            document = decode_jsonlz4(filename.read_bytes())
        except (OSError, ValueError):
            continue
        yield from cookie_arrays(document)
        return


class UniqueProcess(ctypes.Structure):
    _fields_ = [("pid", w.DWORD), ("started", w.FILETIME)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("process", UniqueProcess), ("app", w.WCHAR * 256),
                ("service", w.WCHAR * 64), ("kind", ctypes.c_int),
                ("status", w.ULONG), ("session", w.DWORD), ("restartable", w.BOOL)]


def profile_processes(profile):
    profile = pathlib.Path(profile).resolve()
    if (profile.parent != pathlib.Path(tempfile.gettempdir()).resolve()
            or not profile.name.startswith("melcom-humble-auth-")
            or not (profile / ".humble-temporary-profile").is_file()):
        raise ValueError("Unrecognized Humble login profile")
    dll = ctypes.WinDLL("rstrtmgr", use_last_error=True)
    start = dll.RmStartSession
    start.argtypes, start.restype = [ctypes.POINTER(w.DWORD), w.DWORD, w.LPWSTR], w.DWORD
    register = dll.RmRegisterResources
    register.argtypes = [w.DWORD, w.UINT, ctypes.POINTER(w.LPCWSTR), w.UINT, ctypes.c_void_p, w.UINT, ctypes.c_void_p]
    register.restype = w.DWORD
    get = dll.RmGetList
    get.argtypes = [w.DWORD, ctypes.POINTER(w.UINT), ctypes.POINTER(w.UINT), ctypes.POINTER(ProcessInfo), ctypes.POINTER(w.DWORD)]
    get.restype = w.DWORD
    end = dll.RmEndSession
    end.argtypes, end.restype = [w.DWORD], w.DWORD
    session, key = w.DWORD(), ctypes.create_unicode_buffer(33)
    code = start(ctypes.byref(session), 0, key)
    if code:
        raise OSError(code, "Could not inspect the owned Firefox profile")
    try:
        paths = (w.LPCWSTR * 1)(str(profile / "parent.lock"))
        code = register(session, 1, paths, 0, None, 0, None)
        if code:
            raise OSError(code, "Could not register the owned Firefox lock")
        needed, count, reasons = w.UINT(), w.UINT(), w.DWORD()
        code = get(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
        if code == 0:
            return []
        if code != 234:
            raise OSError(code, "Could not inspect the Firefox lock owner")
        records = (ProcessInfo * needed.value)()
        count.value = needed.value
        code = get(session, ctypes.byref(needed), ctypes.byref(count), records, ctypes.byref(reasons))
        if code:
            raise OSError(code, "Could not enumerate the Firefox lock owner")
        return [(record.process.pid, record.process.started) for record in records[:count.value]]
    finally:
        end(session)


def close_profile(profile):
    owners = profile_processes(profile)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = w.BOOL
    kernel.GetProcessTimes.argtypes = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME)]
    kernel.GetProcessTimes.restype = w.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.TerminateProcess.argtypes, kernel.TerminateProcess.restype = [w.HANDLE, w.UINT], w.BOOL
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowThreadProcessId.restype = w.DWORD
    user.PostMessageW.argtypes, user.PostMessageW.restype = [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL
    accepted = set()
    for pid, started in owners:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            path, length = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            created, exited, system, used = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
                continue
            if pathlib.Path(path.value).name.lower() not in {"firefox.exe", "waterfox.exe", "librewolf.exe", "floorp.exe", "zen.exe"}:
                continue
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(used)):
                continue
            if (created.dwLowDateTime, created.dwHighDateTime) != (started.dwLowDateTime, started.dwHighDateTime):
                continue
            accepted.add(pid)
        finally:
            kernel.CloseHandle(handle)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

    @callback_type
    def close_window(window, context):
        pid = w.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value in accepted:
            user.PostMessageW(window, 0x0010, 0, 0)
        return True

    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, w.LPARAM], w.BOOL
    user.EnumWindows(close_window, 0)
    for _ in range(30):
        if not profile_processes(profile):
            break
        time.sleep(0.1)
    for pid, started in profile_processes(profile):
        if pid not in accepted:
            continue
        handle = kernel.OpenProcess(0x1001, False, pid)
        if not handle:
            continue
        try:
            created, exited, system, used = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
            if (kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(used))
                    and (created.dwLowDateTime, created.dwHighDateTime) == (started.dwLowDateTime, started.dwHighDateTime)):
                kernel.TerminateProcess(handle, 0)
        finally:
            kernel.CloseHandle(handle)
    for _ in range(10):
        if not profile_processes(profile):
            break
        time.sleep(0.1)
    return sorted(accepted)


logger = logging.getLogger(__name__)
LOGIN_URL = LOGIN
FORM_PATH = "/"
OPEN_PATH = "/open"
STATUS_PATH = "/status"
COMPLETE_PATH = "/complete"
TEMP_PROFILE_PREFIX = "melcom-humble-auth-"
TEMP_PROFILE_MARKER = ".humble-temporary-profile"

_FORM_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Connect Humble Bundle</title>
<style>body{font:14px "Segoe UI",sans-serif;background:#151515;color:#eee;margin:0;padding:18px;line-height:1.45}
h2{font-size:19px;margin:0 0 10px}p{margin:10px 0;overflow-wrap:anywhere}
button{background:#7752b8;color:white;border:0;border-radius:4px;padding:12px 20px;cursor:pointer}</style></head>
<body><h2>Connect Humble Bundle</h2>
<p>Sign in to Humble in your default browser. Keep this window open.</p>
<button id="open" hidden>Open Humble Login</button><p id="status">Waiting for sign-in...</p>
<script>
const nonce=__NONCE__, button=document.getElementById('open'), statusBox=document.getElementById('status');
let requested=false;
function openLogin(){if(requested){return;}requested=true;button.disabled=true;fetch('/open?nonce='+encodeURIComponent(nonce),{method:'POST'})
.then(r=>r.json()).then(d=>{if(d.state==='error'){statusBox.textContent=d.message;button.disabled=false;}})
.catch(()=>{statusBox.textContent='Could not open the login window.';button.hidden=false;button.disabled=false;});}
button.onclick=function(){requested=false;openLogin();};
function openWhenShown(){if(document.visibilityState==='visible'){openLogin();}}
window.addEventListener('focus',openWhenShown);
window.addEventListener('pageshow',openWhenShown);
document.addEventListener('visibilitychange',openWhenShown);
openWhenShown();
setInterval(function(){fetch('/status?nonce='+encodeURIComponent(nonce),{cache:'no-store'}).then(r=>r.json()).then(d=>{
if(d.state==='ready'){window.location.href='/complete';}
else if(d.state==='waiting'){statusBox.textContent='Waiting for sign-in...';}
else if(d.state==='error'){statusBox.textContent=d.message;button.hidden=false;button.disabled=false;}}).catch(()=>{});},250);
</script></body></html>"""
_COMPLETE_HTML = "<!DOCTYPE html><html lang='en'><title>Humble login verified</title><p>You can close this window.</p></html>"

@dataclass
class BrowserAuthResult:
    cookies: list[dict]
    user_id: str
    user_name: str


def _create_temporary_browser_profile(browser_kind: str) -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    profile_path = Path(
        tempfile.mkdtemp(
            prefix=f"{TEMP_PROFILE_PREFIX}{browser_kind}-",
            dir=temp_root,
        )
    ).resolve()
    (profile_path / TEMP_PROFILE_MARKER).write_text(
        "Temporary Humble browser authentication profile.\n",
        encoding="utf-8",
    )
    return profile_path


def _remove_temporary_browser_profile(profile_path: Path) -> None:
    resolved_path = profile_path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    marker = resolved_path / TEMP_PROFILE_MARKER
    if (
        resolved_path.parent != temp_root
        or not resolved_path.name.startswith(TEMP_PROFILE_PREFIX)
        or not marker.is_file()
    ):
        raise OSError(f"Refusing to remove unverified browser profile: {resolved_path}")

    for attempt in range(12):
        try:
            shutil.rmtree(resolved_path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 11:
                raise
            time.sleep(0.25)


def _profile_in_use(profile_path: Path) -> bool:
    # Firefox's launcher can exit, and its profile lock may allow an open probe.
    # Restart Manager identifies the process that actually owns the profile.
    try:
        if profile_processes(profile_path):
            return True
    except OSError:
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    for name in ("parent.lock", "lockfile", "SingletonLock", "Default/LOCK"):
        handle = create(str(profile_path / name), 0, 0, None, 3, 128, None)
        if handle == wintypes.HANDLE(-1).value:
            if ctypes.get_last_error() not in {2, 3}:
                return True
        else:
            close(handle)
    return False


def _clean_stale_profiles():
    root = Path(tempfile.gettempdir()).resolve()
    for profile in root.glob(TEMP_PROFILE_PREFIX + "*"):
        if profile.is_symlink() or not profile.is_dir():
            continue
        if not (profile / TEMP_PROFILE_MARKER).is_file():
            continue
        # A newly launched browser may not have opened its profile lock yet.
        if _profile_in_use(profile):
            raise OSError("A Humble login window is already open. Close it before starting another login.")
        if time.time() - profile.stat().st_mtime < 120:
            raise OSError("A previous Humble login is still closing. Try again shortly.")
        _remove_temporary_browser_profile(profile)


@dataclass(frozen=True)
class BrowserInfo:
    executable: Path
    kind: str
    display_name: str


def _browser_kind(executable: Path) -> Optional[str]:
    name = executable.name.casefold()
    path_text = str(executable).casefold()
    if name == "msedge.exe":
        return "edge"
    if name in {"chrome.exe", "chromium.exe", "brave.exe", "thorium.exe", "arc.exe", "browser.exe"}:
        return "chrome"
    if name in {"firefox.exe", "waterfox.exe", "librewolf.exe", "floorp.exe", "zen.exe"}:
        return "firefox"
    if name == "vivaldi.exe":
        return "vivaldi"
    if name == "opera.exe" or (name == "launcher.exe" and "opera" in path_text):
        return "opera"
    return None


def _browser_display_name(kind: str) -> str:
    return {
        "edge": "Microsoft Edge",
        "chrome": "Google Chrome",
        "firefox": "Mozilla Firefox",
        "opera": "Opera",
        "vivaldi": "Vivaldi",
    }[kind]


def _executable_from_command(command: object) -> Optional[Path]:
    if not isinstance(command, str) or not command.strip():
        return None
    match = re.match(r'^\s*"([^"]+\.exe)"|^\s*([^\s]+\.exe)', command, re.IGNORECASE)
    if match is None:
        return None
    return Path(os.path.expandvars(match.group(1) or match.group(2)))


def _default_browser_executable() -> tuple[Optional[Path], Optional[str]]:
    user_choice = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_choice) as key:
            prog_id = str(winreg.QueryValueEx(key, "ProgId")[0])
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            rf"{prog_id}\shell\open\command",
        ) as key:
            command = winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None, None
    return _executable_from_command(command), prog_id


def _find_browser() -> BrowserInfo:
    executable, prog_id = _default_browser_executable()
    if executable is None or not executable.is_file():
        raise FileNotFoundError("The Windows default browser could not be located.")
    kind = _browser_kind(executable)
    if kind is None:
        raise FileNotFoundError("The selected default browser does not provide a supported session handoff.")
    return BrowserInfo(executable, kind, _browser_display_name(kind))


class ExternalBrowserBridge:
    def __init__(self):
        self.profile_path = None
        self.browser_name = None
        self.browser_kind = None
        self._debug_port = None
        self.state = "idle"
        self.error_message = None
        self.result = None
        self._process = None
        self._monitor_task = None
        self._stop_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()

    async def start(self):
        async with self._start_lock:
            await self._start()

    async def _start(self):
        if self.state in {"waiting", "ready"}:
            return
        await self.stop(close_browser=True)
        if self.profile_path is not None:
            raise OSError("The previous Humble login profile could not be removed. Close its browser window and try again.")
        await asyncio.to_thread(_clean_stale_profiles)
        browser = _find_browser()
        self.profile_path = _create_temporary_browser_profile(browser.kind)
        self.browser_name = browser.display_name
        self.browser_kind = browser.kind
        if browser.kind == "firefox":
            # Session-only cookies reach disk through Firefox's session backup.
            # Keep this dedicated login profile responsive to a completed sign-in.
            (self.profile_path / "user.js").write_text(
                'user_pref("browser.sessionstore.interval", 1000);\n', encoding="utf-8"
            )
            arguments = [str(browser.executable), "-no-remote", "-profile", str(self.profile_path), "-new-window", LOGIN_URL]
        else:
            arguments = [str(browser.executable), "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                "--user-data-dir=" + str(self.profile_path), "--no-first-run",
                "--no-default-browser-check", "--disable-background-mode", "--new-window", LOGIN_URL]
        try:
            self._process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except OSError:
            await asyncio.to_thread(_remove_temporary_browser_profile, self.profile_path)
            self.profile_path = None
            raise
        self.state = "waiting"
        self.error_message = None
        self.result = None
        self._monitor_task = asyncio.create_task(self._monitor())
        logger.info("Opened Humble login in the default browser: %s", self.browser_name)

    def _read_debug_port(self):
        if self._debug_port is not None:
            return True
        if self.profile_path is None:
            return False
        path = self.profile_path / "DevToolsActivePort"
        try:
            if path.is_symlink() or path.stat().st_size > 1024:
                return False
            port = int(path.read_text(encoding="utf-8").splitlines()[0])
            if not 1 <= port <= 65535:
                return False
            self._debug_port = port
            return True
        except (OSError, ValueError, IndexError):
            return False

    async def _chromium_cookies(self):
        if not self._read_debug_port():
            return []
        base = "http://127.0.0.1:" + str(self._debug_port)
        timeout = aiohttp.ClientTimeout(total=3)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(base + "/json/list") as response:
                    targets = await response.json()
                for target in targets:
                    url = yarl.URL(str(target.get("url", "")))
                    if target.get("type") != "page" or url.scheme != "https" or url.host not in {"www.humblebundle.com", "auth.humblebundle.com"}:
                        continue
                    endpoint = yarl.URL(target.get("webSocketDebuggerUrl", ""))
                    if endpoint.host != "127.0.0.1" or endpoint.port != self._debug_port:
                        continue
                    async with session.ws_connect(endpoint) as socket:
                        await socket.send_json({"id": 1, "method": "Network.getCookies", "params": {"urls": [SITE + "/", AUTH + "/", LIBRARY]}})
                        for _ in range(50):
                            message = await socket.receive(timeout=3)
                            if message.type != aiohttp.WSMsgType.TEXT:
                                break
                            data = json.loads(message.data)
                            if data.get("id") == 1:
                                cookies = data.get("result", {}).get("cookies", [])
                                return [cookie for cookie in cookies if is_session_cookie(cookie.get("name"))
                                        and str(cookie.get("domain", "")).lstrip('.') in {"humblebundle.com", "www.humblebundle.com", "auth.humblebundle.com"}]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
            pass
        return []

    async def _close_chromium(self):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get("http://127.0.0.1:" + str(self._debug_port) + "/json/version") as response:
                    data = await response.json()
                endpoint = yarl.URL(data.get("webSocketDebuggerUrl", ""))
                if endpoint.host != "127.0.0.1" or endpoint.port != self._debug_port:
                    return
                async with session.ws_connect(endpoint) as socket:
                    await socket.send_json({"id": 1, "method": "Browser.close"})
                    await asyncio.sleep(0.3)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            pass

    def _read_session_cookies(self):
        if self.profile_path is None:
            return []
        profile = self.profile_path.resolve()
        # Only the profile created for this login may supply integration credentials.
        if (profile.parent != Path(tempfile.gettempdir()).resolve()
                or not profile.name.startswith(TEMP_PROFILE_PREFIX)
                or not (profile / TEMP_PROFILE_MARKER).is_file()):
            raise ValueError("Unrecognized Humble login profile")
        database = profile / "cookies.sqlite"
        query = """SELECT name, value, host, path, isSecure, isHttpOnly, expiry
                   FROM moz_cookies
                   WHERE host IN ('.humblebundle.com', 'humblebundle.com',
                       'auth.humblebundle.com', '.auth.humblebundle.com',
                       'www.humblebundle.com', '.www.humblebundle.com')
                     AND (name IN ('ory_kratos_session', '__Host-ory_kratos_session', '__Secure-ory_kratos_session')
                          OR substr(name, 1, 12) = 'ory_session_'
                          OR substr(name, 1, 19) = '__Host-ory_session_'
                          OR substr(name, 1, 21) = '__Secure-ory_session_')
                     AND originAttributes = ''"""
        rows = []
        try:
            if database.is_file() and not database.is_symlink():
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2)) as connection:
                    rows = connection.execute(query).fetchall()
        except sqlite3.Error:
            pass
        selected = {}

        def keep(name, value, host, path, secure, http_only, expiry):
            if not is_session_cookie(name) or not value or not secure:
                return
            if str(host).lstrip('.') not in {"humblebundle.com", "www.humblebundle.com", "auth.humblebundle.com"}:
                return
            if not isinstance(expiry, (int, float)):
                return
            if expiry > 100_000_000_000:
                expiry /= 1000
            if expiry > 0 and expiry <= time.time():
                return
            selected[(name, host, path)] = {"name": name, "value": value, "domain": host,
                "path": path, "secure": True, "httpOnly": bool(http_only), "expires": expiry}

        for row in rows:
            keep(*row)
        for cookie in session_cookies(profile):
            attrs = cookie.get("originAttributes")
            if attrs and (not isinstance(attrs, dict) or any(value not in (0, False, "") for value in attrs.values())):
                continue
            keep(cookie.get("name"), cookie.get("value"), cookie.get("host"), cookie.get("path", "/"),
                 cookie.get("secure", False), cookie.get("httponly", False), cookie.get("expiry", -1))
        return list(selected.values())

    async def _monitor(self):
        try:
            async with RelaunchClientContext() as client:
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    if self.browser_kind == "firefox":
                        cookies = await asyncio.to_thread(self._read_session_cookies)
                    else:
                        cookies = await self._chromium_cookies()
                    if cookies:
                        client.load_cookies(cookies)
                        try:
                            identity = await client.identity_data()
                        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, AuthenticationRequired, BackendError, BackendNotAvailable, BackendTimeout, AccessDenied, NetworkError):
                            await asyncio.sleep(1)
                            continue
                        user_id = identity.get("id")
                        if isinstance(user_id, str) and user_id:
                            self.result = BrowserAuthResult(cookies, user_id, "Humble User")
                            await self.stop(close_browser=True)
                            if self.profile_path is not None:
                                raise OSError("The temporary Humble login profile could not be removed")
                            self.state = "ready"
                            logger.info("Default-browser Humble session validated and temporary profile removed")
                            return
                    await asyncio.sleep(0.5)
            raise TimeoutError("The Humble login was not completed. Close the login window and try again.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Humble browser login stopped (%s)", type(error).__name__)
            self.error_message = str(error) if isinstance(error, TimeoutError) else "Could not verify the Humble login. Close the login window and try again."
            self.state = "error"

    async def stop(self, *, close_browser):
        async with self._stop_lock:
            task, self._monitor_task = self._monitor_task, None
            if task is not None and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            process, self._process = self._process, None
            if close_browser and self._debug_port is not None:
                await self._close_chromium()
                self._debug_port = None
            if close_browser and self.profile_path is not None and self.browser_kind == "firefox":
                try:
                    await asyncio.to_thread(close_profile, self.profile_path)
                except OSError:
                    logger.warning("Could not close the Firefox window for the temporary Humble profile")
            if close_browser and process is not None and process.poll() is None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, 3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, 2)
            if self.profile_path is not None:
                if await asyncio.to_thread(_profile_in_use, self.profile_path):
                    logger.warning("The temporary Humble login profile is still in use")
                    return
                try:
                    await asyncio.to_thread(_remove_temporary_browser_profile, self.profile_path)
                except OSError:
                    logger.warning("Could not remove the temporary Humble login profile")
                else:
                    self.profile_path = None


class RelaunchClientContext:
    async def __aenter__(self):
        self.client = RelaunchClient()
        return self.client

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.close()


def galaxy_confirmation_visible():
    """Detect the parent Galaxy process's visible Humble connection prompt."""
    parent_pid = os.getppid()
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.IsWindowVisible.argtypes, user.IsWindowVisible.restype = [wintypes.HWND], wintypes.BOOL
    user.GetWindowTextLengthW.argtypes, user.GetWindowTextLengthW.restype = [wintypes.HWND], ctypes.c_int
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    found = False
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def inspect(window, context):
        nonlocal found
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value != parent_pid or not user.IsWindowVisible(window):
            return True
        title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(window) + 1)
        user.GetWindowTextW(window, title, len(title))
        normalized = title.value.casefold().replace(" ", "")
        if "humblebundle" in normalized and normalized != "logintohumblebundle":
            found = True
            return False
        return True

    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, wintypes.LPARAM], wintypes.BOOL
    user.EnumWindows(inspect, 0)
    return found


class LocalBrowserAuthServer:
    def __init__(
        self,
        bridge: Optional[ExternalBrowserBridge] = None,
    ):
        self.bridge = bridge or ExternalBrowserBridge()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._nonce: Optional[str] = None
        self.port: Optional[int] = None
        self._stop_lock = asyncio.Lock()

    async def start(self) -> int:
        if self._runner is not None and self.port is not None:
            return self.port

        self.bridge.state = "idle"
        self.bridge.error_message = None
        self.bridge.result = None
        self._nonce = secrets.token_urlsafe(32)
        app = web.Application(client_max_size=8192)
        app.router.add_get(FORM_PATH, self._handle_form)
        app.router.add_post(OPEN_PATH, self._handle_open)
        app.router.add_get(STATUS_PATH, self._handle_status)
        app.router.add_get(COMPLETE_PATH, self._handle_complete)

        self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=2)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = self._site._server.sockets if self._site._server else []
        if len(sockets) != 1:
            await self.stop()
            raise OSError("Local Humble auth server did not bind exactly one socket")
        address = sockets[0].getsockname()
        if address[0] != "127.0.0.1":
            await self.stop()
            raise OSError("Local Humble auth server did not bind to IPv4 loopback")
        self.port = int(address[1])
        logger.info("Local Humble auth server listening on IPv4 loopback port %s", self.port)
        return self.port

    async def stop(self) -> None:
        async with self._stop_lock:
            runner = self._runner
            site = self._site
            self._runner = None
            self._site = None
            self._nonce = None
            self.port = None

            if site is not None:
                try:
                    await asyncio.wait_for(site.stop(), timeout=2)
                except asyncio.TimeoutError:
                    logger.warning("Timed out while closing the local Humble auth listener")

            if runner is not None:
                try:
                    await asyncio.wait_for(runner.cleanup(), timeout=4)
                except asyncio.TimeoutError:
                    logger.warning("Timed out while closing the local Humble auth server")

            try:
                await asyncio.wait_for(
                    self.bridge.stop(close_browser=True),
                    timeout=15,
                )
            except asyncio.TimeoutError:
                logger.warning("Timed out while stopping the Humble browser bridge")

    @property
    def result(self) -> Optional[BrowserAuthResult]:
        return self.bridge.result

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise RuntimeError("Local Humble auth server is not running")
        return f"http://127.0.0.1:{self.port}/"

    @property
    def complete_url(self) -> str:
        if self.port is None:
            raise RuntimeError("Local Humble auth server is not running")
        return f"http://127.0.0.1:{self.port}{COMPLETE_PATH}"

    @property
    def end_uri_regex(self) -> str:
        return "^" + re.escape(self.complete_url) + "$"

    def _is_loopback_request(self, request: web.Request) -> bool:
        origin = request.headers.get("Origin")
        return (request.remote == "127.0.0.1"
                and request.host == f"127.0.0.1:{self.port}"
                and (origin is None or origin == self.base_url.rstrip("/")))

    @staticmethod
    def _response_headers() -> dict[str, str]:
        return {
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'"
            ),
        }

    def _valid_nonce(self, request: web.Request) -> bool:
        submitted_nonce = request.query.get("nonce")
        return bool(
            submitted_nonce
            and self._nonce
            and secrets.compare_digest(submitted_nonce, self._nonce)
        )

    async def _handle_form(self, request: web.Request):
        if not self._is_loopback_request(request):
            raise web.HTTPForbidden()
        page = _FORM_HTML.replace("__NONCE__", json.dumps(self._nonce or ""))
        return web.Response(
            text=page,
            content_type="text/html",
            headers=self._response_headers(),
        )

    async def _handle_open(self, request: web.Request):
        if not self._is_loopback_request(request) or not self._valid_nonce(request):
            raise web.HTTPForbidden()
        try:
            await self.bridge.start()
        except (FileNotFoundError, OSError) as error:
            logger.warning("Could not start external Humble browser: %s", error)
            self.bridge.state = "error"
            self.bridge.error_message = str(error)
            return web.json_response(
                {"state": "error", "message": str(error)},
                status=500,
                headers=self._response_headers(),
            )
        return web.json_response(
            {
                "state": self.bridge.state,
                "browser": self.bridge.browser_name,
            },
            headers=self._response_headers(),
        )

    async def _handle_status(self, request: web.Request):
        if not self._is_loopback_request(request) or not self._valid_nonce(request):
            raise web.HTTPForbidden()
        return web.json_response(
            {
                "state": self.bridge.state,
                "message": self.bridge.error_message,
                "browser": self.bridge.browser_name,
            },
            headers=self._response_headers(),
        )

    async def _handle_complete(self, request: web.Request):
        if not self._is_loopback_request(request):
            raise web.HTTPForbidden()
        if self.bridge.state != "ready" or self.bridge.result is None:
            raise web.HTTPConflict(text="Humble login has not been verified")
        return web.Response(
            text=_COMPLETE_HTML,
            content_type="text/html",
            headers=self._response_headers(),
        )


class WebpackParseError(UnknownBackendResponse):
    pass


class AuthorizedHumbleAPI:
    def __init__(self, headers, credentials_callback=None):
        self._modern = RelaunchClient(headers=headers, credentials_callback=credentials_callback)

    @property
    def modern(self):
        return self._modern

    @property
    def is_authenticated(self):
        return self._modern.authenticated

    async def authenticate(self, credentials):
        return await self._modern.authenticate(credentials)

    async def get_library_orders(self, previous):
        return await library_orders(self._modern, previous)

    async def close_session(self):
        await self._modern.close()
