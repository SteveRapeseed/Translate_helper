import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _resolve_runtime_paths() -> tuple[Path, Path, Path, Path]:
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS"))
        install = Path(sys.executable).resolve().parent
        return bundle / "desktop", bundle, bundle / "shared", install
    desktop = Path(__file__).resolve().parent
    root = desktop.parent
    return desktop, root, root / "shared", root


_DESKTOP_DIR, _REPO_ROOT, _SHARED_DIR, _INSTALL_ROOT = _resolve_runtime_paths()
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import requests
import tkinter as tk
import tkinter.font as tkfont

from translation_core import (
    TARGET_LANGUAGE,
    TranslationResult,
    build_system_prompt,
    build_translation_result,
    detect_source_language,
    format_route_label,
    parse_source_langs,
    should_skip_translation,
)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_env_file(path: str | None = None) -> None:
    if path is None:
        candidates = [
            _INSTALL_ROOT / ".env",
            Path.home() / ".config" / "translate-helper" / ".env",
            _REPO_ROOT / ".config" / "translate-helper" / ".env",
            _DESKTOP_DIR / ".env",
            _REPO_ROOT / ".env",
        ]
        path_obj = next((item for item in candidates if item.exists()), None)
        if path_obj is None:
            return
        path = str(path_obj)

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue

            value = value.strip()
            if value and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]

            current = os.getenv(key)
            if current is None or not current.strip():
                os.environ[key] = value


@dataclass(frozen=True)
class AppConfig:
    source_lang: str
    target_lang: str
    supported_source_langs: tuple[str, ...]
    debounce_ms: int
    clipboard_poll_ms: int
    max_text_length: int
    min_text_length: int
    cache_size: int
    margin_px: int
    repeat_cooldown_ms: int
    inflight_retry_ms: int
    log_events: bool
    hf_token: str
    hf_base_url: str
    hf_model_id: str
    hf_timeout_seconds: int
    hf_max_new_tokens: int
    hf_temperature: float
    hf_use_env_proxy: bool
    hf_retry_count: int
    hf_retry_backoff_seconds: float
    panel_auto_hide_ms: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        model = os.getenv("HF_LLM_MODEL", "").strip() or os.getenv("HF_MODEL_ID", "").strip()
        if not model:
            model = "Qwen/Qwen2.5-7B-Instruct"

        base_url = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1").strip().rstrip("/")
        if not base_url:
            base_url = "https://router.huggingface.co/v1"

        return cls(
            source_lang=os.getenv("SOURCE_LANG", "auto"),
            target_lang=os.getenv("TARGET_LANG", TARGET_LANGUAGE.code),
            supported_source_langs=parse_source_langs(os.getenv("SUPPORTED_SOURCE_LANGS")),
            debounce_ms=env_int("DEBOUNCE_MS", 350),
            clipboard_poll_ms=env_int("CLIPBOARD_POLL_MS", 500),
            max_text_length=env_int("MAX_TEXT_LENGTH", 1000),
            min_text_length=env_int("MIN_TEXT_LENGTH", 1),
            cache_size=env_int("CACHE_SIZE", 200),
            margin_px=env_int("WINDOW_MARGIN_PX", 16),
            repeat_cooldown_ms=env_int("REPEAT_COOLDOWN_MS", 0),
            inflight_retry_ms=env_int("INFLIGHT_RETRY_MS", 10000),
            log_events=env_bool("LOG_EVENTS", True),
            hf_token=os.getenv("HF_TOKEN", "").strip(),
            hf_base_url=base_url,
            hf_model_id=model,
            hf_timeout_seconds=env_int("HF_TIMEOUT_SECONDS", 90),
            hf_max_new_tokens=env_int("HF_MAX_NEW_TOKENS", 256),
            hf_temperature=env_float("HF_TEMPERATURE", 0.1),
            hf_use_env_proxy=env_bool("HF_USE_ENV_PROXY", False),
            hf_retry_count=env_int("HF_RETRY_COUNT", 3),
            hf_retry_backoff_seconds=env_float("HF_RETRY_BACKOFF_SECONDS", 1.2),
            panel_auto_hide_ms=env_int("PANEL_AUTO_HIDE_MS", 15000),
        )


class LruCache:
    def __init__(self, capacity: int):
        self.capacity = max(1, capacity)
        self._data: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)


