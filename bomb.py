import os
import random
import sys
import tkinter as tk
import urllib.request
import winsound
from ctypes import windll


CS_START_SOUND_URLS = [
    "https://www.myinstants.com/media/sounds/cs-1-6-lock-n-load.mp3",
    "https://www.myinstants.com/media/sounds/go-go-go-cs-1-6_nNVZZA6.mp3",
    "https://www.myinstants.com/media/sounds/moveout.mp3",
]
END_SOUND_URL = "https://www.myinstants.com/media/sounds/ma-ka-bhosda-aag.mp3"


def play_mp3_windows(file_path: str) -> bool:
    # Use WinMM MCI so we can play MP3 without third-party packages.
    alias = "bombsound"
    windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
    open_cmd = f'open "{file_path}" type mpegvideo alias {alias}'
    play_cmd = f"play {alias}"
    open_result = windll.winmm.mciSendStringW(open_cmd, None, 0, None)
    if open_result != 0:
        return False
    play_result = windll.winmm.mciSendStringW(play_cmd, None, 0, None)
    return play_result == 0


def ensure_cs_sounds(base_dir: str) -> list[str]:
    sounds_dir = os.path.join(base_dir, "cs_sounds")
    os.makedirs(sounds_dir, exist_ok=True)
    local_paths: list[str] = []

    for idx, url in enumerate(CS_START_SOUND_URLS, start=1):
        filename = f"start_{idx}.mp3"
        target = os.path.join(sounds_dir, filename)
        if not os.path.exists(target):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://www.myinstants.com/",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    with open(target, "wb") as out:
                        out.write(response.read())
            except Exception:
                continue
        local_paths.append(target)

    return local_paths


