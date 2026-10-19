"""Connexion MySQL, création du schéma et insertion idempotente (upsert)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import URL, Engine, MetaData, Table, create_engine, text
from sqlalchemy.dialects.mysql import insert

from nhl_forecast.config import PROJECT_ROOT, Settings, get_settings

log = logging.getLogger(__name__)

SCHEMA_DIR = PROJECT_ROOT / "sql" / "schema"
_BATCH_SIZE = 1_000


def make_engine(settings: Settings | None = None) -> Engine:
    s = settings or get_settings()
    url = URL.create(
        "mysql+pymysql",
        username=s.mysql_user,
        password=s.mysql_password.get_secret_value(),
        host=s.mysql_host,
        port=s.mysql_port,
        database=s.mysql_database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def apply_schema(engine: Engine, schema_dir: Path = SCHEMA_DIR) -> None:
    """Exécute les fichiers ``*.sql`` du dossier, dans l'ordre (``CREATE TABLE IF NOT EXISTS``)."""
    for path in sorted(schema_dir.glob("*.sql")):
        sql = re.sub(r"^\s*--.*$", "", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        log.info("Schéma appliqué : %s (%d instructions)", path.name, len(statements))


class TableWriter:
    """Insère des lignes (dict) dans des tables existantes, avec mise à jour en cas de doublon.

    Seules les clés correspondant à une colonne de la table sont insérées : un champ ajouté
    par la NHL dans l'API est ignoré (signalé une fois) au lieu de faire échouer le chargement.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._tables: dict[str, Table] = {}
        self._warned: set[tuple[str, str]] = set()

    def table(self, name: str) -> Table:
        if name not in self._tables:
            self._tables[name] = Table(name, MetaData(), autoload_with=self.engine)
        return self._tables[name]

    def upsert(self, table_name: str, rows: Iterable[dict]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        table = self.table(table_name)
        columns = set(table.columns.keys())

        present = set().union(*(r.keys() for r in rows))
        for key in sorted(present - columns):
            if (table_name, key) not in self._warned:
                self._warned.add((table_name, key))
                log.info("%s : champ « %s » absent du schéma, ignoré", table_name, key)

        keep = sorted(present & columns)
        values = [{c: r.get(c) for c in keep} for r in rows]
        primary = {c.name for c in table.primary_key.columns}

        stmt = insert(table)
        updates = {c: stmt.inserted[c] for c in keep if c not in primary}
        stmt = stmt.on_duplicate_key_update(updates) if updates else stmt.prefix_with("IGNORE")
        with self.engine.begin() as conn:
            for i in range(0, len(values), _BATCH_SIZE):
                conn.execute(stmt, values[i : i + _BATCH_SIZE])
        return len(values)

    def existing(self, sql: str, **params) -> set:
        """Valeurs de la première colonne d'une requête (ex. matchs déjà chargés)."""
        with self.engine.connect() as conn:
            return {row[0] for row in conn.execute(text(sql), params)}
