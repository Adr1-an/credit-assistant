"""Переносит файлы бэка из корня репозитория в папку backend/ (через git mv, история сохраняется).

Запуск из корня репозитория:  python fix_structure.py
Ничего не удаляет из нужного: заглушка app/ai/ удаляется, потому что настоящий блок ИИ уже лежит в backend/app/ai/.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def git(*args):
    print("git", *args)
    subprocess.run(["git", *args], check=True)


if not (ROOT / ".git").exists() or not (ROOT / "contract").is_dir():
    sys.exit("Запустите из корня репозитория (там, где папки contract, frontend, backend).")
if not (ROOT / "app").is_dir():
    sys.exit("Папки app/ в корне нет — похоже, перенос уже сделан. Ничего не меняю.")
if not (ROOT / "backend" / "app" / "ai" / "tests").is_dir():
    sys.exit("Нет backend/app/ai/tests — блок ИИ не на месте. Остановился, напишите мне.")

# 1. Заглушка ИИ в корне — не нужна, настоящий блок в backend/app/ai/
if (ROOT / "app" / "ai").exists():
    git("rm", "-r", "-q", "app/ai")

# 2. Код бэка: app/* → backend/app/*
for p in sorted((ROOT / "app").iterdir()):
    if p.name == "__pycache__":
        continue
    git("mv", f"app/{p.name}", f"backend/app/{p.name}")

# 3. Файлы бэка из корня
for name in ("Dockerfile", "requirements.txt", "requirements-dev.txt", "pytest.ini"):
    if (ROOT / name).exists():
        git("mv", name, f"backend/{name}")

# 4. Автотесты бэка: tests/ → backend/tests/
(ROOT / "backend" / "tests").mkdir(exist_ok=True)
for name in ("conftest.py", "test_edge_cases.py", "test_end_to_end.py", "test_passport.py", "test_steps_1_3.py"):
    if (ROOT / "tests" / name).exists():
        git("mv", f"tests/{name}", f"backend/tests/{name}")

# 5. Служебный файл macOS
if (ROOT / ".DS_Store").exists():
    git("rm", "-q", "--cached", "--ignore-unmatch", ".DS_Store")
    (ROOT / ".DS_Store").unlink()

# 6. Пустая папка app/ после переноса
import shutil
if (ROOT / "app").is_dir() and not any(f.is_file() and f.suffix != ".pyc" for f in (ROOT / "app").rglob("*")):
    shutil.rmtree(ROOT / "app")

print("\nГотово. Теперь скопируйте файлы из архива и проверьте git status.")
