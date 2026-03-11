"""Retro FPS Game — A retro-style first-person shooter using Pyxel.

Controls:
  Arrow keys / D-pad : Move forward/back (Up/Down), Turn (Left/Right)
  Space / A button   : Shoot
"""

import asyncio
import math
import random
from collections import deque

import pyxel

# ============================================================
# Screen / Layout Constants
# ============================================================
SCREEN_W = 256
SCREEN_H = 224
MAIN_W = 206        # Main 3-D viewport width (pixels)
STATUS_X = MAIN_W   # Status panel left edge
STATUS_W = 50       # Status panel width

# ============================================================
# Map Constants
# ============================================================
MAP_SIZE = 16       # Grid cells (MAP_SIZE × MAP_SIZE)

# ============================================================
# Camera / Movement
# ============================================================
FOV = math.pi / 3   # 60° field of view
HALF_FOV = FOV / 2
MOVE_SPEED = 0.05
ROT_SPEED = 0.05
WALL_MARGIN = 0.25  # Min distance to keep from walls

# ============================================================
# Game-play Constants
# ============================================================
PLAYER_MAX_HP = 100
PLAYER_SHOOT_CD = 15          # Frames between shots
PLAYER_BULLET_SPEED = 0.12
PLAYER_HIT_INVINCIBLE = 30    # Invincibility frames after damage

ENEMY_DEFAULT_HP = 30
ENEMY_SPEED = 0.015
ENEMY_SHOOT_INTERVAL = 120    # Frames between enemy shots
ENEMY_BULLET_SPEED = 0.07
ENEMY_STOP_DIST = 0.8         # Enemy keeps this distance from player

BULLET_HIT_RADIUS = 0.3
BULLET_DAMAGE_PLAYER = 10
BULLET_DAMAGE_ENEMY = 10

FADE_FRAMES = 15              # 0.25 s at 60 fps

# ============================================================
# Pyxel 16-colour Palette Indices
# ============================================================
COL_BLACK = 0
COL_NAVY = 1
COL_PURPLE = 2
COL_DARK_GREEN = 3
COL_BROWN = 4
COL_DARK_GRAY = 5
COL_GRAY = 6
COL_WHITE = 7
COL_RED = 8
COL_ORANGE = 9
COL_YELLOW = 10
COL_GREEN = 11
COL_BLUE = 12
COL_INDIGO = 13
COL_PINK = 14
COL_PEACH = 15

# ============================================================
# Game State IDs
# ============================================================
STATE_TITLE = 0
STATE_GAME = 1
STATE_GAMEOVER = 2
STATE_NEXT_FLOOR = 3


# ============================================================
# Map Generation
# ============================================================

