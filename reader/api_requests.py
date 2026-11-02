"""Explicit HTTP requests from Swagger, independent of the offline web renderer."""

from __future__ import annotations

import base64
import binascii
import json
import re

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_MS = 30_000
METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"})
MANAGED_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "proxy-authorization",
        "proxy-connection",
        "upgrade",
    }
)


def parse_request(raw: str):
    if len(raw) > MAX_BYTES * 4 // 3 + 100_000:
        raise ValueError("Request exceeds the 10 MB limit.")
    try:
        data = json.loads(raw)
        url = QUrl(data["url"], QUrl.ParsingMode.StrictMode)
        method = data["method"].upper()
        headers = data.get("headers", {})
        body = base64.b64decode(data.get("body", ""), validate=True)
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error) as error:
        raise ValueError("Invalid HTTP request.") from error
    if (
        not url.isValid()
        or url.scheme() not in {"http", "https"}
        or not url.host()
        or url.userInfo()
        or url.hasFragment()
    ):
        raise ValueError(
            "Use an absolute HTTP or HTTPS server URL without embedded credentials or a fragment."
        )
    if len(url.toEncoded()) > 32768 or method not in METHODS:
        raise ValueError("Unsupported request URL or HTTP method.")
    if len(body) > MAX_BYTES:
        raise ValueError("Request exceeds the 10 MB limit.")
    if body and method in {"GET", "HEAD"}:
        raise ValueError("GET and HEAD requests cannot have a body.")
    if not isinstance(headers, dict) or len(headers) > 100:
        raise ValueError("Invalid request headers.")
    encoded_headers = []
    for name, value in headers.items():
        if not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise ValueError("Invalid header name.")
        if not isinstance(value, str) or any(
            ord(char) < 32 and char != "\t" or ord(char) == 127 for char in value
        ):
            raise ValueError("Invalid header value.")
        try:
            pair = (name.encode("ascii"), value.encode("latin-1"))
        except UnicodeError as error:
            raise ValueError("HTTP header values must use Latin-1 characters.") from error
        if name.lower() not in MANAGED_HEADERS:
            encoded_headers.append(pair)
    if sum(len(key) + len(value) for key, value in encoded_headers) > 65536:
        raise ValueError("Request headers exceed the 64 KB limit.")
    return url, method, encoded_headers, body


class ApiRequests(QObject):
    finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.pending = {}

    def fail(self, document_id, request_id, message):
        self.finished.emit(
            json.dumps({"documentId": document_id, "id": request_id, "error": message})
        )

    def send(self, document_id, request_id, raw):
        key = (document_id, request_id)
        if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", request_id) or key in self.pending:
            return
        try:
            if len(self.pending) >= 8:
                raise ValueError(
                    "Too many active requests. Wait for a response or cancel requests."
                )
            url, method, headers, body = parse_request(raw)
        except ValueError as error:
            self.fail(document_id, request_id, str(error))
            return
        request = QNetworkRequest(url)
        request.setTransferTimeout(TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy.value,
        )
        for attribute in (
            QNetworkRequest.Attribute.CookieLoadControlAttribute,
            QNetworkRequest.Attribute.CookieSaveControlAttribute,
            QNetworkRequest.Attribute.AuthenticationReuseAttribute,
        ):
            request.setAttribute(attribute, QNetworkRequest.LoadControl.Manual.value)
        for name, value in headers:
            request.setRawHeader(QByteArray(name), QByteArray(value))
        reply = self.manager.sendCustomRequest(
            request, QByteArray(method.encode("ascii")), QByteArray(body)
        )
        reply.setReadBufferSize(64 * 1024)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        entry = {"reply": reply, "timer": timer, "body": bytearray(), "error": ""}
        self.pending[key] = entry
        reply.readyRead.connect(lambda: self._read(key))
        reply.finished.connect(lambda: self._finished(key))
        timer.timeout.connect(lambda: self._abort(key, "Request timed out after 30 seconds."))
        timer.start(TIMEOUT_MS)

    def _read(self, key):
        entry = self.pending.get(key)
        if not entry or entry["error"]:
            return
        available = min(entry["reply"].bytesAvailable(), MAX_BYTES + 1 - len(entry["body"]))
        if available > 0:
            entry["body"].extend(bytes(entry["reply"].read(available)))
        if len(entry["body"]) > MAX_BYTES:
            self._abort(key, "Response exceeds the 10 MB limit.")

    def _abort(self, key, message):
        entry = self.pending.get(key)
        if entry:
            entry["error"] = message
            entry["reply"].abort()

    def cancel(self, document_id=None):
        for key in list(self.pending):
            if document_id is None or key[0] == document_id:
                self._abort(key, "Request cancelled. The server may already have received it.")

    def _finished(self, key):
        entry = self.pending.get(key)
        if not entry:
            return
        self._read(key)
        entry = self.pending.pop(key, None)
        if not entry:
            return
        reply = entry["reply"]
        entry["timer"].stop()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = entry["error"]
        if not error and (
            not status or (reply.error() != QNetworkReply.NetworkError.NoError and status < 400)
        ):
            error = reply.errorString()
        result = {"documentId": key[0], "id": key[1]}
        if error:
            result["error"] = error
        else:
            reason = reply.attribute(QNetworkRequest.Attribute.HttpReasonPhraseAttribute)
            result.update(
                status=status,
                statusText=bytes(reason).decode("latin-1")
                if isinstance(reason, QByteArray)
                else str(reason or ""),
                headers=[
                    [bytes(name).decode("latin-1"), bytes(value).decode("latin-1")]
                    for name, value in reply.rawHeaderPairs()
                ],
                body=base64.b64encode(entry["body"]).decode("ascii"),
            )
        self.finished.emit(json.dumps(result))
        reply.deleteLater()
