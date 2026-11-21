from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kurrentscholar.constants import PROJECT_SCHEMA_VERSION
from kurrentscholar.domain import BoundingBox, ReviewStatus


@dataclass(slots=True)
class StoredLine:
    id: int
    page_number: int
    reading_order: int
    bbox: BoundingBox
    machine_text: str
    corrected_text: str | None
    confidence: float | None
    token_probabilities: list[float]
    review_status: str
    notes: str
    truncated: bool
    recognition_error: str | None

    @property
    def display_text(self) -> str:
        return self.corrected_text if self.corrected_text is not None else self.machine_text


SCHEMA = """
CREATE TABLE IF NOT EXISTS project_info (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  source_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER NOT NULL CHECK (page_count > 0),
  managed_copy INTEGER NOT NULL DEFAULT 0 CHECK (managed_copy IN (0,1))
);
CREATE TABLE IF NOT EXISTS pages (
  page_number INTEGER PRIMARY KEY CHECK (page_number > 0),
  width INTEGER NOT NULL CHECK (width > 0),
  height INTEGER NOT NULL CHECK (height > 0),
  dpi INTEGER NOT NULL,
  rotation INTEGER NOT NULL DEFAULT 0,
  segmentation_status TEXT NOT NULL DEFAULT 'pending',
  segmentation_error TEXT,
  processed_at TEXT
);
CREATE TABLE IF NOT EXISTS lines (
  id INTEGER PRIMARY KEY,
  page_number INTEGER NOT NULL REFERENCES pages(page_number) ON DELETE CASCADE,
  reading_order INTEGER NOT NULL,
  x INTEGER NOT NULL, y INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
  machine_text TEXT NOT NULL DEFAULT '',
  corrected_text TEXT,
  confidence REAL,
  token_probabilities_json TEXT NOT NULL DEFAULT '[]',
  token_ids_json TEXT NOT NULL DEFAULT '[]',
  review_status TEXT NOT NULL DEFAULT 'unreviewed',
  notes TEXT NOT NULL DEFAULT '',
  truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0,1)),
  recognition_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(page_number, reading_order)
);
CREATE TABLE IF NOT EXISTS correction_history (
  id INTEGER PRIMARY KEY,
  line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
  previous_text TEXT,
  new_text TEXT NOT NULL,
  changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lines_page_order ON lines(page_number, reading_order);
CREATE INDEX IF NOT EXISTS idx_lines_review ON lines(review_status);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ProjectDatabase:
    def __init__(self, path: str | Path, create: bool = False, overwrite: bool = False) -> None:
        self.path = Path(path)
        if create and self.path.exists():
            if not overwrite:
                raise FileExistsError(f"Project already exists: {self.path}")
            self.path.unlink()
            for suffix in ("-wal", "-shm"):
                companion = Path(str(self.path) + suffix)
                if companion.is_file():
                    companion.unlink()
        if not create and not self.path.is_file():
            raise FileNotFoundError(f"Project does not exist: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        if create:
            self._create_schema()
        self._validate_version()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(SCHEMA)
            self.connection.execute(f"PRAGMA user_version={PROJECT_SCHEMA_VERSION}")
            self.connection.executemany(
                "INSERT OR IGNORE INTO project_info(key,value) VALUES (?,?)",
                (("created_at", utc_now()), ("schema_version", str(PROJECT_SCHEMA_VERSION))),
            )

    def _validate_version(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version != PROJECT_SCHEMA_VERSION:
            self.connection.close()
            raise ValueError(
                f"Unsupported project schema {version}; this version supports {PROJECT_SCHEMA_VERSION}"
            )

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup, including data still held in WAL."""

        target_path = Path(destination)
        if target_path.resolve() == self.path.resolve():
            raise ValueError("The backup path must differ from the project path")
        if target_path.exists():
            raise FileExistsError(f"Backup already exists: {target_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(target_path)
        try:
            self.connection.backup(target)
        finally:
            target.close()
        return target_path

    def __enter__(self) -> ProjectDatabase:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def document_hash(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def set_document(self, source_path: str | Path, page_count: int) -> None:
        source = Path(source_path).resolve()
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO documents(id,source_path,filename,sha256,page_count) VALUES(1,?,?,?,?)",
                (str(source), source.name, self.document_hash(source), page_count),
            )

    def document(self) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM documents WHERE id=1").fetchone()
        return dict(row) if row else None

    def relink_document(self, source_path: str | Path) -> None:
        """Point a moved project at the identical source document."""

        source = Path(source_path).resolve()
        current = self.document()
        if current is None:
            raise ValueError("The project has no source document record")
        if not source.is_file():
            raise FileNotFoundError(source)
        if self.document_hash(source) != current["sha256"]:
            raise ValueError(
                "The selected file does not match the source document checksum. "
                "Choose the original file so page coordinates remain valid."
            )
        with self.connection:
            self.connection.execute(
                "UPDATE documents SET source_path=?, filename=? WHERE id=1",
                (str(source), source.name),
            )

    def page(self, page_number: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM pages WHERE page_number=?", (page_number,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_page(
        self,
        page_number: int,
        width: int,
        height: int,
        dpi: int,
        rotation: int = 0,
        status: str = "segmented",
        error: str | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO pages(page_number,width,height,dpi,rotation,segmentation_status,segmentation_error,processed_at)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(page_number) DO UPDATE SET
                   width=excluded.width,height=excluded.height,dpi=excluded.dpi,rotation=excluded.rotation,
                   segmentation_status=excluded.segmentation_status,segmentation_error=excluded.segmentation_error,
                   processed_at=excluded.processed_at""",
                (page_number, width, height, dpi, rotation, status, error, utc_now()),
            )

    def add_line(
        self,
        page_number: int,
        reading_order: int,
        bbox: BoundingBox,
        machine_text: str,
        confidence: float | None,
        token_probabilities: list[float],
        token_ids: list[int],
        truncated: bool = False,
        recognition_error: str | None = None,
    ) -> int:
        now = utc_now()
        with self.connection:
            self.connection.execute(
                """INSERT INTO lines(page_number,reading_order,x,y,width,height,machine_text,confidence,
                   token_probabilities_json,token_ids_json,truncated,recognition_error,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(page_number,reading_order) DO UPDATE SET x=excluded.x,y=excluded.y,
                   width=excluded.width,height=excluded.height,machine_text=excluded.machine_text,
                   confidence=excluded.confidence,token_probabilities_json=excluded.token_probabilities_json,
                   token_ids_json=excluded.token_ids_json,truncated=excluded.truncated,
                   recognition_error=excluded.recognition_error,updated_at=excluded.updated_at
                   WHERE lines.machine_text='' AND lines.corrected_text IS NULL""",
                (
                    page_number,
                    reading_order,
                    bbox.x,
                    bbox.y,
                    bbox.width,
                    bbox.height,
                    machine_text,
                    confidence,
                    json.dumps(token_probabilities),
                    json.dumps(token_ids),
                    int(truncated),
                    recognition_error,
                    now,
                    now,
                ),
            )
            row = self.connection.execute(
                "SELECT id FROM lines WHERE page_number=? AND reading_order=?",
                (page_number, reading_order),
            ).fetchone()
            if row is None:
                raise RuntimeError("Line insert did not create or locate a line record")
            return int(row[0])

    def lines(self, page_number: int | None = None) -> list[StoredLine]:
        query = "SELECT * FROM lines"
        arguments: tuple[object, ...] = ()
        if page_number is not None:
            query += " WHERE page_number=?"
            arguments = (page_number,)
        query += " ORDER BY page_number,reading_order"
        return [self._stored_line(row) for row in self.connection.execute(query, arguments)]

    @staticmethod
    def _stored_line(row: sqlite3.Row) -> StoredLine:
        return StoredLine(
            id=row["id"],
            page_number=row["page_number"],
            reading_order=row["reading_order"],
            bbox=BoundingBox(row["x"], row["y"], row["width"], row["height"]),
            machine_text=row["machine_text"],
            corrected_text=row["corrected_text"],
            confidence=row["confidence"],
            token_probabilities=json.loads(row["token_probabilities_json"]),
            review_status=row["review_status"],
            notes=row["notes"],
            truncated=bool(row["truncated"]),
            recognition_error=row["recognition_error"],
        )

    def line(self, line_id: int) -> StoredLine:
        row = self.connection.execute("SELECT * FROM lines WHERE id=?", (line_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown line {line_id}")
        return self._stored_line(row)

    def correct_line(self, line_id: int, text: str) -> bool:
        row = self.connection.execute("SELECT corrected_text,machine_text FROM lines WHERE id=?", (line_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown line {line_id}")
        previous = row["corrected_text"] if row["corrected_text"] is not None else row["machine_text"]
        if text == previous:
            return False
        with self.connection:
            self.connection.execute(
                "UPDATE lines SET corrected_text=?,updated_at=? WHERE id=?", (text, utc_now(), line_id)
            )
            self.connection.execute(
                "INSERT INTO correction_history(line_id,previous_text,new_text,changed_at) VALUES(?,?,?,?)",
                (line_id, previous, text, utc_now()),
            )
        return True

    def set_review_status(self, line_id: int, status: ReviewStatus) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE lines SET review_status=?,updated_at=? WHERE id=?",
                (status.value, utc_now(), line_id),
            )

    def set_metadata(self, values: dict[str, str]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    def metadata(self) -> dict[str, str]:
        return dict(self.connection.execute("SELECT key,value FROM metadata"))

    def set_info(self, values: dict[str, str]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT INTO project_info(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    def info(self) -> dict[str, str]:
        return dict(self.connection.execute("SELECT key,value FROM project_info"))

    def transcription_summary(self) -> dict[str, int]:
        row = self.connection.execute(
            """SELECT COUNT(*) AS line_count,
                      SUM(CASE WHEN corrected_text IS NOT NULL THEN 1 ELSE 0 END) AS corrected_count,
                      SUM(CASE WHEN review_status != 'unreviewed' THEN 1 ELSE 0 END) AS reviewed_count
               FROM lines"""
        ).fetchone()
        return {
            "line_count": int(row["line_count"] or 0),
            "corrected_count": int(row["corrected_count"] or 0),
            "reviewed_count": int(row["reviewed_count"] or 0),
        }

    def reset_transcription(self) -> None:
        """Remove derived page/line results while retaining the source and metadata."""

        with self.connection:
            # Lines and correction history are removed by foreign-key cascades.
            self.connection.execute("DELETE FROM pages")
            self.connection.execute(
                "DELETE FROM project_info WHERE key IN ('segmentation_backend','segmentation_version')"
            )

