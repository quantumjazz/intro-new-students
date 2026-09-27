# Първият ход е ваш

Встъпителна среща с първокурсниците в бакалавърската програма „Управление на
бизнеса и предприемачество“ (НБУ), около 25 минути, и класната игра към нея.

| | |
|---|---|
| Презентацията | `vavedenie.qmd` → `vavedenie.html` (един самостоятелен файл) |
| Играта „Две трети от средното“ | `intro-game/`, на живо на https://intro.visiometrica.com |

## Презентацията

```bash
quarto render vavedenie.qmd
```

Quarto reveal.js, 1920×1080, тема `vavedenie.scss`, шрифтове Sofia Sans
(`fonts/`, SIL Open Font License). По време на лекцията: S = бележки,
F = цял екран.

- Картата на кредитите, лентите по години и анимацията за II семестър се
  генерират от данните в `tools/program_slides.py` → `_program/*.qmd`.
- QR кодът на слайдове 1 и 2: `python3 tools/make_qr.py [адрес]`.
- Слайдът „резултатите“ вгражда `intro.visiometrica.com/results` и го води с
  кликера (`live-results.html`); без връзка остава стълбата за вдигане на ръце.
  Локална проба: `vavedenie.html?results=http://localhost:8004`.

Изходните презентации, от които е събрана: `parviyat-hod.qmd`,
`programna-shema.qmd`, `semestar-2-animacia.qmd`.

## Играта

Виж [intro-game/README.md](intro-game/README.md): студентска страница,
админ страница и страница с резултатите, Python без външни зависимости и
SQLite, инсталация на лаптопа с `intro-game/deploy/install.sh`.
