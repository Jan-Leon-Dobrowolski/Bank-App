import os
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Iterable
from uuid import uuid4
from datetime import datetime, timezone

# ======================= USTAWIENIA ============================================
# Baza danych SQLite tworzona jest w katalogu obok pliku .py
BASE_DIR = Path(__file__).parent.resolve()
DB_FILE = BASE_DIR / "accounts.db"

# ======================= FUNKCJE POMOCNICZE ====================================
def now_utc_iso() -> str:
    """Zwraca aktualny czas UTC w formacie ISO-8601 (łatwy do sortowania)."""
    return datetime.now(timezone.utc).isoformat()

def to_cents(amount_str: str) -> int:
    """
    Konwertuje kwotę wpisaną przez użytkownika (np. '123.45' lub '123,45')
    na grosze (int).  
    Używamy Decimal zamiast float, aby uniknąć błędów zaokrągleń.
    """
    s = amount_str.replace(",", ".").strip()
    try:
        dec = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Podaj poprawną kwotę, np. 12.34")
    if dec < 0:
        raise ValueError("Kwota nie może być ujemna")
    return int(dec * 100)

def fmt_pln(cents: int) -> str:
    """
    Formatuje kwotę w groszach (int) do zapisu w złotówkach z dwoma miejscami po przecinku.
    """
    dec = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))
    return f"{dec} PLN"

def gen_id() -> str:
    """Generuje unikalny identyfikator konta (uuid4, 32 znaki hex)."""
    return uuid4().hex

# ======================= MODEL DOMENOWY ========================================
@dataclass(frozen=True)
class Account:
    """
    Reprezentacja konta bankowego w logice aplikacji.  
    balance_cents – saldo w groszach (int, bez floatów).  
    created_at – data utworzenia konta.
    """
    id: str
    balance_cents: int
    created_at: str

# ======================= REPOZYTORIUM (SQLite) ================================
class AccountsRepo:
    """
    Warstwa dostępu do danych.  
    Odpowiada za tworzenie schematu bazy, zapis/odczyt danych i audyt operacji.  
    Logika biznesowa aplikacji nie musi znać SQL – wszystko przechodzi przez tę klasę.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        """Tworzy nowe połączenie z bazą SQLite."""
        return sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

    def _init_db(self):
        """
        Inicjalizuje strukturę bazy danych (jeśli jeszcze nie istnieje).  
        - Tabela accounts – stan konta + metadane  
        - Tabela audit – historia operacji (append-only)  
        """
        with self._conn() as con:
            cur = con.cursor()
            cur.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS accounts(
                    id TEXT PRIMARY KEY,
                    balance_grosze INTEGER NOT NULL CHECK(balance_grosze >= 0),
                    -- kolumny pin_hash / pin_salt zostawione dla kompatybilności (nieużywane)
                    pin_hash TEXT NOT NULL DEFAULT '',
                    pin_salt TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    event TEXT NOT NULL,               -- CREATED / DEPOSIT / WITHDRAW
                    amount_grosze INTEGER NOT NULL,    -- zawsze dodatnia wartość
                    ts TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(id)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_account_ts ON audit(account_id, ts);
                """
            )

    # -------------------- OPERACJE NA KONCIE (bez PIN-u) -----------------------
    def create_account(self, initial_cents: int) -> Account:
        """Tworzy nowe konto z podanym saldem początkowym i zapisuje je w bazie."""
        if initial_cents < 0:
            raise ValueError("Saldo początkowe nie może być ujemne")
        acc_id = gen_id()
        created_at = now_utc_iso()
        with self._conn() as con:
            cur = con.cursor()
            # zapis konta
            cur.execute(
                "INSERT INTO accounts(id, balance_grosze, pin_hash, pin_salt, created_at) VALUES(?,?,?,?,?)",
                (acc_id, initial_cents, "", "", created_at),
            )
            # wpis w audycie
            cur.execute(
                "INSERT INTO audit(account_id, event, amount_grosze, ts) VALUES(?,?,?,?)",
                (acc_id, "CREATED", initial_cents, created_at),
            )
        return Account(acc_id, initial_cents, created_at)

    def _require_account(self, acc_id: str):
        """Sprawdza, czy konto istnieje – zwraca jego dane albo rzuca wyjątek."""
        with self._conn() as con:
            cur = con.cursor()
            row = cur.execute(
                "SELECT id, balance_grosze, created_at FROM accounts WHERE id=?",
                (acc_id,),
            ).fetchone()
            if not row:
                raise ValueError("Nie znaleziono konta")
            return row  # (id, saldo, data utworzenia)

    def deposit(self, acc_id: str, amount_cents: int) -> int:
        """Wykonuje wpłatę na konto i zwraca nowe saldo."""
        if amount_cents <= 0:
            raise ValueError("Kwota wpłaty musi być > 0")
        with self._conn() as con:
            cur = con.cursor()
            _, balance, _ = self._require_account(acc_id)
            new_balance = balance + amount_cents
            # transakcja SQL
            cur.execute("BEGIN")
            cur.execute("UPDATE accounts SET balance_grosze=? WHERE id=?", (new_balance, acc_id))
            cur.execute(
                "INSERT INTO audit(account_id, event, amount_grosze, ts) VALUES(?,?,?,?)",
                (acc_id, "DEPOSIT", amount_cents, now_utc_iso()),
            )
            con.commit()
            return new_balance

    def withdraw(self, acc_id: str, amount_cents: int) -> int:
        """Wykonuje wypłatę z konta i zwraca nowe saldo."""
        if amount_cents <= 0:
            raise ValueError("Kwota wypłaty musi być > 0")
        with self._conn() as con:
            cur = con.cursor()
            _, balance, _ = self._require_account(acc_id)
            if amount_cents > balance:
                raise ValueError("Kwota wypłaty przekracza saldo")
            new_balance = balance - amount_cents
            cur.execute("BEGIN")
            cur.execute("UPDATE accounts SET balance_grosze=? WHERE id=?", (new_balance, acc_id))
            cur.execute(
                "INSERT INTO audit(account_id, event, amount_grosze, ts) VALUES(?,?,?,?)",
                (acc_id, "WITHDRAW", amount_cents, now_utc_iso()),
            )
            con.commit()
            return new_balance

    def list_accounts(self) -> Iterable[Account]:
        """Zwraca listę wszystkich kont (ID, saldo, data utworzenia)."""
        with self._conn() as con:
            cur = con.cursor()
            for row in cur.execute("SELECT id, balance_grosze, created_at FROM accounts ORDER BY created_at DESC"):
                yield Account(row[0], row[1], row[2])

    def account_balance(self, acc_id: str) -> int:
        """Zwraca aktualne saldo wskazanego konta."""
        with self._conn() as con:
            cur = con.cursor()
            row = cur.execute("SELECT balance_grosze FROM accounts WHERE id=?", (acc_id,)).fetchone()
            if not row:
                raise ValueError("Nie znaleziono konta")
            return int(row[0])

