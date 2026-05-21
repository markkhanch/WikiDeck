"""Button animation state management for smooth scale transitions."""

from ui.effects import ease_out_cubic


class ButtonAnimationState:
    """Tracks smooth scale animation for a button."""

    ANIMATION_DURATION = 0.4  # 400ms

    def __init__(self) -> None:
        self.current_scale = 1.0
        self.target_scale = 1.0
        self.time_elapsed = 0.0
        self.hovered = False

    def set_hovered(self, hovered: bool) -> None:
        """Update hover state and reset animation timer."""
        self.hovered = hovered
        self.target_scale = 1.08 if hovered else 1.0
        self.time_elapsed = 0.0

    def update(self, dt: float) -> None:
        """Update animation state. dt in seconds."""
        if self.time_elapsed >= self.ANIMATION_DURATION:
            self.current_scale = self.target_scale
            return

        self.time_elapsed += dt
        progress = min(1.0, self.time_elapsed / self.ANIMATION_DURATION)
        eased = ease_out_cubic(progress)
        self.current_scale = 1.0 + (self.target_scale - 1.0) * eased

    def get_scale(self) -> float:
        """Get current scale value."""
        return self.current_scale
