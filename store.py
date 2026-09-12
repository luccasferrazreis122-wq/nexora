"""PostgreSQL externo em produção gratuita; SQLite disponível para testes locais."""
import hashlib
import os
import shutil
import tempfile
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class ServiceError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def postgres_ca_file():
    import certifi
    source = Path(certifi.where())
    if not source.is_file():
        raise RuntimeError("Arquivo de certificados ausente; reinstale certifi no ambiente do backend.")
    if os.name != "nt" or str(source).isascii():
        yield str(source)
        return
    # libpq/OpenSSL no Windows pode interpretar incorretamente caminhos com acentos.
    # Copiamos somente certificados públicos; nunca a conexão ou a senha.
    with tempfile.TemporaryDirectory(prefix="nexora-ca-") as directory:
        target = Path(directory) / "cacert.pem"
        if not str(target).isascii():
            raise RuntimeError("Configure TEMP para uma pasta sem acentos para acessar os certificados PostgreSQL.")
        shutil.copyfile(source, target)
        yield str(target)


class PostgresConnection:
    """Adapta as consultas internas fixas, nunca SQL fornecido pelo usuário."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        return self.connection.execute(sql.replace("?", "%s"), parameters)

    def executescript(self, sql):
        for statement in sql.replace("REAL", "DOUBLE PRECISION").split(";"):
            if statement.strip():
                self.execute(statement)


class Store:
    def __init__(self, settings, clock=time.time):
        self.settings, self.clock = settings, clock
        self.postgres = settings.database.startswith(("postgres://", "postgresql://"))
        if not self.postgres:
            Path(settings.database).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, label TEXT NOT NULL, days INTEGER NOT NULL,
                    expires_at REAL, disabled INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    kind TEXT NOT NULL, expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS token_user ON tokens(user_id);
                CREATE INDEX IF NOT EXISTS token_expiry ON tokens(expires_at);
                CREATE TABLE IF NOT EXISTS counters (
                    scope TEXT NOT NULL, bucket INTEGER NOT NULL, period INTEGER NOT NULL,
                    count INTEGER NOT NULL, PRIMARY KEY(scope, bucket, period)
                );
                CREATE TABLE IF NOT EXISTS installations (
                    hash TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id)
                );
            """)

    @contextmanager
    def transaction(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            with postgres_ca_file() as ca_file, psycopg.connect(
                    self.settings.database, row_factory=dict_row,
                    connect_timeout=15, sslmode="verify-full", sslrootcert=ca_file) as connection:
                with connection.transaction():
                    connection.execute("SET LOCAL lock_timeout = '10s'")
                    connection.execute("SET LOCAL statement_timeout = '20s'")
                    # A mesma exclusão mútua do BEGIN IMMEDIATE, compartilhada entre instâncias.
                    # O lock é liberado antes de chamar a OpenAI.
                    connection.execute("SELECT pg_advisory_xact_lock(7349821001)")
                    yield PostgresConnection(connection)
            return
        db = sqlite3.connect(self.settings.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _token(self, db, user_id, kind, expires):
        raw = "nx_" + secrets.token_urlsafe(32)
        db.execute("INSERT INTO tokens VALUES (?, ?, ?, ?)", (digest(raw), user_id, kind, expires))
        return raw

    def provision(self, label, days=7):
        if not 1 <= days <= 3660 or not label.strip():
            raise ValueError("Informe identificação e duração entre 1 e 3660 dias")
        user_id = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO users(id,label,days) VALUES(?,?,?)", (user_id, label.strip(), days))
            code = self._token(db, user_id, "activation", self.clock() + 7 * 86400)
        return user_id, code

    def reissue(self, user_id):
        with self.transaction() as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or user["disabled"]:
                raise ValueError("Usuário ausente ou revogado")
            db.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
            return self._token(db, user_id, "activation", self.clock() + 7 * 86400)

    def revoke(self, user_id):
        with self.transaction() as db:
            db.execute("UPDATE users SET disabled=1 WHERE id=?", (user_id,))
            db.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))

    def extend(self, user_id, days):
        if not 1 <= days <= 3660:
            raise ValueError("Duração inválida")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Usuário não encontrado")
            if row["expires_at"] is None:
                db.execute("UPDATE users SET days=?, disabled=0 WHERE id=?", (days, user_id))
            else:
                expires = max(self.clock(), row["expires_at"]) + days * 86400
                db.execute("UPDATE users SET expires_at=?, disabled=0 WHERE id=?", (expires, user_id))

    def _lookup(self, db, raw, kind):
        row = db.execute("""SELECT u.*, t.expires_at AS token_expires FROM tokens t
                            JOIN users u ON u.id=t.user_id WHERE t.hash=? AND t.kind=?""",
                         (digest(raw), kind)).fetchone()
        if not row or row["token_expires"] <= self.clock():
            raise ServiceError(401, "session_expired" if kind != "activation" else "invalid_activation")
        if row["disabled"] or (row["expires_at"] is not None and row["expires_at"] <= self.clock()):
            raise ServiceError(403, "access_expired")
        return row

    def exchange(self, raw, kind):
        now = self.clock()
        with self.transaction() as db:
            user = self._lookup(db, raw, kind)
            expires = user["expires_at"] or now + user["days"] * 86400
            db.execute("UPDATE users SET expires_at=? WHERE id=?", (expires, user["id"]))
            # Código e refresh são de uso único. Uma nova sessão invalida os access anteriores.
            db.execute("DELETE FROM tokens WHERE user_id=?", (user["id"],))
            access_expires = min(expires, now + self.settings.access_seconds)
            refresh_expires = min(expires, now + self.settings.refresh_seconds)
            return {
                "access_token": self._token(db, user["id"], "access", access_expires),
                "refresh_token": self._token(db, user["id"], "refresh", refresh_expires),
                "expires_in": int(access_expires - now),
                "access_expires_at": access_expires,
                "entitlement_expires_at": expires,
                "user_id": user["id"],
            }

    def trial(self, secret, peer):
        """A mesma credencial recupera o mesmo prazo, inclusive após resposta perdida."""
        now = self.clock()
        with self.transaction() as db:
            user = db.execute("""SELECT u.* FROM installations i JOIN users u
                                 ON u.id=i.user_id WHERE i.hash=?""", (digest(secret),)).fetchone()
            if user is None:
                if not self.settings.trials_enabled:
                    raise ServiceError(403, "trials_unavailable")
                self._consume(db, [
                    ("trial-global", 86400, self.settings.trial_daily_registrations),
                    ("trial-peer:" + digest(peer), 86400, self.settings.trial_peer_daily_registrations),
                ])
                uid = uuid.uuid4().hex
                db.execute("INSERT INTO users(id,label,days,expires_at) VALUES(?,?,?,?)",
                           (uid, "Teste automático " + uid[:8], 7, now + 7 * 86400))
                db.execute("INSERT INTO installations VALUES(?,?)", (digest(secret), uid))
                user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if user["disabled"] or user["expires_at"] <= now:
                raise ServiceError(403, "access_expired")
            expires = user["expires_at"]
            db.execute("DELETE FROM tokens WHERE user_id=?", (user["id"],))
            access_expires = min(expires, now + self.settings.access_seconds)
            return {
                "access_token": self._token(db, user["id"], "access", access_expires),
                "refresh_token": self._token(db, user["id"], "refresh", min(expires, now + self.settings.refresh_seconds)),
                "expires_in": int(access_expires - now),
                "entitlement_expires_at": expires, "user_id": user["id"],
            }

    def _consume(self, db, limits):
        now = int(self.clock())
        db.execute("DELETE FROM counters WHERE bucket * period < ?", (now - 2 * 86400,))
        db.execute("DELETE FROM tokens WHERE expires_at < ?", (now,))
        for scope, period, limit in limits:
            bucket = now // period
            row = db.execute("SELECT count FROM counters WHERE scope=? AND bucket=? AND period=?",
                             (scope, bucket, period)).fetchone()
            if row and row["count"] >= limit:
                raise ServiceError(429, "daily_limit" if period == 86400 else "rate_limit")
            db.execute("""INSERT INTO counters VALUES(?,?,?,1)
                          ON CONFLICT(scope,bucket,period) DO UPDATE SET count=counters.count+1""",
                       (scope, bucket, period))

    def throttle_auth(self, peer):
        with self.transaction() as db:
            self._consume(db, [("auth:" + digest(peer), 60, 10), ("auth-global", 60, 100)])

    def authorize(self, raw, charge=False):
        with self.transaction() as db:
            user = self._lookup(db, raw, "access")
            if charge:
                s = self.settings
                self._consume(db, [
                    ("user:" + user["id"], 60, s.user_minute_requests),
                    ("global", 60, s.global_minute_requests),
                    ("user:" + user["id"], 86400, s.user_daily_requests),
                    ("global", 86400, s.global_daily_requests),
                ])
            row = db.execute("SELECT count FROM counters WHERE scope=? AND bucket=? AND period=86400",
                             ("user:" + user["id"], int(self.clock()) // 86400)).fetchone()
            return {"user_id": user["id"], "active": True, "expires_at": user["expires_at"],
                    "daily_remaining": max(0, self.settings.user_daily_requests - (row["count"] if row else 0))}

    def users(self):
        with self.transaction() as db:
            return [dict(row) for row in db.execute("SELECT * FROM users ORDER BY label")]

    def backup(self, destination):
        if self.postgres:
            raise ValueError("Use pg_dump ou exportação do provedor para backup PostgreSQL")
        # SQLite backup API inclui transações concluídas, sem copiar arquivos abertos.
        with sqlite3.connect(self.settings.database) as source, sqlite3.connect(destination) as target:
            source.backup(target)