# ======================= LOGIKA CLI ============================================
def action_create(repo: AccountsRepo):
    """Obsługuje opcję: tworzenie nowego konta."""
    print("\n=== Tworzenie konta ===", flush=True)
    print("Saldo początkowe (zł, np. 100.00): ", end="", flush=True)
    init = input().strip()
    acc = repo.create_account(to_cents(init))
    print(f"OK. Konto utworzone. ID: {acc.id}")
    print(f"   Saldo: {fmt_pln(acc.balance_cents)}  (baza: {DB_FILE.name})")

def action_deposit(repo: AccountsRepo):
    """Obsługuje opcję: wpłata na konto."""
    print("\n=== Wpłata ===", flush=True)
    print("ID konta: ", end="", flush=True)
    acc_id = input().strip()
    print("Kwota (np. 10.00): ", end="", flush=True)
    amount = input().strip()
    new_bal = repo.deposit(acc_id, to_cents(amount))
    print(f"OK. Nowe saldo: {fmt_pln(new_bal)}")

def action_withdraw(repo: AccountsRepo):
    """Obsługuje opcję: wypłata z konta."""
    print("\n=== Wypłata ===", flush=True)
    print("ID konta: ", end="", flush=True)
    acc_id = input().strip()
    print("Kwota (np. 10.00): ", end="", flush=True)
    amount = input().strip()
    new_bal = repo.withdraw(acc_id, to_cents(amount))
    print(f"OK. Nowe saldo: {fmt_pln(new_bal)}")

def action_list(repo: AccountsRepo):
    """Obsługuje opcję: lista wszystkich kont."""
    print("\n--- Lista kont ---", flush=True)
    empty = True
    for acc in repo.list_accounts():
        empty = False
        print(f"ID: {acc.id} | Saldo: {fmt_pln(acc.balance_cents)} | Utworzone: {acc.created_at}")
    if empty:
        print("(brak kont)")
    print(f"(Plik bazy: {DB_FILE})")

def main():
    """Główna pętla menu CLI – prosty interfejs tekstowy."""
    repo = AccountsRepo(DB_FILE)
    while True:
        print("\n=== SYSTEM BANKOWY (CLI) ===", flush=True)
        print("1. Utwórz konto")
        print("2. Wpłata")
        print("3. Wypłata")
        print("4. Pokaż wszystkie konta")
        print("5. Pokaż saldo konta")
        print("6. Wyjście")
        print("Wybierz opcję: ", end="", flush=True)
        choice = input().strip()
        try:
            if choice == "1":
                action_create(repo)
            elif choice == "2":
                action_deposit(repo)
            elif choice == "3":
                action_withdraw(repo)
            elif choice == "4":
                action_list(repo)
            elif choice == "5":
                print("ID konta: ", end="", flush=True)
                acc_id = input().strip()
                bal = repo.account_balance(acc_id)
                print(f"Saldo: {fmt_pln(bal)}")
            elif choice == "6":
                print("Zamykanie…")
                break
            else:
                print("Nieprawidłowy wybór.")
        except ValueError as e:
            print("Błąd:", e)

if __name__ == "__main__":
    print("Katalog roboczy:", os.getcwd())
    print("Plik bazy:", DB_FILE)
    main()