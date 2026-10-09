# AGENTS.md

## Status

Приложение на Python + PySide6 (Qt): стартовый экран с характеристиками ПК и модули
оптимизации Windows (очистка файлов, автозагрузка, службы, память, твики реестра/сети).
Точка входа — `main.py`, зависимости — `requirements.txt`, описание — `README.md`.

Запуск из исходников: `python -m pip install -r requirements.txt` затем `python main.py`.
Тестов/линтера пока нет. Python в этом окружении не установлен (только заглушка из
Microsoft Store), поэтому здесь код не запускается — проверяйте на машине с Python 3.10+.

## Environment gotcha

Git is installed but **not on PATH** in this environment, so a bare `git ...`
fails with "command not found". Use the full path:

```powershell
& "C:\Program Files\Git\cmd\git.exe" status
```

## Remote

- Origin: `https://github.com/jNYAAAA/optimizer-game.git`
- Default branch: `main` (tracks `origin/main`)
- Credentials are cached; `git push` works without further auth setup.