def generate_map():
    """Return (grid, player_start, stairs_pos).

    Uses depth-first-search (recursive backtracking) to carve a perfect
    maze.  Stairs are placed at the cell farthest (BFS) from the player
    start, guaranteeing reachability.

    grid        : 2-D list — 0 = open, 1 = wall
    player_start: (x, y) world-space coordinates (centre of cell 1,1)
    stairs_pos  : (gx, gy) grid coordinates of the stairs cell
    """
    grid = [[1] * MAP_SIZE for _ in range(MAP_SIZE)]

    # --- Recursive DFS carve ---
    def carve(gx, gy):
        grid[gy][gx] = 0
        dirs = [(0, -2), (2, 0), (0, 2), (-2, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = gx + dx, gy + dy
            if 0 < nx < MAP_SIZE - 1 and 0 < ny < MAP_SIZE - 1 and grid[ny][nx] == 1:
                grid[gy + dy // 2][gx + dx // 2] = 0
                carve(nx, ny)

    carve(1, 1)

    # --- BFS to find farthest reachable cell ---
    visited = {(1, 1)}
    queue = deque([(1, 1, 0)])
    farthest, max_dist = (1, 1), 0
    while queue:
        cx, cy, d = queue.popleft()
        if d > max_dist:
            max_dist, farthest = d, (cx, cy)
        for ddx, ddy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = cx + ddx, cy + ddy
            if 0 <= nx < MAP_SIZE and 0 <= ny < MAP_SIZE and grid[ny][nx] == 0 \
                    and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny, d + 1))

    return grid, (1.5, 1.5), farthest


# ============================================================
# Bullet Classes
# ============================================================

class BaseBullet:
    """Base class for bullets — inherit to add new bullet types."""

    def __init__(self, x, y, dx, dy, speed, color):
        self.x = x
        self.y = y
        self.dx = dx          # Normalised direction X
        self.dy = dy          # Normalised direction Y
        self.speed = speed
        self.color = color
        self.active = True

    def update(self, grid):
        self.x += self.dx * self.speed
        self.y += self.dy * self.speed
        gx, gy = int(self.x), int(self.y)
        if not (0 <= gx < MAP_SIZE and 0 <= gy < MAP_SIZE) or grid[gy][gx] == 1:
            self.active = False


class PlayerBullet(BaseBullet):
    """Yellow bullet fired by the player."""

    def __init__(self, x, y, dx, dy):
        super().__init__(x, y, dx, dy, PLAYER_BULLET_SPEED, COL_YELLOW)


class EnemyBullet(BaseBullet):
    """Red bullet fired by enemies."""

    def __init__(self, x, y, dx, dy):
        super().__init__(x, y, dx, dy, ENEMY_BULLET_SPEED, COL_RED)


# ============================================================
# Enemy Classes
# ============================================================

class BaseEnemy:
    """Base class for enemies — inherit to add new enemy types."""

    def __init__(self, x, y, hp, speed, shoot_interval, color):
        self.x = x
        self.y = y
        self.hp = hp
        self.speed = speed
        self.shoot_interval = shoot_interval
        self.shoot_timer = random.randint(0, shoot_interval)
        self.color = color
        self.active = True

    # ---- public API ----

    def update(self, player, grid, enemy_bullets):
        if not self.active:
            return
        self._move_toward_player(player, grid)
        self._try_shoot(player, enemy_bullets)

    def take_damage(self, damage):
        self.hp -= damage
        if self.hp <= 0:
            self.active = False
            return True
        return False

    # ---- overridable internals ----

    def _move_toward_player(self, player, grid):
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist < ENEMY_STOP_DIST:
            return
        ndx = dx / dist * self.speed
        ndy = dy / dist * self.speed
        # Axis-separated slide movement for wall hugging
        nx, ny = self.x + ndx, self.y + ndy
        if 0 < nx < MAP_SIZE and grid[int(self.y)][int(nx)] == 0:
            self.x = nx
        if 0 < ny < MAP_SIZE and grid[int(ny)][int(self.x)] == 0:
            self.y = ny

    def _try_shoot(self, player, enemy_bullets):
        self.shoot_timer += 1
        if self.shoot_timer >= self.shoot_interval:
            self.shoot_timer = 0
            dx = player.x - self.x
            dy = player.y - self.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                enemy_bullets.append(self._create_bullet(dx / dist, dy / dist))

    def _create_bullet(self, dx, dy):
        return EnemyBullet(self.x, self.y, dx, dy)


class Enemy(BaseEnemy):
    """Standard red stick-figure enemy."""

    def __init__(self, x, y):
        super().__init__(x, y, ENEMY_DEFAULT_HP, ENEMY_SPEED,
                         ENEMY_SHOOT_INTERVAL, COL_RED)


# ============================================================
# Player
# ============================================================

class Player:
    """Player character — FPS perspective (not rendered)."""

    def __init__(self, x, y, angle=math.pi / 4):
        self.x = x
        self.y = y
        self.angle = angle
        self.hp = PLAYER_MAX_HP
        self.bullets = []
        self.shoot_cd = 0
        self.invincible = 0

    @property
    def dir_x(self):
        return math.cos(self.angle)

    @property
    def dir_y(self):
        return math.sin(self.angle)

    def update(self, grid):
        self._handle_movement(grid)
        self._handle_shoot()
        for b in self.bullets:
            b.update(grid)
        self.bullets = [b for b in self.bullets if b.active]
        if self.invincible > 0:
            self.invincible -= 1
        if self.shoot_cd > 0:
            self.shoot_cd -= 1

    def _handle_movement(self, grid):
        dx = dy = 0.0
        if pyxel.btn(pyxel.KEY_UP) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
            dx += self.dir_x * MOVE_SPEED
            dy += self.dir_y * MOVE_SPEED
        if pyxel.btn(pyxel.KEY_DOWN) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
            dx -= self.dir_x * MOVE_SPEED
            dy -= self.dir_y * MOVE_SPEED
        if pyxel.btn(pyxel.KEY_LEFT) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_LEFT):
            self.angle -= ROT_SPEED
        if pyxel.btn(pyxel.KEY_RIGHT) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT):
            self.angle += ROT_SPEED
        self.angle %= 2 * math.pi

        m = WALL_MARGIN
        if dx:
            nx = self.x + dx
            cx = int(nx + (m if dx > 0 else -m))
            if 0 < nx < MAP_SIZE and grid[int(self.y)][cx] == 0:
                self.x = nx
        if dy:
            ny = self.y + dy
            cy = int(ny + (m if dy > 0 else -m))
            if 0 < ny < MAP_SIZE and grid[cy][int(self.x)] == 0:
                self.y = ny

    def _handle_shoot(self):
        if (pyxel.btnp(pyxel.KEY_SPACE) or
                pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A)) and self.shoot_cd == 0:
            self.bullets.append(PlayerBullet(self.x, self.y, self.dir_x, self.dir_y))
            self.shoot_cd = PLAYER_SHOOT_CD

    def take_damage(self, amount):
        if self.invincible > 0:
            return False
        self.hp -= amount
        self.invincible = PLAYER_HIT_INVINCIBLE
        return self.hp <= 0


