class Particle:
    def __init__(self, x, y, preset, cx=None, cy=None):
        import math
        import random

        self.x = x
        self.y = y
        self.life = 1.0
        self.cx = cx or x
        self.cy = cy or y
        self.preset = preset
        self.rot = random.uniform(0, math.pi * 2)
        self.rotv = (random.random() - 0.5) * 0.3

        if preset == "spark":
            a = random.uniform(0, math.pi * 2)
            s = random.uniform(4, 12)
            self.vx = math.cos(a) * s
            self.vy = math.sin(a) * s
            r = random.randint(200, 255)
            g = random.randint(160, 220)
            self.color = (r, g, 0)
            self.gravity = 0.1
            self.drag = 0.92
            self.decay = 0.03 + random.random() * 0.03
            self.radius = 2
            self.shape = "line"

        elif preset == "fountain":
            a = random.uniform(-math.pi * 0.9, -math.pi * 0.1)
            s = random.uniform(2, 6)
            self.vx = math.cos(a) * s
            self.vy = math.sin(a) * s
            self.color = (random.randint(140, 200), 0, 0)
            self.gravity = 0.15
            self.drag = 0.97
            self.decay = 0.012 + random.random() * 0.015
            self.radius = 3 + random.random() * 4
            self.shape = "circle"

        elif preset == "smoke":
            self.vx = random.uniform(-0.5, 0.5)
            self.vy = random.uniform(-1.5, -0.3)
            v = random.randint(80, 140)
            self.color = (v // 2, 0, v)
            self.gravity = 0
            self.drag = 0.99
            self.decay = 0.006 + random.random() * 0.008
            self.radius = 8 + random.random() * 8
            self.max_radius = 40
            self.grow = True
            self.shape = "smoke"

        elif preset == "ring":
            i = random.randint(0, 47)
            a = (i / 48) * math.pi * 2
            s = random.uniform(3, 5)
            self.vx = math.cos(a) * s
            self.vy = math.sin(a) * s
            self.color = (60, random.randint(120, 200), 220)
            self.gravity = 0
            self.drag = 0.96
            self.decay = 0.018
            self.radius = 3
            self.shape = "circle"

        elif preset == "orbit":
            self.orbit = True
            self.angle = random.uniform(0, math.pi * 2)
            self.orbit_radius = 40 + random.random() * 30
            self.orbit_speed = 0.08 + random.random() * 0.06
            self.color = (
                random.randint(80, 140),
                random.randint(80, 140),
                random.randint(80, 140),
            )
            self.decay = 0.006
            self.radius = 4 + random.random() * 4
            self.shape = "circle"
            self.vx = 0
            self.vy = 0
            self.gravity = 0
            self.drag = 1.0

        elif preset == "bubble":
            self.vx = random.uniform(-1, 1)
            self.vy = random.uniform(-2, -0.5)
            self.color = (0, random.randint(180, 255), random.randint(60, 120))
            self.gravity = -0.02
            self.drag = 0.99
            self.decay = 0.008 + random.random() * 0.01
            self.radius = 4 + random.random() * 12
            self.shape = "bubble"

        elif preset == "beam":
            self.vx = 0
            self.vy = 0
            self.color = (255, 255, 220)
            self.gravity = 0
            self.drag = 1.0
            self.decay = 0.025
            self.radius = 2
            self.max_radius = 50 + random.random() * 30
            self.grow = True
            self.shape = "smoke"

        elif preset == "confetti":
            cols = [(255, 80, 80), (80, 180, 255), (80, 255, 120), (255, 220, 0), (200, 80, 255)]
            self.color = random.choice(cols)
            self.vx = random.uniform(-4, 4)
            self.vy = random.uniform(-6, -1)
            self.gravity = 0.15
            self.drag = 0.99
            self.decay = 0.008
            self.radius = 0
            self.w = 6 + random.random() * 8
            self.h = 2 + random.random() * 3
            self.shape = "confetti"

        elif preset == "vortex":
            a = random.uniform(0, math.pi * 2)
            dist = random.uniform(20, 100)
            self.x = self.cx + math.cos(a) * dist
            self.y = self.cy + math.sin(a) * dist
            tang = a + math.pi / 2
            self.vx = math.cos(tang) * random.uniform(2, 4) - math.cos(a) * 1.5
            self.vy = math.sin(tang) * random.uniform(2, 4) - math.sin(a) * 1.5
            self.color = (random.randint(100, 180), 0, random.randint(180, 255))
            self.gravity = 0
            self.drag = 0.96
            self.decay = 0.012
            self.radius = 2 + random.random() * 4
            self.shape = "circle"

        elif preset == "trail":
            a = random.uniform(0, math.pi * 2)
            self.vx = math.cos(a) * random.uniform(1, 3)
            self.vy = math.sin(a) * random.uniform(1, 3)
            self.color = (255, random.randint(180, 255), 0)
            self.gravity = -0.05
            self.drag = 0.97
            self.decay = 0.015 + random.random() * 0.015
            self.radius = 3 + random.random() * 4
            self.shape = "circle"

        elif preset == "shatter":
            a = random.uniform(0, math.pi * 2)
            s = random.uniform(3, 10)
            self.vx = math.cos(a) * s
            self.vy = math.sin(a) * s
            self.color = (random.randint(100, 180), random.randint(180, 255), 255)
            self.gravity = 0.12
            self.drag = 0.95
            self.decay = 0.018
            self.radius = 0
            self.w = 5 + random.random() * 10
            self.h = 1 + random.random() * 3
            self.shape = "confetti"

        else:
            a = random.uniform(0, math.pi * 2)
            s = random.uniform(2, 5)
            self.vx = math.cos(a) * s
            self.vy = math.sin(a) * s
            self.color = (200, 200, 200)
            self.gravity = 0.05
            self.drag = 0.97
            self.decay = 0.02
            self.radius = 3
            self.shape = "circle"

        if not hasattr(self, "grow"):
            self.grow = False
        if not hasattr(self, "max_radius"):
            self.max_radius = 30
        if not hasattr(self, "orbit"):
            self.orbit = False

    def update(self):
        import math

        if self.orbit:
            self.angle += self.orbit_speed
            self.orbit_radius *= 0.992
            self.x = self.cx + math.cos(self.angle) * self.orbit_radius
            self.y = self.cy + math.sin(self.angle) * self.orbit_radius
        else:
            self.vx *= self.drag
            self.vy *= self.drag
            self.x += self.vx
            self.y += self.vy
            self.vy += self.gravity
        if self.grow:
            self.radius = min(self.radius + 0.5, self.max_radius)
        if self.shape == "confetti":
            self.rot += self.rotv
        self.life -= self.decay

    def draw(self, surface):
        import math
        import pygame

        if self.life <= 0:
            return
        cr, cg, cb = self.color
        alpha = max(0, min(255, int(self.life * 255)))

        if self.shape == "circle":
            r = max(1, int(self.radius * self.life))
            c = (int(cr * self.life), int(cg * self.life), int(cb * self.life))
            pygame.draw.circle(surface, c, (int(self.x), int(self.y)), r)

        elif self.shape == "smoke":
            r = max(1, int(self.radius))
            a = max(0, min(255, int(self.life * 80)))
            pygame.draw.circle(surface, (cr, cg, cb, a), (int(self.x), int(self.y)), r)

        elif self.shape == "line":
            end_x = int(self.x - self.vx * 3)
            end_y = int(self.y - self.vy * 3)
            c = (int(cr * self.life), int(cg * self.life), int(cb * self.life))
            pygame.draw.line(surface, c, (int(self.x), int(self.y)), (end_x, end_y), 2)

        elif self.shape == "confetti":
            hw = self.w * 0.5
            hh = self.h * 0.5
            cos_r = math.cos(self.rot)
            sin_r = math.sin(self.rot)
            points = []
            for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
                px = self.x + dx * cos_r - dy * sin_r
                py = self.y + dx * sin_r + dy * cos_r
                points.append((int(px), int(py)))
            pygame.draw.polygon(surface, (cr, cg, cb, alpha), points)

        elif self.shape == "bubble":
            r = max(1, int(self.radius))
            pygame.draw.circle(surface, (cr, cg, cb, alpha), (int(self.x), int(self.y)), r, 2)

    def is_dead(self):
        return self.life <= 0


class Shockwave:
    def __init__(self, x, y, color=(255, 255, 255)):
        self.x = x
        self.y = y
        self.r = 5
        self.life = 1.0
        self.color = color
        self.speed = 6

    def update(self):
        self.r += self.speed
        self.speed *= 0.95
        self.life -= 0.025

    def draw(self, surface):
        import pygame

        if self.life <= 0:
            return
        r = max(1, int(self.r))
        cr, cg, cb = self.color
        a = max(0, min(255, int(self.life * 200)))
        pygame.draw.circle(surface, (cr, cg, cb, a), (int(self.x), int(self.y)), r, 2)

    def is_dead(self):
        return self.life <= 0


class Lightning:
    def __init__(self, x1, y1, x2, y2, depth=5):
        import random

        self.segs = []
        self.life = 1.0

        def seg(ax, ay, bx, by, d):
            if d <= 0:
                self.segs.append((ax, ay, bx, by))
                return
            mx = (ax + bx) / 2 + (by - ay) * (random.random() - 0.5) * 0.5
            my = (ay + by) / 2 + (ax - bx) * (random.random() - 0.5) * 0.5
            seg(ax, ay, mx, my, d - 1)
            seg(mx, my, bx, by, d - 1)

        seg(x1, y1, x2, y2, depth)

    def update(self):
        self.life -= 0.08

    def draw(self, surface):
        import pygame

        if self.life <= 0:
            return
        a = max(0, min(255, int(self.life * 200)))
        outer = (180, 220, 255, a)
        inner = (255, 255, 255, int(a * 0.5))
        outer_w = max(1, int(self.life * 2))
        for ax, ay, bx, by in self.segs:
            pygame.draw.line(
                surface,
                outer,
                (int(ax), int(ay)),
                (int(bx), int(by)),
                outer_w,
            )
            pygame.draw.line(
                surface,
                inner,
                (int(ax), int(ay)),
                (int(bx), int(by)),
                1,
            )

    def is_dead(self):
        return self.life <= 0


MAX_PARTICLES = 300


class ParticleSystem:
    def __init__(self):
        self.particles = []
        self.shockwaves = []
        self.lightnings = []

    def emit(self, x, y, preset, count=None, cx=None, cy=None):
        defaults = {
            "spark": 20,
            "fountain": 30,
            "smoke": 8,
            "ring": 30,
            "orbit": 8,
            "bubble": 20,
            "beam": 10,
            "confetti": 40,
            "vortex": 15,
            "trail": 20,
            "shatter": 25,
        }
        n = count or defaults.get(preset, 20)
        for _ in range(n):
            self.particles.append(Particle(x, y, preset, cx=cx or x, cy=cy or y))
        if len(self.particles) > MAX_PARTICLES:
            self.particles = self.particles[-MAX_PARTICLES:]

    def shockwave(self, x, y, color=(255, 255, 255)):
        self.shockwaves.append(Shockwave(x, y, color))

    def lightning(self, x1, y1, x2, y2):
        self.lightnings.append(Lightning(x1, y1, x2, y2))

    def trigger(self, event_type, x, y, target_x=None, target_y=None):
        """Call this from match screen when a game event happens."""
        cx, cy = x, y
        if event_type == "DEPLOY":
            self.emit(cx, cy, "confetti", 35)
        elif event_type == "DAMAGE":
            self.emit(cx, cy, "spark", 25)
        elif event_type == "BLEEDING":
            self.emit(cx, cy, "fountain", 20)
        elif event_type in ("DESTROY", "BANISH"):
            self.emit(cx, cy, "shatter", 30)
            self.shockwave(cx, cy, (180, 230, 255))
        elif event_type in ("VITALITY", "HEAL"):
            self.emit(cx, cy, "bubble", 20)
        elif event_type == "SHIELD":
            self.emit(cx, cy, "ring", 36)
        elif event_type == "POISON":
            self.emit(cx, cy, "smoke", 8)
        elif event_type == "LOCK":
            self.emit(cx, cy, "orbit", 8, cx=cx, cy=cy)
        elif event_type in ("DUEL", "CLASH"):
            if target_x and target_y:
                self.lightning(cx, cy, target_x, target_y)
                self.lightning(cx, cy, target_x, target_y)
            self.shockwave(cx, cy, (255, 100, 0))
        elif event_type == "DEATHWISH":
            self.shockwave(cx, cy, (150, 150, 150))
            self.emit(cx, cy, "smoke", 8)
        elif event_type == "GOLD":
            self.emit(cx, cy, "trail", 20)
        elif event_type == "DRAW":
            self.emit(cx, cy, "vortex", 15, cx=cx, cy=cy)
        elif event_type == "TIMER":
            self.emit(cx, cy, "orbit", 8, cx=cx, cy=cy)
        elif event_type == "REVIVE":
            self.emit(cx, cy, "beam", 15)
            self.emit(cx, cy, "ring", 36)

    def update(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if not p.is_dead()]
        for s in self.shockwaves:
            s.update()
        self.shockwaves = [s for s in self.shockwaves if not s.is_dead()]
        for l in self.lightnings:
            l.update()
        self.lightnings = [l for l in self.lightnings if not l.is_dead()]

    def draw(self, surface):
        for s in self.shockwaves:
            s.draw(surface)
        for l in self.lightnings:
            l.draw(surface)
        for p in self.particles:
            p.draw(surface)


particle_system = ParticleSystem()
