"""Persistent document library and annotations, stored separately from sources."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


def clean_anchor(value):
    if not isinstance(value, dict):
        raise ValueError("Choose a place in the document first.")
    index, progress = value.get("index"), value.get("progress")
    if type(index) is not int or not 0 <= index <= 1_000_000:
        raise ValueError("Invalid annotation position.")
    if type(progress) not in (float, int) or not math.isfinite(progress) or not 0 <= progress <= 1:
        raise ValueError("Invalid reading progress.")
    limits = {
        "tag": 32,
        "hash": 16,
        "text": 320,
        "tail": 100,
        "before": 160,
        "after": 160,
        "heading": 300,
        "quote": 500,
        "fingerprint": 64,
    }
    result = {"index": index, "progress": progress}
    for key, limit in limits.items():
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > limit or "\x00" in text:
            raise ValueError("Invalid annotation text.")
        result[key] = text
    offset = value.get("quoteOffset", 0)
    if type(offset) is not int or not 0 <= offset <= 5_000_000:
        raise ValueError("Invalid text selection.")
    result["quoteOffset"] = offset
    return result


class ReadingLibrary:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=3)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY, name TEXT NOT NULL, format TEXT NOT NULL,
                    starred INTEGER NOT NULL DEFAULT 0, opened_at INTEGER NOT NULL,
                    resume_id TEXT
                );
                CREATE TABLE IF NOT EXISTS annotations (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
                    kind TEXT NOT NULL, label TEXT NOT NULL, body TEXT NOT NULL,
                    anchor TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS annotation_paths ON annotations(path);
                CREATE TABLE IF NOT EXISTS workspace (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, sort_order INTEGER NOT NULL,
                    files_collapsed INTEGER NOT NULL DEFAULT 0,
                    library_collapsed INTEGER NOT NULL DEFAULT 0
                );
            """)
            columns = {
                row["name"] for row in self.connection.execute("PRAGMA table_info(documents)")
            }
            if "pinned" not in columns:
                self.connection.execute(
                    "ALTER TABLE documents ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
                )
            if "category_id" not in columns:
                self.connection.execute(
                    "ALTER TABLE documents ADD COLUMN category_id TEXT "
                    "REFERENCES categories(id) ON DELETE SET NULL"
                )
            if "sort_order" not in columns:
                self.connection.execute(
                    "ALTER TABLE documents ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
                )
                paths = self.connection.execute(
                    "SELECT path FROM documents ORDER BY opened_at DESC,path"
                ).fetchall()
                self.connection.executemany(
                    "UPDATE documents SET sort_order=? WHERE path=?",
                    [(index, row["path"]) for index, row in enumerate(paths)],
                )

    def remember(self, path, document_format, inherit_from=None):
        path = str(Path(path).resolve())
        with self.connection:
            existing = self.connection.execute(
                "SELECT 1 FROM documents WHERE path=?", (path,)
            ).fetchone()
            self.connection.execute(
                """INSERT INTO documents(path,name,format,opened_at) VALUES(?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET name=excluded.name,format=excluded.format,opened_at=excluded.opened_at""",
                (path, Path(path).name, document_format, time.time_ns()),
            )
            if not existing:
                self.connection.execute(
                    "UPDATE documents SET sort_order=(SELECT MAX(sort_order)+1 FROM documents) "
                    "WHERE path=?",
                    (path,),
                )
            if not existing and inherit_from and inherit_from != path:
                previous = self.get(inherit_from)
                if previous:
                    resume_id = None
                    for annotation in previous["annotations"]:
                        new_id = str(uuid4())
                        self.connection.execute(
                            "INSERT INTO annotations VALUES(?,?,?,?,?,?,?)",
                            (
                                new_id,
                                path,
                                annotation["kind"],
                                annotation["label"],
                                annotation["body"],
                                json.dumps(annotation["anchor"], ensure_ascii=False),
                                annotation["createdAt"],
                            ),
                        )
                        if annotation["id"] == previous["resumeId"]:
                            resume_id = new_id
                    self.connection.execute(
                        "UPDATE documents SET starred=?,resume_id=?,category_id=? WHERE path=?",
                        (previous["starred"], resume_id, previous["categoryId"] or None, path),
                    )

    def entries(self):
        documents = [self._document_record(row) for row in self._ordered_documents()]
        by_path = {record["path"]: record for record in documents}
        for row in self.connection.execute("SELECT * FROM annotations ORDER BY created_at,id"):
            by_path[row["path"]]["annotations"].append(self._annotation_record(row))
        return documents

    def _ordered_documents(self):
        return self.connection.execute(
            "SELECT d.* FROM documents d LEFT JOIN categories c ON c.id=d.category_id "
            "ORDER BY c.id IS NULL,c.sort_order,c.id,d.pinned DESC,d.sort_order,d.path"
        )

    def get(self, path):
        """Look up one document without loading the rest of the reading library."""
        row = self.connection.execute("SELECT * FROM documents WHERE path=?", (path,)).fetchone()
        if row is None:
            return None
        document = self._document_record(row)
        document["annotations"] = [
            self._annotation_record(annotation)
            for annotation in self.connection.execute(
                "SELECT * FROM annotations WHERE path=? ORDER BY created_at,id", (path,)
            )
        ]
        return document

    @staticmethod
    def _document_record(row):
        record = dict(row)
        record["starred"] = bool(record["starred"])
        record["pinned"] = bool(record["pinned"])
        record["order"] = record.pop("sort_order")
        record["categoryId"] = record.pop("category_id") or ""
        record["resumeId"] = record.pop("resume_id")
        record.pop("opened_at")
        record["annotations"] = []
        return record

    @staticmethod
    def _annotation_record(row):
        item = dict(row)
        item.pop("path")
        item["anchor"] = json.loads(item["anchor"])
        item["createdAt"] = item.pop("created_at")
        return item

    def set_starred(self, path, starred):
        with self.connection:
            self.connection.execute(
                "UPDATE documents SET starred=? WHERE path=?", (bool(starred), path)
            )

    def set_pinned(self, path, pinned):
        with self.connection:
            self.connection.execute(
                "UPDATE documents SET pinned=? WHERE path=?", (bool(pinned), path)
            )

    def move_relative(self, path, neighbor, before):
        """Reorder within a pin group, retaining items hidden by the current UI filter."""
        with self.connection:
            rows = self._ordered_documents().fetchall()
            pins = {row["path"]: row["pinned"] for row in rows}
            categories = {row["path"]: row["category_id"] for row in rows}
            if path == neighbor or path not in pins or neighbor not in pins:
                return
            if pins[path] != pins[neighbor]:
                raise ValueError("Pinned files stay above unpinned files.")
            if categories[path] != categories[neighbor]:
                raise ValueError("Move the file to that category first.")
            paths = [row["path"] for row in rows if row["path"] != path]
            paths.insert(paths.index(neighbor) + (0 if before else 1), path)
            self.connection.executemany(
                "UPDATE documents SET sort_order=? WHERE path=?", enumerate(paths)
            )

    def categories(self):
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "order": row["sort_order"],
                "filesCollapsed": bool(row["files_collapsed"]),
                "libraryCollapsed": bool(row["library_collapsed"]),
            }
            for row in self.connection.execute("SELECT * FROM categories ORDER BY sort_order,id")
        ]

    def _category_name(self, name, identifier=None):
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 80
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("Enter a category name of 1–80 characters.")
        name = name.strip()
        if any(
            c["id"] != identifier and c["name"].casefold() == name.casefold()
            for c in self.categories()
        ):
            raise ValueError("A category with that name already exists.")
        return name

    def _require_category(self, identifier):
        if (
            identifier
            and not self.connection.execute(
                "SELECT 1 FROM categories WHERE id=?", (identifier,)
            ).fetchone()
        ):
            raise ValueError("This category no longer exists.")

    def _require_paths(self, paths):
        if any(
            not self.connection.execute("SELECT 1 FROM documents WHERE path=?", (path,)).fetchone()
            for path in paths
        ):
            raise ValueError("Save all selected documents before organizing them.")

    def create_category(self, name, paths=()):
        with self.connection:
            name = self._category_name(name)
            self._require_paths(paths)
            identifier = str(uuid4())
            self.connection.execute(
                "INSERT INTO categories(id,name,sort_order) VALUES(?,?,(SELECT COALESCE(MAX(sort_order),-1)+1 FROM categories))",
                (identifier, name),
            )
            self._assign_category(paths, identifier)
        return identifier

    def rename_category(self, identifier, name):
        with self.connection:
            self._require_category(identifier)
            name = self._category_name(name, identifier)
            self.connection.execute("UPDATE categories SET name=? WHERE id=?", (name, identifier))

    def delete_category(self, identifier):
        with self.connection:
            self.connection.execute("DELETE FROM categories WHERE id=?", (identifier,))

    def move_category(self, identifier, neighbor, before):
        with self.connection:
            self._require_category(identifier)
            self._require_category(neighbor)
            if identifier == neighbor:
                return
            ids = [c["id"] for c in self.categories() if c["id"] != identifier]
            if neighbor not in ids:
                raise ValueError("Choose a category to reorder.")
            ids.insert(ids.index(neighbor) + (0 if before else 1), identifier)
            self.connection.executemany(
                "UPDATE categories SET sort_order=? WHERE id=?", enumerate(ids)
            )

    def collapse_category(self, identifier, scope, collapsed):
        if scope not in {"files", "library"}:
            raise ValueError("Unknown category list.")
        with self.connection:
            self.connection.execute(
                f"UPDATE categories SET {scope}_collapsed=? WHERE id=?",
                (bool(collapsed), identifier),
            )

    def _assign_category(self, paths, identifier):
        position = self.connection.execute(
            "SELECT COALESCE(MAX(sort_order),-1)+1 FROM documents"
        ).fetchone()[0]
        for path in dict.fromkeys(paths):
            self.connection.execute(
                "UPDATE documents SET category_id=?,sort_order=? WHERE path=? AND category_id IS NOT ?",
                (identifier or None, position, path, identifier or None),
            )
            position += 1

    def assign_category(self, paths, identifier):
        with self.connection:
            self._require_category(identifier)
            self._require_paths(paths)
            self._assign_category(paths, identifier)

    def set_files_flag(self, paths, flag, value):
        if flag not in {"starred", "pinned"}:
            raise ValueError("Unknown file action.")
        with self.connection:
            self._require_paths(paths)
            self.connection.executemany(
                f"UPDATE documents SET {flag}=? WHERE path=?",
                [(bool(value), path) for path in paths],
            )

    def rename_document(self, old_path, new_path, rename_file):
        """Move metadata and the source together; preserve annotation IDs and category."""
        with self.connection:
            self._require_paths([old_path])
            if self.connection.execute(
                "SELECT 1 FROM documents WHERE path=?", (new_path,)
            ).fetchone():
                raise ValueError("That name already belongs to a document in the library.")
            self.connection.execute(
                "INSERT INTO documents(path,name,format,starred,opened_at,resume_id,pinned,sort_order,category_id) "
                "SELECT ?,?,format,starred,opened_at,resume_id,pinned,sort_order,category_id FROM documents WHERE path=?",
                (new_path, Path(new_path).name, old_path),
            )
            self.connection.execute(
                "UPDATE annotations SET path=? WHERE path=?", (new_path, old_path)
            )
            self.connection.execute("DELETE FROM documents WHERE path=?", (old_path,))
            workspace = self.workspace()
            workspace["paths"] = [new_path if p == old_path else p for p in workspace["paths"]]
            if workspace["active"] == old_path:
                workspace["active"] = new_path
            self.connection.execute(
                "INSERT OR REPLACE INTO workspace VALUES('session',?)", (json.dumps(workspace),)
            )
            rename_file()

    def save_annotation(self, path, identifier, kind, label, body, anchor):
        if (
            kind not in ("mark", "note")
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 160
        ):
            raise ValueError("Enter a name of 1–160 characters.")
        if not isinstance(body, str) or len(body) > 10000 or "\x00" in body:
            raise ValueError("Notes can contain up to 10,000 characters.")
        if kind == "note" and not body.strip():
            raise ValueError("Write a note before saving it.")
        clean = clean_anchor(anchor)
        if not self.connection.execute("SELECT 1 FROM documents WHERE path=?", (path,)).fetchone():
            raise ValueError("Save the document before adding annotations.")
        with self.connection:
            if identifier:
                old = self.connection.execute(
                    "SELECT kind FROM annotations WHERE id=? AND path=?", (identifier, path)
                ).fetchone()
                if not old or old["kind"] != kind:
                    raise ValueError(
                        "This annotation no longer exists. Reopen the list and try again."
                    )
                self.connection.execute(
                    "UPDATE annotations SET label=?,body=? WHERE id=? AND path=?",
                    (label.strip(), body if kind == "note" else "", identifier, path),
                )
            else:
                identifier = str(uuid4())
                self.connection.execute(
                    "INSERT INTO annotations VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        path,
                        kind,
                        label.strip(),
                        body if kind == "note" else "",
                        json.dumps(clean, ensure_ascii=False),
                        time.time_ns(),
                    ),
                )
                self.connection.execute(
                    "UPDATE documents SET resume_id=? WHERE path=?", (identifier, path)
                )
        return identifier

    def resume(self, path, identifier):
        with self.connection:
            if self.connection.execute(
                "SELECT 1 FROM annotations WHERE path=? AND id=?", (path, identifier)
            ).fetchone():
                self.connection.execute(
                    "UPDATE documents SET resume_id=? WHERE path=?", (identifier, path)
                )

    def delete_annotation(self, path, identifier):
        with self.connection:
            self.connection.execute(
                "DELETE FROM annotations WHERE path=? AND id=?", (path, identifier)
            )
            replacement = self.connection.execute(
                "SELECT id FROM annotations WHERE path=? ORDER BY created_at DESC LIMIT 1", (path,)
            ).fetchone()
            self.connection.execute(
                "UPDATE documents SET resume_id=? WHERE path=? AND resume_id=?",
                (replacement["id"] if replacement else None, path, identifier),
            )

    def forget(self, path):
        with self.connection:
            self.connection.execute("DELETE FROM documents WHERE path=?", (path,))

    def save_workspace(self, paths, active):
        value = json.dumps({"paths": list(dict.fromkeys(paths)), "active": active})
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO workspace VALUES('session',?)", (value,)
            )

    def workspace(self):
        row = self.connection.execute("SELECT value FROM workspace WHERE key='session'").fetchone()
        if not row:
            return {"paths": [], "active": None}
        value = json.loads(row["value"])
        if not isinstance(value, dict) or not isinstance(value.get("paths"), list):
            raise ValueError("The saved reading session is invalid.")
        return {
            "paths": [path for path in value["paths"] if isinstance(path, str)],
            "active": value.get("active") if isinstance(value.get("active"), str) else None,
        }
