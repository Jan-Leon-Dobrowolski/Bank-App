# Bank Account CLI (Python + SQLite)

Napisałem tę aplikację konsolową jako ćwiczenie z Pythona i SQL. Program symuluje prosty system bankowy i pozwala zarządzać kontami oraz śledzić historię operacji.

## Funkcje
- tworzenie kont z saldem początkowym,
- wpłaty i wypłaty z kontrolą stanu konta,
- sprawdzanie aktualnego salda,
- lista wszystkich kont,
- zapisywanie historii operacji w bazie SQLite (audit log).

## Użyte technologie
- Python 3.10+
- SQLite (transakcje, indeksy, klucze obce)
- standardowa biblioteka Pythona: `sqlite3`, `dataclasses`, `decimal`, `uuid`, `pathlib`

## Pliki
- `main.py` – logika aplikacji i interfejs tekstowy
- `accounts.db` – baza SQLite, tworzona automatycznie przy pierwszym uruchomieniu

## Jak uruchomić
1. Sklonuj repozytorium:
   ```bash
   git clone https://github.com/twoj-nick/bank-account-cli.git
   cd bank-account-cli
   ```

2. Sprawdź wersję Pythona (wymagany 3.10+):
   ```bash
   python --version
   ```

3. Uruchom program:
   ```bash
   python main.py
   ```

## Przykład działania
```
=== SYSTEM BANKOWY (CLI) ===
1. Utwórz konto
2. Wpłata
3. Wypłata
4. Pokaż wszystkie konta
5. Pokaż saldo konta
6. Wyjście
Wybierz opcję: 1

=== Tworzenie konta ===
Saldo początkowe (zł, np. 100.00): 50
OK. Konto utworzone. ID: 9d3f82c6b5d349c68f99c9c9477b0e29
   Saldo: 50.00 PLN  (baza: accounts.db)
```

## Dlaczego ten projekt
Chciałem przećwiczyć praktyczne użycie Pythona i SQL.  
Zastosowałem `Decimal` do obliczeń na pieniądzach, aby uniknąć błędów z `float`. Oddzieliłem logikę od warstwy bazodanowej w klasie `AccountsRepo`. Dzięki temu kod jest czytelniejszy i łatwiejszy do rozbudowy.

## Możliwe dalsze kroki
- dodać testy jednostkowe (`pytest`),
- eksport danych do CSV/JSON,
- obsługa wielu użytkowników,
- zamiana prostego menu CLI na `argparse` albo `click`.