class TranslatorService:
    RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

    def __init__(self, config: AppConfig):
        self.config = config
        self.http = requests.Session()
        self.http.trust_env = config.hf_use_env_proxy

    def translate(self, text: str) -> TranslationResult:
        if not self.config.hf_token:
            raise RuntimeError("HF_TOKEN is required for HuggingFace backend.")

        detected = self._resolve_source_language(text)
        skip, _reason = should_skip_translation(text, detected, self.config.target_lang)
        if skip:
            return build_translation_result(
                source_text=text,
                translated_text=text,
                source_lang=detected,
                target_lang=self.config.target_lang,
                skipped=True,
            )

        if self.config.hf_base_url.endswith("/v1"):
            translated = self._translate_openai_compatible(text, detected)
        else:
            translated = self._translate_inference_api(text, detected)

        return build_translation_result(
            source_text=text,
            translated_text=translated,
            source_lang=detected,
            target_lang=self.config.target_lang,
        )

    def resolve_source_language(self, text: str) -> str:
        return self._resolve_source_language(text)

    def _resolve_source_language(self, text: str) -> str:
        configured = self.config.source_lang.strip().lower()
        if configured and configured != "auto":
            return configured
        return detect_source_language(text, self.config.supported_source_langs)

    def _translate_openai_compatible(self, text: str, source_lang: str) -> str:
        endpoint = f"{self.config.hf_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.hf_model_id,
            "messages": [
                {"role": "system", "content": self._build_system_prompt(source_lang)},
                {"role": "user", "content": text},
            ],
            "max_tokens": self.config.hf_max_new_tokens,
            "temperature": self.config.hf_temperature,
        }
        body = self._post_json(endpoint, headers, payload)
        translated = self._extract_chat_text(body) or self._extract_generated_text(body)
        if not translated:
            raise RuntimeError("HuggingFace returned empty translation output.")
        return self._normalize_output(translated)

    def _translate_inference_api(self, text: str, source_lang: str) -> str:
        endpoint = f"{self.config.hf_base_url}/models/{self.config.hf_model_id}"
        headers = {
            "Authorization": f"Bearer {self.config.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": f"{self._build_system_prompt(source_lang)}\n\nUser text:\n{text}",
            "parameters": {
                "max_new_tokens": self.config.hf_max_new_tokens,
                "temperature": self.config.hf_temperature,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }
        body = self._post_json(endpoint, headers, payload)
        translated = self._extract_generated_text(body)
        if not translated:
            raise RuntimeError("HuggingFace returned empty translation output.")
        return self._normalize_output(translated)

    def _post_json(self, endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        retries = max(0, self.config.hf_retry_count)
        for attempt in range(1, retries + 2):
            try:
                response = self.http.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.config.hf_timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt <= retries:
                    self._sleep_backoff(attempt, None)
                    continue
                raise RuntimeError(f"HuggingFace request failed: {exc}") from exc

            body = self._parse_json_or_text(response)
            if response.status_code < 400:
                return body

            if response.status_code in self.RETRYABLE_STATUS_CODES and attempt <= retries:
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                self._sleep_backoff(attempt, retry_after)
                continue

            raise RuntimeError(f"HuggingFace API error ({response.status_code}): {self._error_message(body)}")

        raise RuntimeError("HuggingFace request failed after retries.")

    def _build_system_prompt(self, detected_source_lang: str) -> str:
        return build_system_prompt(
            source_lang=detected_source_lang,
            target_lang=self.config.target_lang.strip() or TARGET_LANGUAGE.code,
            allowed_sources=self.config.supported_source_langs,
        )

    @staticmethod
    def _parse_json_or_text(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _error_message(body: Any) -> str:
        if isinstance(body, dict):
            if "error" in body:
                return TranslatorService._normalize_error_text(str(body["error"]))
            return TranslatorService._normalize_error_text(str(body))
        if isinstance(body, str):
            return TranslatorService._extract_html_error_summary(body)
        return TranslatorService._normalize_error_text(str(body))

    @staticmethod
    def _normalize_error_text(text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) > 220:
            return compact[:217] + "..."
        return compact

    @staticmethod
    def _extract_html_error_summary(text: str) -> str:
        raw = text.strip()
        lowered = raw.lower()
        if "<html" not in lowered:
            return TranslatorService._normalize_error_text(raw)

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw, flags=re.IGNORECASE | re.DOTALL)
        p_match = re.search(r"<p[^>]*>(.*?)</p>", raw, flags=re.IGNORECASE | re.DOTALL)
        h1_text = TranslatorService._normalize_error_text(re.sub(r"<[^>]+>", "", h1_match.group(1))) if h1_match else ""
        p_text = TranslatorService._normalize_error_text(re.sub(r"<[^>]+>", "", p_match.group(1))) if p_match else ""

        if h1_text and p_text:
            return f"{h1_text} {p_text}".strip()
        if h1_text:
            return h1_text
        if p_text:
            return p_text
        return "Service unavailable (HTML response)."

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        value = value.strip()
        try:
            seconds = float(value)
            if seconds >= 0:
                return seconds
        except ValueError:
            return None
        return None

    def _sleep_backoff(self, attempt: int, retry_after_seconds: float | None) -> None:
        if retry_after_seconds is not None:
            delay = retry_after_seconds
        else:
            base = max(0.2, self.config.hf_retry_backoff_seconds)
            delay = min(20.0, base * (2 ** (attempt - 1)))
        time.sleep(delay)

    @staticmethod
    def _extract_generated_text(body: Any) -> str:
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, dict):
                for key in ("generated_text", "translation_text", "text"):
                    value = first.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
        if isinstance(body, dict):
            for key in ("generated_text", "translation_text", "text"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        if isinstance(body, str):
            return body
        return ""

    @staticmethod
    def _extract_chat_text(body: Any) -> str:
        if not isinstance(body, dict):
            return ""
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""

        message = first.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                if parts:
                    return "\n".join(parts)

        text = first.get("text")
        if isinstance(text, str) and text.strip():
            return text
        return ""

    @staticmethod
    def _normalize_output(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^\s*(translation|translated text)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip().strip('"').strip("'")


class TkTranslatorApp:
    URL_ONLY_RE = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)
    BUBBLE_SIZE = 68
    BUBBLE_SHELL_BG = "#0B1220"
    PANEL_WIDTH = 460
    PANEL_HEIGHT = 230
    VISIBILITY_CHECK_MS = 800
    TOPMOST_ENFORCE_MS = 200
    TOPMOST_HARD_RESET_SEC = 2.0

    def __init__(self, config: AppConfig, service: TranslatorService):
        self.config = config
        self.service = service
        self.cache = LruCache(config.cache_size)

        self.pending_text = ""
        self.last_seen_clipboard_text = ""
        self.last_processed_text = ""
        self.last_processed_at = 0.0
        self.in_flight: dict[str, float] = {}
        self.result_queue: queue.Queue[tuple[TranslationResult | None, str | None, str]] = queue.Queue()

        self._debounce_after_id: str | None = None
        self._running = True
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._panel_expanded = False
        self._panel_pinned = False
        self._auto_hide_after_id: str | None = None
        self._anchor_tr_x = 0
        self._anchor_tr_y = 0
        self._visibility_warned = False
        self._last_visibility_signature = ""
        self._recover_cooldown_until = 0.0
        self._topmost_tick = 0
        self._last_hard_topmost_at = 0.0
        self._bubble_photo = None
        self._bubble_active = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("翻译助手")
        self.root.configure(bg=self.BUBBLE_SHELL_BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.wm_attributes("-topmost", 1)
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.root.bind("<Control-Shift-T>", lambda _event: self.translate_now())
        self.root.bind("<Control-Shift-t>", lambda _event: self.translate_now())
        self._font_family = self._select_display_font_family()
        self._pil_image = None
        self._pil_draw = None
        self._pil_font = None
        self._pil_imagetk = None
        self._pil_font_path: str | None = None
        self._title_photo = None
        self._source_photo = None
        self._status_photo = None
        self._translated_photo = None
        self._init_image_text_renderer()

        self._build_ui()
        self._place_initial_bubble()
        self._finalize_window_show()
        self._log("就绪：复制外语文本自动翻译；Ctrl+Shift+T 手动触发")
        if self._running_on_wsl():
            self._log("提示：WSL 版不能盖住 Chrome/Edge 等浏览器，需用 Windows 版才能全局置顶")

        self.root.after(0, self._finalize_window_show)
        self.root.after(300, self._finalize_window_show)
        self.root.after(1000, self._finalize_window_show)
        self.root.after(self.VISIBILITY_CHECK_MS, self._keep_window_visible)
        self.root.after(self.TOPMOST_ENFORCE_MS, self._enforce_topmost)
        self.root.bind("<Map>", lambda _event: self._raise_to_front())
        self.root.bind("<FocusOut>", lambda _event: self._raise_to_front())
        self.root.after(max(100, config.clipboard_poll_ms), self._poll_clipboard)
        self.root.after(80, self._process_result_queue)

    def _log(self, message: str) -> None:
        if self.config.log_events:
            print(f"[translate-helper][tk] {message}", flush=True)

    def _build_ui(self) -> None:
        self.shell = tk.Frame(self.root, bg=self.BUBBLE_SHELL_BG, bd=0, highlightthickness=0)
        self.shell.pack(fill="both", expand=True)

        self.bubble_view = tk.Frame(
            self.shell,
            bg=self.BUBBLE_SHELL_BG,
            width=self.BUBBLE_SIZE,
            height=self.BUBBLE_SIZE,
            bd=0,
            highlightthickness=0,
        )
        self.bubble_view.pack_propagate(False)
        self.bubble_label = tk.Label(
            self.bubble_view,
            bg=self.BUBBLE_SHELL_BG,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.bubble_label.pack(expand=True)
        self._refresh_bubble_skin()

        self.panel_view = tk.Frame(self.shell, bg="#111827", bd=1, relief="solid")

        card = tk.Frame(self.panel_view, bg="#111827")
        card.pack(fill="both", expand=True, padx=1, pady=1)

        top_row = tk.Frame(card, bg="#111827")
        top_row.pack(fill="x", padx=10, pady=(8, 6))

        title = tk.Label(
            top_row,
            justify="left",
            anchor="w",
            fg="#f9fafb",
            bg="#111827",
        )
        title.pack(side="left", fill="x", expand=True)
        self.title_label = title

        controls = tk.Frame(top_row, bg="#111827")
        controls.pack(side="right")

        self.pin_btn = tk.Button(
            controls,
            text="钉住",
            command=self._toggle_pin,
            relief="flat",
            bg="#374151",
            fg="#F9FAFB",
            activebackground="#4B5563",
            activeforeground="#F9FAFB",
            padx=8,
            pady=2,
            cursor="hand2",
        )
        self.pin_btn.pack(side="left", padx=(0, 4))

        self.close_btn = tk.Button(
            controls,
            text="关闭",
            command=self._collapse_to_bubble,
            relief="flat",
            bg="#374151",
            fg="#F9FAFB",
            activebackground="#4B5563",
            activeforeground="#F9FAFB",
            padx=8,
            pady=2,
            cursor="hand2",
        )
        self.close_btn.pack(side="left")

        self.source_label = tk.Label(
            card,
            justify="left",
            anchor="w",
            fg="#9ca3af",
            bg="#111827",
            wraplength=420,
        )
        self.source_label.pack(fill="x", padx=10, pady=(0, 4))

        self.translated_container = tk.Frame(card, bg="#111827")
        self.translated_container.pack(fill="x", padx=10, pady=(0, 6))

        self.translated_label = tk.Label(
            self.translated_container,
            justify="left",
            anchor="w",
            fg="#f9fafb",
            bg="#111827",
            wraplength=420,
        )
        self.translated_label.pack(fill="x")

        self.status_label = tk.Label(
            card,
            justify="left",
            anchor="w",
            fg="#60a5fa",
            bg="#111827",
            wraplength=420,
        )
        self.status_label.pack(fill="x", padx=10, pady=(0, 8))

        drag_targets = (self.bubble_view, self.bubble_label, top_row, title, self.panel_view, card)
        for widget in drag_targets:
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_move)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)

        self.bubble_label.bind("<Double-Button-1>", lambda _event: self.translate_now())
        self.bubble_view.bind("<Button-3>", lambda _event: self.shutdown())

        self.panel_view.pack_forget()
        self.bubble_view.pack(fill="both", expand=True)
        self._panel_expanded = False

    def _sync_anchor_from_window(self) -> None:
        self.root.update_idletasks()
        self._anchor_tr_x = self.root.winfo_x() + self.root.winfo_width()
        self._anchor_tr_y = self.root.winfo_y()

    def _apply_geometry(self, width: int, height: int) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        margin = max(0, self.config.margin_px)
        x = self._anchor_tr_x - width
        y = self._anchor_tr_y
        if x < margin:
            x = margin
        if y < margin:
            y = margin
        if x + width > screen_w - margin:
            x = max(margin, screen_w - width - margin)
        if y + height > screen_h - margin:
            y = max(margin, screen_h - height - margin)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self._anchor_tr_x = x + width
        self._anchor_tr_y = y
        self._clamp_window_to_screen()

    def _place_initial_bubble(self) -> None:
        margin = max(0, self.config.margin_px)
        screen_w = max(800, self.root.winfo_screenwidth())
        screen_h = max(600, self.root.winfo_screenheight())
        if self._running_on_wsl():
            # WSLg 下居中更容易看到；用户拖动后会记住新位置
            self._anchor_tr_x = int(screen_w * 0.52)
            self._anchor_tr_y = int(screen_h * 0.42)
        else:
            self._anchor_tr_x = min(screen_w - margin, max(margin + self.BUBBLE_SIZE, int(screen_w * 0.75)))
            self._anchor_tr_y = max(margin, int(screen_h * 0.15))
        self._collapse_to_bubble(initial=True)
        self._log(f"小球位置: 屏幕 {screen_w}x{screen_h}, 锚点 ({self._anchor_tr_x}, {self._anchor_tr_y})")

    def _expand_panel(self, schedule_hide: bool = True) -> None:
        if self._panel_expanded:
            if schedule_hide:
                self._schedule_auto_hide()
            return
        self._sync_anchor_from_window()
        self.shell.configure(bg="#111827")
        self.root.configure(bg="#111827")
        self.bubble_view.pack_forget()
        self.panel_view.pack(fill="both", expand=True)
        self._panel_expanded = True
        self._render_static_title()
        self.root.update_idletasks()
        self._apply_geometry(self.PANEL_WIDTH, self.PANEL_HEIGHT)
        self._finalize_window_show()
        if schedule_hide and not self._panel_pinned:
            self._schedule_auto_hide()

    def _collapse_to_bubble(self, initial: bool = False) -> None:
        self._cancel_auto_hide()
        if self._panel_expanded:
            self._sync_anchor_from_window()
        self.panel_view.pack_forget()
        self.shell.configure(bg=self.BUBBLE_SHELL_BG)
        self.root.configure(bg=self.BUBBLE_SHELL_BG)
        self.bubble_view.pack(fill="both", expand=True)
        self._panel_expanded = False
        if not initial:
            self._panel_pinned = False
            self.pin_btn.configure(text="钉住", bg="#374151")
        self._refresh_bubble_skin()
        self.root.update_idletasks()
        self._apply_geometry(self.BUBBLE_SIZE, self.BUBBLE_SIZE)
        if not initial:
            self._finalize_window_show()

    def _raise_to_front(self) -> None:
        if not self._running or self._dragging:
            return
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)
            self._apply_platform_topmost()
        except tk.TclError:
            pass

    @staticmethod
    def _is_windows_native() -> bool:
        return sys.platform == "win32"

    def _resolve_windows_hwnd(self) -> int | None:
        if not self._is_windows_native():
            return None
        try:
            import ctypes

            hwnd = int(self.root.winfo_id())
            if hwnd <= 0:
                return None
            parent = int(ctypes.windll.user32.GetParent(hwnd))
            return parent if parent > 0 else hwnd
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _apply_windows_topmost(self) -> None:
        hwnd = self._resolve_windows_hwnd()
        if hwnd is None:
            return
        try:
            import ctypes

            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _apply_platform_topmost(self) -> None:
        if self._is_windows_native():
            self._apply_windows_topmost()
        elif self._running_on_wsl() or sys.platform.startswith("linux"):
            self._apply_x11_above_state()

    def _apply_x11_above_state(self) -> None:
        xprop = shutil.which("xprop")
        if not xprop:
            return
        try:
            window_id = self.root.winfo_id()
            subprocess.run(
                [
                    xprop,
                    "-id",
                    str(window_id),
                    "-f",
                    "_NET_WM_STATE",
                    "32a",
                    "-set",
                    "_NET_WM_STATE",
                    "_NET_WM_STATE_ABOVE",
                ],
                timeout=1,
                check=False,
                capture_output=True,
            )
        except (OSError, subprocess.TimeoutExpired, tk.TclError):
            pass

    def _enforce_topmost(self) -> None:
        if not self._running:
            return
        try:
            self._topmost_tick += 1
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)

            now = time.monotonic()
            if now - self._last_hard_topmost_at >= self.TOPMOST_HARD_RESET_SEC:
                self._last_hard_topmost_at = now
                self.root.attributes("-topmost", False)
                self.root.update_idletasks()
                self.root.attributes("-topmost", True)
                self.root.wm_attributes("-topmost", 1)
                self.root.lift()

            if self._topmost_tick % 3 == 0:
                self._apply_platform_topmost()
        except tk.TclError:
            pass
        self.root.after(self.TOPMOST_ENFORCE_MS, self._enforce_topmost)

    def _visibility_signature(self) -> str:
        try:
            return (
                f"{self.root.state()}|{self.root.winfo_ismapped()}|{self.root.winfo_viewable()}|"
                f"{self.root.winfo_geometry()}|{self._panel_expanded}"
            )
        except tk.TclError:
            return "error"

    def _window_position_invalid(self) -> bool:
        try:
            self.root.update_idletasks()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            margin = max(0, self.config.margin_px)
            if width < 20 or height < 20:
                return True
            if x + width < margin or y + height < margin:
                return True
            if x > screen_w - margin or y > screen_h - margin:
                return True
        except tk.TclError:
            return True
        return False

    def _expected_window_size(self) -> tuple[int, int]:
        if self._panel_expanded:
            return self.PANEL_WIDTH, self.PANEL_HEIGHT
        return self.BUBBLE_SIZE, self.BUBBLE_SIZE

    def _log_visibility_state(self, tag: str) -> None:
        if not self.config.log_events:
            return
        signature = self._visibility_signature()
        if signature == self._last_visibility_signature and tag == "window":
            return
        self._last_visibility_signature = signature
        try:
            self._log(
                f"{tag}: state={self.root.state()} mapped={self.root.winfo_ismapped()} "
                f"viewable={self.root.winfo_viewable()} geom={self.root.winfo_geometry()} "
                f"expanded={self._panel_expanded}"
            )
        except tk.TclError:
            pass

    def _hard_recover_window(self) -> None:
        if not self._running or self._dragging:
            return
        now = time.monotonic()
        if now < self._recover_cooldown_until:
            return
        self._recover_cooldown_until = now + 1.5
        try:
            width, height = self._expected_window_size()
            if self._window_position_invalid():
                margin = max(0, self.config.margin_px)
                screen_w = max(800, self.root.winfo_screenwidth())
                screen_h = max(600, self.root.winfo_screenheight())
                if self._running_on_wsl():
                    self._anchor_tr_x = int(screen_w * 0.52)
                    self._anchor_tr_y = int(screen_h * 0.42)
                else:
                    self._anchor_tr_x = min(screen_w - margin, max(margin + self.BUBBLE_SIZE, int(screen_w * 0.75)))
                    self._anchor_tr_y = max(margin, int(screen_h * 0.15))
            self.root.withdraw()
            self.root.update_idletasks()
            self._apply_geometry(width, height)
            self.root.deiconify()
            self.root.attributes("-topmost", False)
            self.root.update_idletasks()
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)
            self.root.lift()
            self._apply_platform_topmost()
            self.root.update_idletasks()
            self._clamp_window_to_screen()
            self._log_visibility_state("recover")
        except tk.TclError:
            pass

    def _finalize_window_show(self) -> None:
        try:
            state = self.root.state()
            if state in {"withdrawn", "iconic"}:
                self.root.deiconify()
            width, height = self._expected_window_size()
            self.root.update_idletasks()
            if self.root.winfo_width() < 20 or self.root.winfo_height() < 20 or self._window_position_invalid():
                self._apply_geometry(width, height)
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)
            self.root.lift()
            self._apply_platform_topmost()
            self.root.update_idletasks()
            self._clamp_window_to_screen()
            if not self.root.winfo_viewable() and not self._visibility_warned:
                self._visibility_warned = True
                if self._running_on_wsl():
                    self._log("WSL 模式无法始终浮在 Windows 浏览器上，请改用 Windows 版：运行 build-app.bat")
                else:
                    self._log("窗口可能未显示，请确认在桌面会话中运行")
            self._log_visibility_state("window")
        except tk.TclError:
            pass

    def _keep_window_visible(self) -> None:
        if not self._running:
            return
        try:
            state = self.root.state()
            mapped = self.root.winfo_ismapped()
            viewable = self.root.winfo_viewable()
            if (
                state in {"withdrawn", "iconic"}
                or not mapped
                or not viewable
                or self._window_position_invalid()
            ):
                self._hard_recover_window()
        except tk.TclError:
            pass
        self.root.after(self.VISIBILITY_CHECK_MS, self._keep_window_visible)

    def _toggle_pin(self) -> None:
        self._panel_pinned = not self._panel_pinned
        if self._panel_pinned:
            self.pin_btn.configure(text="已钉", bg="#1D4ED8")
            self._cancel_auto_hide()
            self._log("panel pinned")
        else:
            self.pin_btn.configure(text="钉住", bg="#374151")
            self._schedule_auto_hide()
            self._log("panel unpinned")

    def _schedule_auto_hide(self) -> None:
        if self._panel_pinned or self.config.panel_auto_hide_ms <= 0:
            return
        self._cancel_auto_hide()
        self._auto_hide_after_id = self.root.after(self.config.panel_auto_hide_ms, self._collapse_to_bubble)

    def _cancel_auto_hide(self) -> None:
        if self._auto_hide_after_id:
            try:
                self.root.after_cancel(self._auto_hide_after_id)
            except tk.TclError:
                pass
            self._auto_hide_after_id = None

    def _on_content_activity(self, schedule_hide: bool = True) -> None:
        self._expand_panel(schedule_hide=schedule_hide)
        self._finalize_window_show()

    def _bring_to_front(self) -> None:
        self._finalize_window_show()

    @staticmethod
    def _running_on_wsl() -> bool:
        try:
            with open("/proc/version", encoding="utf-8") as handle:
                return "microsoft" in handle.read().lower()
        except OSError:
            return False

    def _read_windows_clipboard_powershell(self) -> str:
        # Try common locations instead of relying on shutil.which (may fail in PyInstaller)
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if not ps:
            for candidate in (
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
            ):
                if os.path.isfile(candidate):
                    ps = candidate
                    break
        if not ps:
            return ""
        try:
            result = subprocess.run(
                [ps, "-NoProfile", "-STA", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0 or not isinstance(result.stdout, str):
            return ""
        return result.stdout

    @staticmethod
    def _read_clipboard_via_command() -> str:
        for cmd in (["wl-paste", "-n"], ["xclip", "-o", "-selection", "clipboard"]):
            if not shutil.which(cmd[0]):
                continue
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and isinstance(result.stdout, str) and result.stdout.strip():
                return result.stdout
        return ""

    def _clamp_window_to_screen(self) -> None:
        try:
            self.root.update_idletasks()
            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            margin = max(0, self.config.margin_px)

            new_x, new_y = x, y
            if x < margin:
                new_x = margin
            elif x + width > screen_w - margin:
                new_x = max(margin, screen_w - width - margin)
            if y < margin:
                new_y = margin
            elif y + height > screen_h - margin:
                new_y = max(margin, screen_h - height - margin)

            if new_x != x or new_y != y:
                self.root.geometry(f"{width}x{height}+{new_x}+{new_y}")
            self._anchor_tr_x = self.root.winfo_x() + width
            self._anchor_tr_y = self.root.winfo_y()
        except tk.TclError:
            pass

    def _select_display_font_family(self) -> str:
        preferred_families = [
            "Noto Sans CJK SC",
            "Noto Sans SC",
            "Source Han Sans SC",
            "WenQuanYi Micro Hei",
            "WenQuanYi Zen Hei",
            "Microsoft YaHei",
            "PingFang SC",
            "SimHei",
            "Arial Unicode MS",
            "Segoe UI",
        ]
        try:
            available_map = {name.lower(): name for name in tkfont.families(self.root)}
        except Exception:  # pylint: disable=broad-exception-caught
            return "TkDefaultFont"

        for family in preferred_families:
            found = available_map.get(family.lower())
            if found:
                self._log(f"using font family: {found}")
                return found

        self._log("using fallback font family: TkDefaultFont")
        return "TkDefaultFont"

    def _init_image_text_renderer(self) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
        except Exception:  # pylint: disable=broad-exception-caught
            self._log("Pillow unavailable; image text renderer disabled")
            return

        self._pil_image = Image
        self._pil_draw = ImageDraw
        self._pil_font = ImageFont
        self._pil_imagetk = ImageTk
        self._pil_font_path = self._resolve_render_font_file()

        if self._pil_font_path:
            self._log(f"using image-render font: {self._pil_font_path}")
        else:
            self._log("no CJK font file found for image renderer")

    def _resolve_render_font_file(self) -> str | None:
        candidates = [
            os.path.join(str(_DESKTOP_DIR), ".font-cache", "NotoSansCJKsc-Regular.otf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/mnt/c/Windows/Fonts/msyh.ttc",
            "/mnt/c/Windows/Fonts/msyh.ttf",
            "/mnt/c/Windows/Fonts/simhei.ttf",
        ]

        for path in candidates:
            if path and os.path.exists(path):
                return path

        return self._download_fallback_font()

    def _download_fallback_font(self) -> str | None:
        cache_dir = os.path.join(str(_DESKTOP_DIR), ".font-cache")
        os.makedirs(cache_dir, exist_ok=True)
        target = os.path.join(cache_dir, "NotoSansCJKsc-Regular.otf")
        if os.path.exists(target):
            return target

        url = (
            "https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
            "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
        )
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200 or not response.content:
                return None
            with open(target, "wb") as file:
                file.write(response.content)
            return target
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        if len(value) != 6:
            return 249, 250, 251
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    def _load_pil_font(self, font_size: int):
        if not (self._pil_font and self._pil_font_path):
            return None
        try:
            if self._pil_font_path.lower().endswith(".ttc"):
                return self._pil_font.truetype(self._pil_font_path, font_size, index=0)
            return self._pil_font.truetype(self._pil_font_path, font_size)
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _render_bubble_skin(self, *, active: bool = False) -> Any | None:
        if not (self._pil_image and self._pil_draw and self._pil_imagetk):
            return None

        size = self.BUBBLE_SIZE
        shell = self._hex_to_rgb(self.BUBBLE_SHELL_BG)
        img = self._pil_image.new("RGB", (size, size), shell)
        draw = self._pil_draw.Draw(img)

        if active:
            ring = (56, 189, 248)
            body = (29, 78, 216)
            shine = (125, 211, 252)
        else:
            ring = (59, 130, 246)
            body = (37, 99, 235)
            shine = (147, 197, 253)

        draw.ellipse((1, 1, size - 2, size - 2), fill=ring)
        draw.ellipse((4, 4, size - 5, size - 5), fill=body)
        draw.ellipse((10, 8, size - 12, size - 14), fill=shine)
        draw.ellipse((14, 12, size - 20, size - 22), fill=body)

        font = self._load_pil_font(24 if active else 22)
        if font is not None:
            glyph = "译"
            bbox = draw.textbbox((0, 0), glyph, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_x = (size - text_w) // 2 - bbox[0]
            text_y = (size - text_h) // 2 - bbox[1] + 1
            draw.text((text_x, text_y), glyph, font=font, fill=(255, 255, 255))

        return self._pil_imagetk.PhotoImage(img)

    def _refresh_bubble_skin(self, *, active: bool | None = None) -> None:
        if active is None:
            active = self._bubble_active
        else:
            self._bubble_active = active

        photo = self._render_bubble_skin(active=active)
        if photo is not None:
            self._bubble_photo = photo
            self.bubble_label.configure(image=photo, text="", bg=self.BUBBLE_SHELL_BG)
            return

        self._bubble_photo = None
        self.bubble_label.configure(
            image="",
            text="译",
            fg="#FFFFFF",
            bg="#2563EB",
            font=(self._font_family, 16, "bold"),
        )

    def _render_text_to_photo(
        self,
        text: str,
        width: int,
        font_size: int,
        *,
        fill: tuple[int, int, int] = (249, 250, 251),
        background: tuple[int, int, int] = (17, 24, 39),
    ) -> Any | None:
        if not (self._pil_image and self._pil_draw and self._pil_imagetk):
            return None
        if not text.strip():
            return None

        font = self._load_pil_font(font_size)
        if font is None:
            return None

        probe = self._pil_image.new("RGB", (8, 8), background)
        draw = self._pil_draw.Draw(probe)

        def text_width(s: str) -> float:
            try:
                return float(draw.textlength(s, font=font))
            except Exception:  # pylint: disable=broad-exception-caught
                bbox = draw.textbbox((0, 0), s, font=font)
                return float(bbox[2] - bbox[0])

        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            if not paragraph:
                lines.append("")
                continue
            current = ""
            for ch in paragraph:
                candidate = current + ch
                if current and text_width(candidate) > width:
                    lines.append(current)
                    current = ch
                else:
                    current = candidate
            lines.append(current)

        if not lines:
            lines = [text]

        bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_height = max(18, bbox[3] - bbox[1])
        line_spacing = 4
        pad = 4
        image_width = width + pad * 2
        image_height = pad * 2 + len(lines) * line_height + max(0, len(lines) - 1) * line_spacing

        image = self._pil_image.new("RGBA", (image_width, image_height), (*background, 255))
        canvas = self._pil_draw.Draw(image)
        y = pad
        for line in lines:
            canvas.text((pad, y), line, font=font, fill=(*fill, 255))
            y += line_height + line_spacing

        return self._pil_imagetk.PhotoImage(image)

    def _set_label_content(
        self,
        label: tk.Label,
        photo_attr: str,
        text: str,
        *,
        width: int = 420,
        font_size: int = 11,
        color: str = "#f9fafb",
        fallback_font: tuple[str, int] | tuple[str, int, str] = ("TkDefaultFont", 10),
    ) -> None:
        cleaned = text or ""
        if cleaned and self._pil_font_path:
            photo = self._render_text_to_photo(
                text=cleaned,
                width=width,
                font_size=font_size,
                fill=self._hex_to_rgb(color),
            )
            if photo is not None:
                setattr(self, photo_attr, photo)
                label.configure(image=photo, text="", font=fallback_font)
                return

        setattr(self, photo_attr, None)
        label.configure(image="", text=cleaned, font=fallback_font)

    def _render_static_title(self) -> None:
        self._set_label_content(
            self.title_label,
            "_title_photo",
            "多语翻译 → 中文",
            width=420,
            font_size=13,
            color="#f9fafb",
            fallback_font=(self._font_family, 11, "bold"),
        )

    def _set_translated_display(self, text: str) -> None:
        self._set_label_content(
            self.translated_label,
            "_translated_photo",
            text,
            width=420,
            font_size=18,
            color="#f9fafb",
            fallback_font=(self._font_family, 11, "bold"),
        )

    def _set_source_display(self, text: str) -> None:
        self._set_label_content(
            self.source_label,
            "_source_photo",
            text,
            width=420,
            font_size=11,
            color="#9ca3af",
            fallback_font=(self._font_family, 10),
        )

    def _set_status_display(self, text: str) -> None:
        self._set_label_content(
            self.status_label,
            "_status_photo",
            text,
            width=420,
            font_size=10,
            color="#60a5fa",
            fallback_font=(self._font_family, 9),
        )

    def _on_drag_start(self, event) -> None:
        self._dragging = True
        self._drag_start_x = event.x_root - self.root.winfo_x()
        self._drag_start_y = event.y_root - self.root.winfo_y()

    def _on_drag_move(self, event) -> None:
        if not self._dragging:
            return
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.root.geometry(f"+{x}+{y}")
        self._clamp_window_to_screen()

    def _on_drag_end(self, _event) -> None:
        self._dragging = False
        self._sync_anchor_from_window()
        self._clamp_window_to_screen()

    @staticmethod
    def _normalize(text: str) -> str:
        lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
        compact = " ".join(line for line in lines if line)
        compact = re.sub(r"\s{2,}", " ", compact)
        return compact.strip()

    def _read_clipboard_text(self) -> str:
        candidates: list[str] = []

        # 1) tkinter clipboard (works in native X11/Wayland)
        for clip_type in ("UTF8_STRING", "STRING", "TEXT"):
            try:
                value = self.root.clipboard_get(type=clip_type)
            except Exception:  # pylint: disable=broad-exception-caught
                value = ""
            if isinstance(value, str) and value.strip():
                candidates.append(value)
                break

        if not candidates:
            try:
                value = self.root.clipboard_get()
            except Exception:  # pylint: disable=broad-exception-caught
                value = ""
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        # 2) On native Windows (exe or python), tkinter may not reach system clipboard
        # Use powershell Get-Clipboard as a reliable fallback on any Windows environment
        if not candidates:
            value = self._read_windows_clipboard_powershell()
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        # 3) WSL: fallback to wl-paste / xclip
        if not candidates and self._running_on_wsl():
            value = self._read_clipboard_via_command()
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        # 4) PRIMARY selection (X11, not WSL)
        if not candidates and self._running_on_wsl():
            try:
                value = self.root.selection_get(selection="PRIMARY")
            except Exception:  # pylint: disable=broad-exception-caught
                value = ""
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        if not candidates:
            return ""
        return self._normalize(candidates[0])

    def _poll_clipboard(self) -> None:
        if not self._running:
            return
        try:
            text = self._read_clipboard_text()
            if text and text != self.last_seen_clipboard_text:
                self.last_seen_clipboard_text = text
                self._queue_text(text, trigger="poll")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._log(f"clipboard poll error: {exc}")
        self.root.after(max(100, self.config.clipboard_poll_ms), self._poll_clipboard)

    def _flash_bubble(self) -> None:
        if self._panel_expanded:
            return
        self._refresh_bubble_skin(active=True)
        self.root.after(220, lambda: self._refresh_bubble_skin(active=False))

    def _queue_text(self, text: str, trigger: str) -> None:
        self.pending_text = text
        self._log(f"检测到新文本 ({trigger}, {len(text)} 字)")
        preview = text if len(text) <= 160 else text[:157] + "..."
        self._flash_bubble()
        self._on_content_activity(schedule_hide=False)
        self._set_source_display(preview)
        self._set_status_display("已检测到剪贴板，准备翻译...")
        if self._debounce_after_id:
            try:
                self.root.after_cancel(self._debounce_after_id)
            except tk.TclError:
                pass
        self._debounce_after_id = self.root.after(self.config.debounce_ms, self._process_pending_text)

    def _skip_reason(self, text: str) -> str | None:
        if len(text) < self.config.min_text_length:
            return "文本太短，未翻译"
        if self.URL_ONLY_RE.match(text):
            return "仅 URL 链接，未翻译"
        if self.config.repeat_cooldown_ms > 0 and text == self.last_processed_text and self.last_processed_at > 0:
            elapsed_ms = int((time.monotonic() - self.last_processed_at) * 1000)
            if elapsed_ms < self.config.repeat_cooldown_ms:
                return f"相同内容冷却中（{elapsed_ms}ms）"
        detected = self.service.resolve_source_language(text)
        skip, reason = should_skip_translation(text, detected, self.config.target_lang)
        if skip:
            return reason
        return None

    def _process_pending_text(self, force: bool = False) -> None:
        self._debounce_after_id = None
        text = self.pending_text
        self.pending_text = ""
        if not text:
            return

        reason = None if force else self._skip_reason(text)
        if reason:
            preview = text if len(text) <= 160 else text[:157] + "..."
            self._on_content_activity(schedule_hide=True)
            self._set_source_display(preview)
            self._set_translated_display("")
            self._set_status_display(f"已跳过：{reason}")
            self._log(f"skip translation: {reason}")
            return

        text = text[: self.config.max_text_length]
        cached = self.cache.get(text)
        if cached is not None:
            detected = self.service.resolve_source_language(text)
            result = build_translation_result(
                source_text=text,
                translated_text=cached,
                source_lang=detected,
                target_lang=self.config.target_lang,
                from_cache=True,
            )
            self.last_processed_text = text
            self.last_processed_at = time.monotonic()
            self.show_translation(result)
            self._log(f"translation served from cache ({result.status})")
            return

        started_at = self.in_flight.get(text)
        if started_at is not None:
            age_ms = int((time.monotonic() - started_at) * 1000)
            if age_ms < self.config.inflight_retry_ms:
                self._log(f"skip translation: already in progress ({age_ms}ms)")
                return
            self._log(f"retry stale in-flight request ({age_ms}ms)")
            self.in_flight.pop(text, None)

        self.in_flight[text] = time.monotonic()
        detected = self.service.resolve_source_language(text)
        self._on_content_activity(schedule_hide=False)
        self._set_status_display(f"翻译中：{format_route_label(detected, self.config.target_lang)}...")
        worker = threading.Thread(target=self._translate_worker, args=(text,), daemon=True)
        worker.start()

    def _translate_worker(self, text: str) -> None:
        try:
            result = self.service.translate(text)
            self.result_queue.put((result, None, text))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.result_queue.put((None, str(exc), text))

    def _process_result_queue(self) -> None:
        if not self._running:
            return
        while True:
            try:
                result, error, source_text = self.result_queue.get_nowait()
            except queue.Empty:
                break

            self.in_flight.pop(source_text, None)

            if error is not None:
                self.show_error(source_text, error)
                self._log(f"translation request failed: {error}")
                continue

            if result is None:
                continue

            self.last_processed_text = result.source_text
            self.last_processed_at = time.monotonic()

            if not result.translated_text.strip():
                self.show_error(result.source_text, "Empty translation output")
                self._log("translation request failed: empty output")
                continue

            if not result.skipped:
                self.cache.set(result.source_text, result.translated_text)
            self.show_translation(result)
            self._log(f"translation request succeeded ({result.status})")

        self.root.after(80, self._process_result_queue)

    def translate_now(self) -> None:
        text = self._read_clipboard_text()
        if not text:
            self._on_content_activity(schedule_hide=True)
            self._set_status_display("剪贴板没有文本")
            self._log("手动翻译跳过：剪贴板无文本")
            return
        self._log("手动翻译请求 (Ctrl+Shift+T)")
        self.pending_text = text
        self._process_pending_text(force=True)

    def show_status(self, text: str) -> None:
        self._on_content_activity(schedule_hide=True)
        self._set_source_display("")
        self._set_translated_display("")
        self._set_status_display(text)
        self.root.update_idletasks()

    def show_translation(self, result: TranslationResult) -> None:
        self._on_content_activity(schedule_hide=True)
        source_preview = result.source_text if len(result.source_text) <= 160 else result.source_text[:157] + "..."
        self._set_source_display(source_preview)
        if result.skipped:
            self._set_translated_display("（已是中文，无需翻译）")
        else:
            self._set_translated_display(result.translated_text)
        self._set_status_display(result.status)
        self.root.update_idletasks()

    def show_error(self, source_text: str, error_message: str) -> None:
        self._on_content_activity(schedule_hide=True)
        source_preview = source_text[:160]
        short_error = error_message if len(error_message) <= 120 else error_message[:117] + "..."
        self._set_source_display(source_preview)
        self._set_translated_display("")
        self._set_status_display(f"翻译失败：{short_error}")
        self.root.update_idletasks()

    def run(self) -> int:
        self._log("tkinter UI started")
        self.root.after(0, self._finalize_window_show)
        self.root.mainloop()
        return 0

    def shutdown(self) -> None:
        if not self._running:
            return
        self._running = False
        self._cancel_auto_hide()
        self._log("application exiting")
        try:
            self.root.quit()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            self.root.destroy()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


def main() -> int:
    load_env_file()
    config = AppConfig.from_env()

    print("[translate-helper] 启动界面...", flush=True)
    print(
        "[translate-helper] 语言: "
        f"{','.join(config.supported_source_langs)} -> {config.target_lang}",
        flush=True,
    )
    try:
        service = TranslatorService(config)
        app = TkTranslatorApp(config, service)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[translate-helper] 界面初始化失败: {exc}", flush=True)
        return 2

    print("[translate-helper] 运行中（终端会保持占用，Ctrl+C 退出）。", flush=True)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
