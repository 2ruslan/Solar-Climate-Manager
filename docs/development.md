# Розробка та перевірки

## Базове середовище

Для інтеграційних тестів зафіксовано Home Assistant **2026.10.1**, Python **3.14.2** і `pytest-homeassistant-custom-component==0.13.372`. Це ціль перевірки сумісності, а не підтвердження підтримки всіх старіших версій HA. Python 3.11 використовується лише для незалежного unit-набору.

Версії вибрані за [метаданими HA](https://pypi.org/pypi/homeassistant/2026.10.1/json) і [тестового плагіна](https://pypi.org/pypi/pytest-homeassistant-custom-component/0.13.372/json). Прямі залежності закріплені в `requirements/`; їхні транзитивні залежності додатково обмежені самим HA і плагіном. Це не повний lock-файл усіх пакетів.

## Швидкі локальні перевірки (Windows або Linux)

Створіть venv; у Windows замість `python3` можна використати `py -3.11` або встановлений Python 3.14.2:

```sh
python3 -m venv .venv
```

Активуйте його: `.venv\Scripts\Activate.ps1` у PowerShell або `source .venv/bin/activate` у bash. Далі:

```sh
python -m pip install -r requirements/dev.txt
python -m ruff check .
python -m mypy
python -m unittest discover -s tests/unit -v
python -m compileall -q custom_components tests
```

## Повна перевірка на Linux / WSL

У чистому venv із Python 3.14.2 виконайте:

```sh
python -m pip install -r requirements/ha.txt
python -m pip check
python -m ruff check .
python -m mypy
python -m unittest discover -s tests/unit -v
python -m pytest -q tests/ha
```

Unit і HA запускаються **окремими процесами**. Unit-тести адаптера підміняють `homeassistant.*` у `sys.modules`; не запускайте `pytest tests` чи обидва набори в одному процесі. Звичайний `python -m pytest` збирає лише `tests/ha` згідно з `pyproject.toml`.

## Linux-тести через Docker із Windows

Потрібен запущений Docker Desktop у режимі Linux containers. З кореня репозиторію в PowerShell:

```powershell
docker run --rm --mount "type=bind,source=$($PWD.Path),target=/workspace,readonly" -w /workspace -e PYTHONDONTWRITEBYTECODE=1 python:3.14.2-slim-bookworm sh -c 'python -m pip install -r requirements/ha.txt && python -m pip check && python -m ruff check --no-cache . && python -m mypy --cache-dir=/tmp/mypy-cache && python -m unittest discover -s tests/unit -v && python -m pytest -q tests/ha -o cache_dir=/tmp/pytest-cache'
```

Проєкт змонтовано лише для читання. Залежності й тимчасові файли залишаються в контейнері та видаляються після виходу. Початкове встановлення залежностей потребує мережі; самі тести використовують моделі пристроїв, без фізичних кондиціонерів.

## Шаблон CI (вимкнено)

`docs/ci/tests.yml.disabled` — неактивний шаблон. GitHub не запускає його; тести наразі виконуються лише локально. Шаблон містить такі перевірки:

- Ruff і строгий mypy для domain/strategy/window/presentation/storage на Python 3.14.2.
- Unit-тести й перевірка компіляції на Python 3.11 та 3.14.2.
- HA-тести на Ubuntu 24.04 / Python 3.14.2; перевірка залежностей і JUnit-звіт як artifact, зокрема при падінні тестів.

Оновлюйте HA і тестовий плагін разом, перевіряючи їхні метадані. Якщо змінюється потрібний Python, синхронно змініть workflow, Docker-приклад та цей документ. Успішні локальні перевірки не означають, що віддалений workflow уже виконувався.
## Регресійні сценарії першого етапу

| Поведінка | Перевірка |
|---|---|
| Чотири режими select та reload | HA: `test_select_mode_replaces_switch_and_survives_reload` |
| Заборона команд поза control | HA: `test_non_control_modes_send_no_climate_commands` (3 режими) |
| Тимчасове блокування, reload та місцева північ | HA: `test_temporary_block_survives_reload_and_returns_at_local_midnight` |
| Скасування незавершеної команди при unload | HA: `test_unload_cancels_inflight_climate_command` |
| Timeout не залишає завислу задачу | Unit: `test_service_timeout_is_reported_and_does_not_leave_worker_stuck` |
| Захисна зупинка під час старту | Unit: `test_pending_start_is_followed_immediately_by_protective_stop` |
| Зміна режиму скасовує команду в черзі | Unit: `test_mode_change_cancels_queued_command` |
| Ручна зміна й повернення попереднього режиму | Unit: `test_temporary_block_returns_each_previous_mode_at_local_midnight` |

Наявні unit-сценарії не дублюються механічно; нові HA-тести перевіряють саме межі реального фреймворку — платформи, події, часовий пояс, reload та unload.


## Перевірений результат першого етапу

2026-10-14: 143 unit-тести пройшли на Windows / Python 3.11 і Linux / Python 3.14.2; 18 HA-тестів — на Linux / Python 3.14.2 / HA 2026.10.1. Ruff, перевірка синтаксису та `pip check` пройшли. GitHub workflow ще не запускався: ці результати отримано локально, з HA в чистому Docker-контейнері. Локальний JUnit-звіт збережено в `test-results/ha.xml` і виключено з Git.

Для HA увімкнено строгі перевірки конфігурації/маркерів pytest та ліміт 60 секунд на тест. Робочий код інтеграції в першому етапі не змінювався.


## Перевірений результат другого етапу

2026-10-15: 150 unit-тестів пройшли на Windows / Python 3.11 і Linux / Python 3.14.2; 18 HA-тестів — на Linux / Python 3.14.2 / HA 2026.10.1. Додано mypy 2.4.0 до dev-залежностей і CI; область строгого аналізу поки обмежена чотирма файлами чистого ядра.

Нові контрактні регресії перевіряють незавершений старт, відкладену зупинку, незмінність входів, ізоляцію історії вікна й даних команд, legacy-конфігурацію та формат Store v1. Одноразове детерміноване порівняння зі стратегією до рефакторингу перевірило 10 000 послідовних рішень, стан збереження та історію вікна — розбіжностей немає. Це доповнює регресійні тести, але не доводить еквівалентність для всіх можливих входів.


2026-10-15: за рішенням користувача автоматичні перевірки GitHub вимкнено. Шаблон винесено за межі `.github/workflows/` і перейменовано на `tests.yml.disabled`. Для майбутнього ввімкнення його потрібно явно повернути як `.github/workflows/tests.yml`; зараз цього робити не потрібно.


## Перевірений результат третього етапу

2026-10-15: 159 unit-тестів пройшли на Windows / Python 3.11 і Linux / Python 3.14.2; 18 HA-тестів — на Linux / HA 2026.10.1. Новий набір `tests/unit/test_adapters.py` перевіряє capture/нормалізацію, метадані актуальності, Store v1 і приватність експорту. Команда `python -m mypy` тепер охоплює сім файлів; відсутні пакети HA допускаються лише для імпортів `homeassistant.*` у легкому локальному середовищі.

Публічний стан і persistence додатково порівняно з координатором до етапу 3 на 2 000 оцінюваннях — без розбіжностей. Локальний звіт HA: `test-results/ha-stage3.xml`. GitHub-тести залишаються вимкненими.

## Перевірений результат четвертого етапу

2026-10-15: 165 unit-тестів пройшли на Windows / Python 3.11 і Linux / Python 3.14.2; 18 HA-тестів — на Linux / Python 3.14.2 / HA 2026.10.1. Ruff, строгий mypy (8 файлів, включно з runtime/device.py), compileall, pip check та git diff --check пройшли. Linux-перевірки виконано локально в окремому Docker-контейнері, який автоматично видалено після завершення.

Нові сценарії перевіряють завершення сервісу без підтвердження, часткову відповідь, фізичний стан після timeout зупинки, пізнє підтвердження off, ручну зміну під час команди, скасування активного сервісу при зміні режиму/unload, ігнорування подій після shutdown та читання diagnostics із нового runtime. Наявний HA-тест unload використовує задачу CommandExecutor. GitHub workflow залишається вимкненим.