def ensure_end_sound(base_dir: str) -> str | None:
    sounds_dir = os.path.join(base_dir, "cs_sounds")
    os.makedirs(sounds_dir, exist_ok=True)
    target = os.path.join(sounds_dir, "end_sound.mp3")
    if os.path.exists(target):
        return target

    try:
        req = urllib.request.Request(
            END_SOUND_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.myinstants.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            with open(target, "wb") as out:
                out.write(response.read())
        return target
    except Exception:
        return None


class DraggableImage:
    def __init__(
        self,
        image_path: str,
        total_seconds: int,
        sound_files: list[str],
        end_sound_file: str | None,
    ) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        # Make the window background fully transparent on Windows.
        # Use a dark key color to avoid green halos on anti-aliased edges.
        transparent_key = "#010101"
        self.root.configure(bg=transparent_key)
        self.root.wm_attributes("-transparentcolor", transparent_key)

        self._drag_start_x = 0
        self._drag_start_y = 0
        self._timer_job = None
        self._running = False
        self.total_seconds = max(0, int(total_seconds))
        self.remaining_seconds = self.total_seconds
        self.sound_files = sound_files
        self.end_sound_file = end_sound_file
        self._exploded = False

        self.base_image = tk.PhotoImage(file=image_path)
        # Scale to ~80% size so it is slightly smaller.
        self.image = self.base_image.zoom(4, 4).subsample(5, 5)
        self.canvas = tk.Canvas(
            self.root,
            width=self.image.width(),
            height=self.image.height(),
            bd=0,
            highlightthickness=0,
            bg=transparent_key,
        )
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.image, anchor="nw")

        # Position the timer display over the clock area in the bomb image.
        center_x = (self.image.width() // 2) - 8
        # Tuned to sit centered inside the counter panel.
        center_y = int(self.image.height() * 0.515)
        timer_font = ("Consolas", 18, "bold")
        self.timer_glow_layers: list[int] = []
        # Outer/inner glow passes to fake emissive neon text.
        for color, offsets in (
            ("#2a0000", [(-3, 0), (3, 0), (0, -3), (0, 3)]),
            ("#5a0d0d", [(-2, -2), (2, -2), (-2, 2), (2, 2)]),
            ("#9e1e1e", [(-1, 0), (1, 0), (0, -1), (0, 1)]),
        ):
            for dx, dy in offsets:
                layer = self.canvas.create_text(
                    center_x + dx,
                    center_y + dy,
                    text="00:00:00",
                    fill=color,
                    font=timer_font,
                    anchor="center",
                )
                self.timer_glow_layers.append(layer)

        self.timer_text = self.canvas.create_text(
            center_x,
            center_y,
            text="00:00:00",
            fill="#ff5a4c",
            font=timer_font,
            anchor="center",
        )
        self.explosion_layers: list[int] = []

        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        # Quick exit options
        self.root.bind("<Escape>", lambda _e: self._close())
        self.root.bind("<Button-3>", lambda _e: self._close_all())
        # Space pauses/resumes, R resets to original value.
        self.root.bind("<space>", lambda _e: self._toggle_start())
        self.root.bind("r", lambda _e: self._reset())

        self.root.geometry("+200+120")
        self._update_timer_text()
        self._play_random_start_sound()
        self._toggle_start()

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event: tk.Event) -> None:
        new_x = self.root.winfo_x() + event.x - self._drag_start_x
        new_y = self.root.winfo_y() + event.y - self._drag_start_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def _toggle_start(self) -> None:
        if self._running:
            self._stop_timer()
            return

        if self.remaining_seconds <= 0:
            self._reset()
            if self.remaining_seconds <= 0:
                return

        self._running = True
        self._tick()

    def _tick(self) -> None:
        if not self._running:
            return

        self._update_timer_text()
        if self.remaining_seconds <= 0:
            self._stop_timer()
            self._trigger_explosion()
            return

        self.remaining_seconds -= 1
        self._timer_job = self.root.after(1000, self._tick)

    def _reset(self) -> None:
        self._stop_timer()
        self.remaining_seconds = self.total_seconds
        self._update_timer_text()

    def _play_random_start_sound(self) -> None:
        if not self.sound_files:
            return
        try:
            sound = random.choice(self.sound_files)
            played = play_mp3_windows(sound)
            if not played:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            # Fallback so user still gets an audible cue.
            winsound.MessageBeep(winsound.MB_ICONASTERISK)

    def _play_end_sound(self) -> None:
        if not self.end_sound_file:
            winsound.MessageBeep(winsound.MB_ICONHAND)
            return
        played = play_mp3_windows(self.end_sound_file)
        if not played:
            winsound.MessageBeep(winsound.MB_ICONHAND)

    def _trigger_explosion(self) -> None:
        if self._exploded:
            return
        self._exploded = True
        # Start the voice line at the same moment as the blast.
        self._play_end_sound()
        self._animate_blast(0)
        # Close after the blast + voice line.
        self.root.after(4200, self._close)

    def _animate_blast(self, frame: int) -> None:
        if frame >= 22 or not self.root.winfo_exists():
            for layer in self.explosion_layers:
                self.canvas.delete(layer)
            self.explosion_layers.clear()
            return

        for layer in self.explosion_layers:
            self.canvas.delete(layer)
        self.explosion_layers.clear()

        # Retro "DOOM-like" fire palette blast with expanding shock rings.
        colors = ["#260000", "#6a0000", "#b41300", "#ff4a00", "#ff9800", "#ffe27a"]
        base_radius = 18 + frame * 16
        cx = self.image.width() // 2
        cy = self.image.height() // 2

        # Core flash
        core = self.canvas.create_oval(
            cx - (base_radius // 3),
            cy - (base_radius // 3),
            cx + (base_radius // 3),
            cy + (base_radius // 3),
            fill=colors[min(frame // 4 + 2, len(colors) - 1)],
            outline="",
        )
        self.explosion_layers.append(core)

        # Concentric shock rings
        for i in range(4):
            ring_r = base_radius + i * 26
            ring = self.canvas.create_oval(
                cx - ring_r,
                cy - ring_r,
                cx + ring_r,
                cy + ring_r,
                outline=colors[max(0, len(colors) - 1 - i)],
                width=max(1, 6 - i),
            )
            self.explosion_layers.append(ring)

        # Cross-blast streaks
        streak_len = base_radius + 50
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            streak = self.canvas.create_line(
                cx - dx * streak_len,
                cy - dy * streak_len,
                cx + dx * streak_len,
                cy + dy * streak_len,
                fill="#ffd36b" if frame < 10 else "#ff5a00",
                width=2 if frame < 10 else 1,
            )
            self.explosion_layers.append(streak)

        # Brief red-hot full overlay pulse.
        if frame < 8:
            overlay = self.canvas.create_rectangle(
                0,
                0,
                self.image.width(),
                self.image.height(),
                fill="#a61200" if frame % 2 == 0 else "#ff4a00",
                stipple="gray25",
                outline="",
            )
            self.explosion_layers.append(overlay)

        for layer in self.timer_glow_layers:
            self.canvas.tag_raise(layer)
        self.canvas.tag_raise(self.timer_text)

        # Heavy quake that decays over frames.
        jitter = max(1, 16 - frame)
        base_x = self.root.winfo_x()
        base_y = self.root.winfo_y()
        self.root.geometry(
            f"+{base_x + random.randint(-jitter, jitter)}+{base_y + random.randint(-jitter, jitter)}"
        )
        self.root.after(50, lambda: self._animate_blast(frame + 1))

    def _stop_timer(self) -> None:
        self._running = False
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None

    def _update_timer_text(self) -> None:
        hours = self.remaining_seconds // 3600
        minutes = (self.remaining_seconds % 3600) // 60
        seconds = self.remaining_seconds % 60
        value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        for layer in self.timer_glow_layers:
            self.canvas.itemconfig(layer, text=value)
        self.canvas.itemconfig(self.timer_text, text=value)

    def _close(self) -> None:
        self._stop_timer()
        self.root.destroy()

    def _close_all(self) -> None:
        self._close()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(current_dir, "bomb.png")

    if not os.path.exists(image_path):
        raise FileNotFoundError("bomb.png not found in the same folder as bomb.py")

    hours = 0.0
    minutes = 1.0
    if len(sys.argv) > 2:
        try:
            hours = float(sys.argv[1])
            minutes = float(sys.argv[2])
        except ValueError:
            raise ValueError("Usage: python bomb.py [hours] [minutes]")
    elif len(sys.argv) > 1:
        # Backward-compatible: single arg is treated as minutes.
        try:
            minutes = float(sys.argv[1])
        except ValueError:
            raise ValueError("Usage: python bomb.py [hours] [minutes]")
    else:
        raw_hours = input("Enter countdown hours (default 0): ").strip()
        if raw_hours:
            try:
                hours = float(raw_hours)
            except ValueError:
                raise ValueError("Please enter a valid number of hours.")

        raw_minutes = input("Enter countdown minutes (default 1): ").strip()
        if raw_minutes:
            try:
                minutes = float(raw_minutes)
            except ValueError:
                raise ValueError("Please enter a valid number of minutes.")

    if hours < 0 or minutes < 0:
        raise ValueError("Hours and minutes must be non-negative.")

    total_seconds = int(hours * 3600 + minutes * 60)

    sound_files = ensure_cs_sounds(current_dir)
    end_sound_file = ensure_end_sound(current_dir)
    app = DraggableImage(image_path, total_seconds, sound_files, end_sound_file)
    app.run()


if __name__ == "__main__":
    main()