# ============================================================
# Raycaster / 3-D Renderer
# ============================================================

class Raycaster:
    """Wireframe 3-D raycasting renderer using the DDA algorithm."""

    def __init__(self):
        self.z_buf = [0.0] * MAIN_W   # per-column wall depth

    # ---- public entry point ----

    def render(self, grid, player, enemies, enemy_bullets, stairs_pos):
        rays = self._cast_rays(grid, player)
        self._draw_scene(rays)
        self._draw_floor_object(stairs_pos, player, COL_GREEN)
        # Collect visible sprites, sort far→near
        sprites = []
        for e in enemies:
            if e.active:
                sprites.append(e)
        for b in enemy_bullets:
            if b.active:
                sprites.append(b)
        for b in player.bullets:
            if b.active:
                sprites.append(b)
        sprites.sort(
            key=lambda s: -math.hypot(s.x - player.x, s.y - player.y))
        for s in sprites:
            self._draw_sprite(s, player)

    # ---- raycasting ----

    def _cam_plane(self, player):
        """Return (dir_x, dir_y, plane_x, plane_y) for the current frame."""
        dx = player.dir_x
        dy = player.dir_y
        t = math.tan(HALF_FOV)
        return dx, dy, -dy * t, dx * t

    def _cast_rays(self, grid, player):
        """DDA ray cast for every screen column. Fills self.z_buf."""
        dx, dy, px, py = self._cam_plane(player)
        rays = []
        for col in range(MAIN_W):
            cam_x = 2.0 * col / MAIN_W - 1.0   # –1 … +1
            rdx = dx + px * cam_x
            rdy = dy + py * cam_x

            mx = int(player.x)
            my = int(player.y)
            ddx = abs(1.0 / rdx) if rdx != 0 else 1e30
            ddy = abs(1.0 / rdy) if rdy != 0 else 1e30

            if rdx < 0:
                step_x, sdx = -1, (player.x - mx) * ddx
            else:
                step_x, sdx = 1, (mx + 1.0 - player.x) * ddx
            if rdy < 0:
                step_y, sdy = -1, (player.y - my) * ddy
            else:
                step_y, sdy = 1, (my + 1.0 - player.y) * ddy

            side = 0
            for _ in range(MAP_SIZE * 2):
                if sdx < sdy:
                    sdx += ddx; mx += step_x; side = 0
                else:
                    sdy += ddy; my += step_y; side = 1
                if not (0 <= mx < MAP_SIZE and 0 <= my < MAP_SIZE):
                    break
                if grid[my][mx] == 1:
                    break

            dist = max(0.001, (sdx - ddx) if side == 0 else (sdy - ddy))
            wh = min(SCREEN_H * 2, int(SCREEN_H / dist))
            wt = max(0, SCREEN_H // 2 - wh // 2)
            wb = min(SCREEN_H - 1, SCREEN_H // 2 + wh // 2)

            rays.append((dist, side, wt, wb))
            self.z_buf[col] = dist
        return rays

    # ---- scene drawing ----

    def _draw_scene(self, rays):
        """Ceiling (black) + floor (navy) + wireframe walls."""
        pyxel.rect(0, 0, MAIN_W, SCREEN_H // 2, COL_BLACK)
        pyxel.rect(0, SCREEN_H // 2, MAIN_W, SCREEN_H - SCREEN_H // 2, COL_NAVY)

        for col, (dist, side, wt, wb) in enumerate(rays):
            c = COL_WHITE if side == 0 else COL_GRAY
            pyxel.pset(col, wt, c)
            pyxel.pset(col, wb, c)
            # Vertical edge at depth transitions
            if col > 0:
                pd, ps, pwt, pwb = rays[col - 1]
                if abs(dist - pd) > 0.5 or ps != side:
                    yt = min(wt, pwt)
                    yb = max(wb, pwb)
                    pyxel.line(col, yt, col, yb, COL_WHITE)

    # ---- camera-space transform (shared by floor objects and sprites) ----

    def _world_to_cam(self, wx, wy, player):
        """Transform a world point to camera (cam_x, cam_z) coordinates."""
        dx = wx - player.x
        dy = wy - player.y
        dir_x, dir_y, plane_x, plane_y = self._cam_plane(player)
        inv = 1.0 / (plane_x * dir_y - dir_x * plane_y)
        cam_x = inv * (dir_y * dx - dir_x * dy)
        cam_z = inv * (-plane_y * dx + plane_x * dy)
        return cam_x, cam_z

    # ---- floor object (stairs) ----

    def _draw_floor_object(self, gpos, player, color):
        """Render a coloured square on the floor at grid cell gpos."""
        cx, cz = self._world_to_cam(gpos[0] + 0.5, gpos[1] + 0.5, player)
        if cz <= 0.1:
            return
        sx = int(MAIN_W / 2 * (1 + cx / cz))
        sy = int(SCREEN_H / 2 + SCREEN_H / (2 * cz))
        if not (0 <= sx < MAIN_W and SCREEN_H // 2 <= sy < SCREEN_H):
            return
        if cz >= self.z_buf[sx]:
            return
        sz = max(1, int(5 / cz))
        x1 = max(0, sx - sz)
        x2 = min(MAIN_W - 1, sx + sz)
        y1 = max(SCREEN_H // 2, sy - sz // 2)
        y2 = min(SCREEN_H - 1, sy + max(1, sz // 2))
        if x1 < x2 and y1 < y2:
            pyxel.rect(x1, y1, x2 - x1, y2 - y1, color)

    # ---- sprite rendering ----

    def _draw_sprite(self, entity, player):
        """Render an enemy (stick figure) or bullet (circle) in 3-D space."""
        cx, cz = self._world_to_cam(entity.x, entity.y, player)
        if cz <= 0.1:
            return
        sx = int(MAIN_W / 2 * (1 + cx / cz))

        if isinstance(entity, BaseBullet):
            r = max(1, int(3 / cz))
            cy = SCREEN_H // 2
            col = max(0, min(MAIN_W - 1, sx))
            if 0 <= sx < MAIN_W and cz < self.z_buf[col]:
                pyxel.circ(sx, cy, r, entity.color)
        else:
            h = max(6, int(SCREEN_H * 0.6 / cz))
            col = max(0, min(MAIN_W - 1, sx))
            if cz < self.z_buf[col]:
                cy = SCREEN_H // 2
                self._draw_stick_figure(sx, cy, h, entity.color)

    @staticmethod
    def _draw_stick_figure(cx, cy, h, color):
        """Draw a simple stick-figure centred at (cx, cy) with height h."""
        head_r = max(1, h // 8)
        head_cy = cy - h // 3
        pyxel.circ(cx, head_cy, head_r, color)              # head
        body_top = head_cy + head_r
        body_bot = cy + h // 6
        pyxel.line(cx, body_top, cx, body_bot, color)       # body
        arm_y = cy - h // 10
        arm_w = max(2, h // 5)
        pyxel.line(cx - arm_w, arm_y, cx + arm_w, arm_y, color)  # arms
        leg_bot = cy + h // 3
        leg_w = max(2, h // 6)
        pyxel.line(cx, body_bot, cx - leg_w, leg_bot, color)     # left leg
        pyxel.line(cx, body_bot, cx + leg_w, leg_bot, color)     # right leg


# ============================================================
# Main Application
# ============================================================

class App:
    """Top-level application — owns all game state."""

    def __init__(self):
        pyxel.init(SCREEN_W, SCREEN_H, title="Retro FPS", fps=60)
        self.high_score = 0
        self.new_high_score = False
        self.score = 0
        self.floor = 1
        # Game objects (initialised in _init_game)
        self.grid = None
        self.stairs_pos = None
        self.player = None
        self.enemies = []
        self.enemy_bullets = []
        self.raycaster = None
        # Fade state
        self.fade_dir = 0
        self.fade_timer = 0
        self.state = STATE_TITLE
        pyxel.run(self.update, self.draw)

    # ---- initialisation helpers ----

    def _init_game(self):
        self.grid, player_start, self.stairs_pos = generate_map()
        self.player = Player(player_start[0], player_start[1])
        self.enemies = []
        self.enemy_bullets = []
        self.raycaster = Raycaster()
        self._spawn_enemies()
        self.fade_dir = 0
        self.fade_timer = 0

    def _spawn_enemies(self):
        candidates = [
            (x + 0.5, y + 0.5)
            for y in range(MAP_SIZE) for x in range(MAP_SIZE)
            if self.grid[y][x] == 0
            and (x, y) != (1, 1)
            and (x, y) != self.stairs_pos
            and math.hypot(x + 0.5 - 1.5, y + 0.5 - 1.5) > 4
        ]
        random.shuffle(candidates)
        n = min(3 + self.floor, max(3, len(candidates)))
        for ex, ey in candidates[:n]:
            self.enemies.append(Enemy(ex, ey))

    # ================================================================
    # Update
    # ================================================================

    def update(self):
        if self.state == STATE_TITLE:
            self._update_title()
        elif self.state == STATE_GAME:
            self._update_game()
        elif self.state == STATE_GAMEOVER:
            self._update_gameover()
        elif self.state == STATE_NEXT_FLOOR:
            self._update_next_floor()

    def _update_title(self):
        if pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
            self.score = 0
            self.floor = 1
            self._init_game()
            self.state = STATE_GAME

    def _update_game(self):
        p = self.player
        p.update(self.grid)

        for e in self.enemies:
            e.update(p, self.grid, self.enemy_bullets)
        self.enemies = [e for e in self.enemies if e.active]

        for b in self.enemy_bullets:
            b.update(self.grid)
        self.enemy_bullets = [b for b in self.enemy_bullets if b.active]

        # Player bullets vs enemies
        for pb in list(p.bullets):
            if not pb.active:
                continue
            for e in self.enemies:
                if not e.active:
                    continue
                if math.hypot(pb.x - e.x, pb.y - e.y) < BULLET_HIT_RADIUS:
                    pb.active = False
                    if e.take_damage(BULLET_DAMAGE_ENEMY):
                        self.score += 100
                    break

        # Enemy bullets vs player
        for eb in list(self.enemy_bullets):
            if not eb.active:
                continue
            if math.hypot(eb.x - p.x, eb.y - p.y) < BULLET_HIT_RADIUS:
                eb.active = False
                if p.take_damage(BULLET_DAMAGE_PLAYER):
                    self._trigger_gameover()
                    return

        # Check stairs
        if (int(p.x), int(p.y)) == self.stairs_pos:
            self.state = STATE_NEXT_FLOOR
            self.fade_dir = -1   # fade out
            self.fade_timer = 0

    def _trigger_gameover(self):
        if self.score > self.high_score:
            self.high_score = self.score
            self.new_high_score = True
        else:
            self.new_high_score = False
        self.state = STATE_GAMEOVER

    def _update_gameover(self):
        if pyxel.btnp(pyxel.KEY_SPACE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
            self.state = STATE_TITLE

    def _update_next_floor(self):
        self.fade_timer += 1
        if self.fade_dir == -1:                     # fading out
            if self.fade_timer >= FADE_FRAMES:
                self.floor += 1
                self._init_game()
                self.fade_dir = 1                   # start fade in
                self.fade_timer = 0
                self.state = STATE_NEXT_FLOOR       # stay in transition
        elif self.fade_dir == 1:                    # fading in
            if self.fade_timer >= FADE_FRAMES:
                self.state = STATE_GAME

    # ================================================================
    # Draw
    # ================================================================

    def draw(self):
        pyxel.cls(COL_BLACK)
        if self.state == STATE_TITLE:
            self._draw_title()
        elif self.state == STATE_GAME:
            self._draw_game()
        elif self.state == STATE_GAMEOVER:
            self._draw_gameover()
        elif self.state == STATE_NEXT_FLOOR:
            self._draw_next_floor()

    # ---- Title screen ----

    def _draw_title(self):
        cx = SCREEN_W // 2
        y = SCREEN_H // 4

        title = "RETRO FPS"
        pyxel.text(cx - len(title) * 2, y, title, COL_WHITE)

        sub = "A RETRO FIRST-PERSON SHOOTER"
        pyxel.text(cx - len(sub) * 2, y + 14, sub, COL_GRAY)

        start = "PRESS SPACE OR A  TO START"
        t = pyxel.frame_count // 30 % 2
        pyxel.text(cx - len(start) * 2, y + 60, start, COL_WHITE if t else COL_DARK_GRAY)

        if self.high_score > 0:
            hs = f"HIGH SCORE: {self.high_score}"
            pyxel.text(cx - len(hs) * 2, y + 80, hs, COL_YELLOW)

        # Controls hint
        hint_lines = [
            "  UP / DOWN  : MOVE",
            "LEFT / RIGHT : TURN",
            "       SPACE : SHOOT",
        ]
        for i, line in enumerate(hint_lines):
            pyxel.text(cx - len(line) * 2, y + 108 + i * 9, line, COL_DARK_GRAY)

    # ---- Game screen ----

    def _draw_game(self):
        # 3-D viewport
        self.raycaster.render(
            self.grid, self.player,
            self.enemies, self.enemy_bullets, self.stairs_pos)
        # Status panel
        self._draw_status()

    # ---- Game-Over screen ----

    def _draw_gameover(self):
        cx = SCREEN_W // 2
        y = SCREEN_H // 4

        msg = "GAME OVER"
        pyxel.text(cx - len(msg) * 2, y, msg, COL_RED)

        sc = f"SCORE: {self.score}"
        pyxel.text(cx - len(sc) * 2, y + 20, sc, COL_WHITE)

        if self.new_high_score:
            hs = "NEW HIGH SCORE!"
            pyxel.text(cx - len(hs) * 2, y + 34, hs, COL_YELLOW)

        bst = f"BEST : {self.high_score}"
        pyxel.text(cx - len(bst) * 2, y + 48, bst, COL_YELLOW)

        ret = "PRESS SPACE OR A  TO RETURN"
        t = pyxel.frame_count // 30 % 2
        pyxel.text(cx - len(ret) * 2, y + 74, ret, COL_WHITE if t else COL_DARK_GRAY)

    # ---- Floor transition ----

    def _draw_next_floor(self):
        self._draw_game()
        # Compute fade alpha (0.0 = transparent … 1.0 = black)
        alpha = self.fade_timer / FADE_FRAMES
        if self.fade_dir == 1:
            alpha = 1.0 - alpha
        alpha = max(0.0, min(1.0, alpha))
        if alpha > 0.0:
            pyxel.dither(alpha)
            pyxel.rect(0, 0, SCREEN_W, SCREEN_H, COL_BLACK)
            pyxel.dither(1.0)

    # ---- Status panel ----

    def _draw_status(self):
        # Background + dividing line
        pyxel.rect(STATUS_X, 0, STATUS_W, SCREEN_H, COL_DARK_GRAY)
        pyxel.line(STATUS_X, 0, STATUS_X, SCREEN_H - 1, COL_WHITE)

        sx = STATUS_X + 2

        # Floor & score
        pyxel.text(sx, 2, f"FL:{self.floor}", COL_WHITE)
        sc_str = f"SC:{self.score}"
        pyxel.text(sx, 10, sc_str, COL_YELLOW)

        # HP label + bar
        pyxel.text(sx, 22, f"HP:{self.player.hp}", COL_WHITE)
        bar_w = STATUS_W - 6
        filled = max(0, int(bar_w * self.player.hp / PLAYER_MAX_HP))
        bar_col = (COL_GREEN if self.player.hp > 60
                   else COL_YELLOW if self.player.hp > 30 else COL_RED)
        pyxel.rect(sx + 1, 30, bar_w, 5, COL_BLACK)
        if filled > 0:
            pyxel.rect(sx + 1, 30, filled, 5, bar_col)
        pyxel.rectb(sx + 1, 30, bar_w, 5, COL_WHITE)

        # Character face (frame + expression stage)
        self._draw_face(sx, 40)

        # Mini-map
        self._draw_minimap(sx, 110)

    def _draw_face(self, sx, sy):
        """Draw a framed character face.  5 HP stages (frame only for now)."""
        fw, fh = 42, 42
        pyxel.rectb(sx, sy, fw, fh, COL_WHITE)

        # Determine stage 0–4 (4 = healthy, 0 = critical)
        hp_pct = max(0.0, self.player.hp / PLAYER_MAX_HP)
        stage = min(4, int(hp_pct * 5))

        # Simple ASCII expressions as placeholder for real images
        expressions = [">_<", "-_-", "o_o", "^_^", "^v^"]
        colors = [COL_RED, COL_ORANGE, COL_YELLOW, COL_GREEN, COL_WHITE]
        expr = expressions[stage]
        col = colors[stage]
        ex = sx + fw // 2 - len(expr) * 2
        ey = sy + fh // 2 - 3
        pyxel.text(ex, ey, expr, col)

        # Small HP stage label at bottom of face frame
        lbl = f"ST{stage}"
        pyxel.text(sx + fw // 2 - len(lbl) * 2, sy + fh - 9, lbl, COL_GRAY)

    def _draw_minimap(self, sx, sy):
        """Draw an overhead mini-map inside the status panel."""
        avail_w = STATUS_W - 4
        avail_h = SCREEN_H - sy - 4
        cell = max(1, min(avail_w // MAP_SIZE, avail_h // MAP_SIZE))
        mw = cell * MAP_SIZE
        mh = cell * MAP_SIZE

        for gy in range(MAP_SIZE):
            for gx in range(MAP_SIZE):
                px = sx + gx * cell
                py = sy + gy * cell
                if px + cell > STATUS_X + STATUS_W:
                    continue
                col = COL_GRAY if self.grid[gy][gx] == 1 else COL_BLACK
                pyxel.rect(px, py, cell, cell, col)

        # Stairs
        stx = sx + self.stairs_pos[0] * cell
        sty = sy + self.stairs_pos[1] * cell
        pyxel.rect(stx, sty, max(1, cell), max(1, cell), COL_GREEN)

        # Enemies
        for e in self.enemies:
            ex = sx + int(e.x) * cell
            ey = sy + int(e.y) * cell
            pyxel.rect(ex, ey, max(1, cell), max(1, cell), COL_RED)

        # Player (white dot + direction tick)
        px = sx + int(self.player.x) * cell
        py = sy + int(self.player.y) * cell
        pyxel.rect(px, py, max(1, cell), max(1, cell), COL_WHITE)
        tx = px + cell // 2 + int(self.player.dir_x * cell)
        ty = py + cell // 2 + int(self.player.dir_y * cell)
        pyxel.line(px + cell // 2, py + cell // 2, tx, ty, COL_YELLOW)


# ============================================================
# Entry Point
# ============================================================


async def main():
    App()


asyncio.run(main())
