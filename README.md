# Retro FPS Game

A retro-style first-person shooter built with **Python** and the **[Pyxel](https://github.com/kitao/pyxel)** library.

---

## ▶ Play in Browser

Click the badge below to launch the game instantly in your browser (virtual gamepad included):

[![Play on Pyxel Web](https://img.shields.io/badge/Play-Pyxel%20Web-blue?style=for-the-badge)](https://kitao.github.io/pyxel/wasm/launcher/?play=zencha201/retro_fps_game2/main/retro_fps_game2&gamepad=enabled)

> **Direct link:**
> `https://kitao.github.io/pyxel/wasm/launcher/?play=zencha201/retro_fps_game2/main/retro_fps_game2&gamepad=enabled`

---

## 🎮 Controls

| Input | Action |
|-------|--------|
| ↑ Arrow / D-pad Up | Move Forward |
| ↓ Arrow / D-pad Down | Move Backward |
| ← Arrow / D-pad Left | Turn Left |
| → Arrow / D-pad Right | Turn Right |
| **Space** / **A Button** | Shoot |

---

## 📋 Game Overview

### Screen Layout

```
┌──────────────────────┬──────┐
│                      │  HP  │
│   Main Viewport      │ Face │
│    (206 × 224)       │ Map  │
│   Wireframe 3-D FPS  │      │
│                      │(50px)│
└──────────────────────┴──────┘
     256 × 224 pixels total
```

### Characters

| Character | Description |
|-----------|-------------|
| **Player** | FPS perspective (not visible). Shoots yellow bullets. Starts with **100 HP**. |
| **Player Bullet** | Yellow circle flying forward. |
| **Enemy** | Red stick-figure. Moves toward the player and fires red bullets. |
| **Enemy Bullet** | Red circle. Damages the player on contact. |

### Game Flow

```
Title Screen
    │ Press Space / A
    ▼
Game Screen  ──── enemy bullet hits player ──── HP reaches 0 ──── Game Over Screen
    │                                                                     │
    │ step on green stairs                                         Press Space / A
    ▼                                                                     │
Fade Out (0.25 s) → Next Floor Generated → Fade In (0.25 s)      Title Screen ◄─┘
```

### Maps

- **Random maze** generated fresh each floor using depth-first search.
- Walls are displayed as **wireframe** lines.
- **Enemies and bullets behind walls are hidden** (depth-buffer occlusion).
- **Green square on the floor** = stairs to the next floor.
- The maze algorithm guarantees the player can always reach the stairs.

### Status Panel (right side)

| Element | Description |
|---------|-------------|
| **FL** | Current floor number |
| **SC** | Current score (100 pts per kill) |
| **HP** | Player HP with colour bar (green → yellow → red) |
| **Face** | Character face frame — 5 expressions based on HP (placeholder frames; images TBD) |
| **Mini-map** | Top-down view: white = player, red = enemies, green = stairs, grey = walls |

### High Score

Shown on the **Game Over** screen. Persists for the current session.

---

## 🚀 Run Locally

### Requirements

```bash
pip install pyxel
```

### Launch

```bash
python main.py
```

### Resolution

256 × 224 pixels

---

## 📦 Package

The application is packaged as `retro_fps_game2.pyxapp` (included in the repository).

To re-package after modifying:

```bash
pyxel package . main.py
```

To generate a self-contained HTML file:

```bash
pyxel app2html retro_fps_game2.pyxapp
```

---

## 🏗 Project Structure

```
retro_fps_game2/
├── main.py                  # Game source code
├── retro_fps_game2.pyxapp   # Packaged application (for web launcher)
├── retro_fps_game2.html     # Self-contained HTML build
└── README.md
```

---

## 🛠 Class Design

```
BaseBullet          ← base class for all bullets
├── PlayerBullet    ← yellow bullet (player)
└── EnemyBullet     ← red bullet (enemy)

BaseEnemy           ← base class for all enemies (inheritable for expansion)
└── Enemy           ← standard red stick-figure enemy

Player              ← player (FPS, not rendered)
Raycaster           ← DDA wireframe 3-D renderer
App                 ← main application / state machine
```

---

## License

[MIT](LICENSE)
