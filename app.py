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
from typing import Any

import requests
import tkinter as tk
import tkinter.font as tkfont


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


def load_env_file(path: str = ".env") -> None:
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
            target_lang=os.getenv("TARGET_LANG", "zh-CN"),
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

    def translate(self, text: str) -> str:
        if not self.config.hf_token:
            raise RuntimeError("HF_TOKEN is required for HuggingFace backend.")

        if self.config.hf_base_url.endswith("/v1"):
            return self._translate_openai_compatible(text)
        return self._translate_inference_api(text)

    def _translate_openai_compatible(self, text: str) -> str:
        endpoint = f"{self.config.hf_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.hf_model_id,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
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

    def _translate_inference_api(self, text: str) -> str:
        endpoint = f"{self.config.hf_base_url}/models/{self.config.hf_model_id}"
        headers = {
            "Authorization": f"Bearer {self.config.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": f"{self._build_system_prompt()}\n\nUser text:\n{text}",
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

    def _build_system_prompt(self) -> str:
        source = self.config.source_lang.strip() or "auto"
        target = self.config.target_lang.strip() or "zh-CN"
        if source.lower() == "auto":
            source_hint = "Detect the source language automatically."
        else:
            source_hint = f"Source language: {source}."
        return (
            "You are a professional translation engine.\n"
            f"{source_hint}\n"
            f"Translate the user text into {target}.\n"
            "Return only translated text without explanation."
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
    TOPMOST_ENFORCE_MS = 50
    TOPMOST_HARD_RESET_EVERY = 8
    TOPMOST_AGGRESSIVE_EVERY = 10
    TOPMOST_X11_REAPPLY_EVERY = 20

    def __init__(self, config: AppConfig, service: TranslatorService):
        self.config = config
        self.service = service
        self.cache = LruCache(config.cache_size)

        self.pending_text = ""
        self.last_seen_clipboard_text = ""
        self.last_processed_text = ""
        self.last_processed_at = 0.0
        self.in_flight: dict[str, float] = {}
        self.result_queue: queue.Queue[tuple[str, str | None, str | None]] = queue.Queue()

        self._debounce_after_id: str | None = None
        self._running = True
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._iconic_retry_count = 0
        self._last_iconic_log_at = 0.0
        self._iconic_warned = False
        self._topmost_tick = 0
        self._xprop_supported = False

        self.root = tk.Tk()
        self.root.title("Clipboard Translator")
        self.root.geometry("460x230")
        self.root.minsize(420, 190)
        self.root.configure(bg="#111827")
        self.root.attributes("-topmost", True)
        self.root.wm_attributes("-topmost", 1)
        self._apply_platform_topmost_hint()
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self._font_family = self._select_display_font_family()
        self._pil_image = None
        self._pil_draw = None
        self._pil_font = None
        self._pil_imagetk = None
        self._pil_font_path: str | None = None
        self._translated_photo = None
        self._init_image_text_renderer()

        self.source_var = tk.StringVar(value="")
        self.translated_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._place_top_right()
        self._init_x11_topmost_support()
        self._enforce_topmost()
        self.root.bind("<FocusIn>", lambda _event: self._enforce_topmost())
        self.root.bind("<FocusOut>", lambda _event: self._schedule_topmost_burst())
        self.root.bind("<Map>", lambda _event: self._enforce_topmost())
        self.root.bind("<Visibility>", lambda _event: self._schedule_topmost_burst())
        self.show_status("Ready. Copy text to translate.")

        self.root.after(max(100, config.clipboard_poll_ms), self._poll_clipboard)
        self.root.after(80, self._process_result_queue)
        self.root.after(1500, self._keep_window_visible)
        self.root.after(self.TOPMOST_ENFORCE_MS, self._keep_topmost)

    def _log(self, message: str) -> None:
        if self.config.log_events:
            print(f"[clipboard-translator][tk] {message}", flush=True)

    def _build_ui(self) -> None:
        title_font = (self._font_family, 11, "bold")
        body_font = (self._font_family, 10)
        translated_font = (self._font_family, 11, "bold")
        status_font = (self._font_family, 9)

        card = tk.Frame(self.root, bg="#111827", bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=1, pady=1)

        top_row = tk.Frame(card, bg="#111827")
        top_row.pack(fill="x", padx=10, pady=(8, 6))

        title = tk.Label(
            top_row,
            text="Clipboard Translation",
            fg="#f9fafb",
            bg="#111827",
            font=title_font,
        )
        title.pack(side="left")

        source_label = tk.Label(
            card,
            textvariable=self.source_var,
            justify="left",
            anchor="w",
            fg="#9ca3af",
            bg="#111827",
            wraplength=420,
            font=body_font,
        )
        source_label.pack(fill="x", padx=10, pady=(0, 4))

        self.translated_container = tk.Frame(card, bg="#111827")
        self.translated_container.pack(fill="x", padx=10, pady=(0, 6))

        self.translated_text_label = tk.Label(
            self.translated_container,
            textvariable=self.translated_var,
            justify="left",
            anchor="w",
            fg="#f9fafb",
            bg="#111827",
            wraplength=420,
            font=translated_font,
        )
        self.translated_text_label.pack(fill="x")

        self.translated_image_label = tk.Label(
            self.translated_container,
            justify="left",
            anchor="w",
            bg="#111827",
            bd=0,
            highlightthickness=0,
        )

        status_label = tk.Label(
            card,
            textvariable=self.status_var,
            justify="left",
            anchor="w",
            fg="#60a5fa",
            bg="#111827",
            wraplength=420,
            font=status_font,
        )
        status_label.pack(fill="x", padx=10, pady=(0, 8))

        for widget in (top_row, title):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_move)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)

    def _place_top_right(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max(0, self.root.winfo_screenwidth() - width - self.config.margin_px)
        y = max(0, self.config.margin_px)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

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
            os.path.join(os.path.dirname(__file__), ".font-cache", "NotoSansCJKsc-Regular.otf"),
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
        cache_dir = os.path.join(os.path.dirname(__file__), ".font-cache")
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
    def _contains_non_ascii(text: str) -> bool:
        return any(ord(ch) > 127 for ch in text)

    def _render_text_to_photo(self, text: str, width: int, font_size: int) -> Any | None:
        if not (self._pil_image and self._pil_draw and self._pil_font and self._pil_imagetk and self._pil_font_path):
            return None
        if not text.strip():
            return None

        try:
            font = self._pil_font.truetype(self._pil_font_path, font_size)
        except Exception:  # pylint: disable=broad-exception-caught
            return None

        probe = self._pil_image.new("RGB", (8, 8), (0, 0, 0))
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

        image = self._pil_image.new("RGBA", (image_width, image_height), (17, 24, 39, 255))
        canvas = self._pil_draw.Draw(image)
        y = pad
        for line in lines:
            canvas.text((pad, y), line, font=font, fill=(249, 250, 251, 255))
            y += line_height + line_spacing

        return self._pil_imagetk.PhotoImage(image)

    def _set_translated_display(self, text: str) -> None:
        if text and self._contains_non_ascii(text):
            photo = self._render_text_to_photo(text=text, width=420, font_size=18)
            if photo is not None:
                self._translated_photo = photo
                self.translated_image_label.configure(image=photo)
                if not self.translated_image_label.winfo_ismapped():
                    self.translated_text_label.pack_forget()
                    self.translated_image_label.pack(fill="x")
                return

        self._translated_photo = None
        self.translated_var.set(text)
        if not self.translated_text_label.winfo_ismapped():
            self.translated_image_label.pack_forget()
            self.translated_text_label.pack(fill="x")

    def _apply_platform_topmost_hint(self) -> None:
        # On Linux/WSLg some WMs honor dock/splash hints for persistent top layers.
        try:
            self.root.wm_attributes("-type", "dock")
            return
        except tk.TclError:
            pass
        try:
            self.root.wm_attributes("-type", "splash")
        except tk.TclError:
            pass

    def _init_x11_topmost_support(self) -> None:
        self._xprop_supported = bool(shutil.which("xprop"))
        if self._xprop_supported:
            self._apply_x11_above_state()

    def _apply_x11_above_state(self) -> None:
        if not self._xprop_supported:
            return
        window_id = hex(self.root.winfo_id())
        cmds = [
            [
                "xprop",
                "-id",
                window_id,
                "-f",
                "_NET_WM_STATE",
                "32a",
                "-set",
                "_NET_WM_STATE",
                "_NET_WM_STATE_ABOVE,_NET_WM_STATE_STICKY",
            ],
            [
                "xprop",
                "-id",
                window_id,
                "-f",
                "_NET_WM_WINDOW_TYPE",
                "32a",
                "-set",
                "_NET_WM_WINDOW_TYPE",
                "_NET_WM_WINDOW_TYPE_DOCK",
            ],
        ]
        for cmd in cmds:
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:  # pylint: disable=broad-exception-caught
                return

    def _aggressive_raise(self) -> None:
        try:
            self.root.deiconify()
            self.root.state("normal")
        except tk.TclError:
            pass
        self._enforce_topmost()

    def _force_above_once(self) -> None:
        try:
            # One-shot hard reset used in bursts after focus/visibility changes.
            self.root.attributes("-topmost", False)
            self.root.wm_attributes("-topmost", 0)
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)
            self.root.lift()
            self._apply_x11_above_state()
        except tk.TclError:
            pass

    def _schedule_topmost_burst(self) -> None:
        # Re-assert topmost in short hard bursts after focus/visibility changes.
        self._force_above_once()
        self.root.after(20, self._force_above_once)
        self.root.after(70, self._force_above_once)
        self.root.after(150, self._force_above_once)
        self.root.after(300, self._force_above_once)

    def _enforce_topmost(self) -> None:
        try:
            self._topmost_tick += 1
            self.root.attributes("-topmost", True)
            self.root.wm_attributes("-topmost", 1)
            self.root.lift()
            if self._topmost_tick % self.TOPMOST_X11_REAPPLY_EVERY == 0:
                self._apply_x11_above_state()
        except tk.TclError:
            pass

    def _keep_topmost(self) -> None:
        if not self._running:
            return
        if self._topmost_tick % self.TOPMOST_AGGRESSIVE_EVERY == 0:
            self._schedule_topmost_burst()
        self._enforce_topmost()
        self.root.after(self.TOPMOST_ENFORCE_MS, self._keep_topmost)

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

    def _on_drag_end(self, _event) -> None:
        self._dragging = False

    def _keep_window_visible(self) -> None:
        if not self._running:
            return
        try:
            state = self.root.state()
        except tk.TclError:
            return

        if state in {"withdrawn", "iconic"}:
            self._iconic_retry_count += 1
            now = time.monotonic()
            if self._iconic_retry_count in {1, 2, 5, 10} or (now - self._last_iconic_log_at) >= 30:
                self._log(f"window state={state}, restoring (attempt={self._iconic_retry_count})")
                self._last_iconic_log_at = now
            if self._iconic_retry_count >= 12 and not self._iconic_warned:
                self._iconic_warned = True
                self._log("window manager keeps iconifying this app; GUI session may be unstable.")
            try:
                self.root.deiconify()
                self.root.state("normal")
            except tk.TclError:
                pass
        elif self._iconic_retry_count > 0:
            self._log(f"window restored after {self._iconic_retry_count} retries")
            self._iconic_retry_count = 0
            self._iconic_warned = False

        try:
            self._enforce_topmost()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        self.root.after(1500, self._keep_window_visible)

    @staticmethod
    def _normalize(text: str) -> str:
        lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
        compact = " ".join(line for line in lines if line)
        compact = re.sub(r"\s{2,}", " ", compact)
        return compact.strip()

    def _read_clipboard_text(self) -> str:
        candidates = []

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

        if not candidates:
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
        text = self._read_clipboard_text()
        if text and text != self.last_seen_clipboard_text:
            self.last_seen_clipboard_text = text
            self._queue_text(text, trigger="poll")
        self.root.after(max(100, self.config.clipboard_poll_ms), self._poll_clipboard)

    def _queue_text(self, text: str, trigger: str) -> None:
        self.pending_text = text
        self._log(f"clipboard update received ({trigger}, {len(text)} chars)")
        if self._debounce_after_id:
            try:
                self.root.after_cancel(self._debounce_after_id)
            except tk.TclError:
                pass
        self._debounce_after_id = self.root.after(self.config.debounce_ms, self._process_pending_text)

    def _skip_reason(self, text: str) -> str | None:
        if len(text) < self.config.min_text_length:
            return "text too short"
        if self.URL_ONLY_RE.match(text):
            return "url only"
        if self.config.repeat_cooldown_ms > 0 and text == self.last_processed_text and self.last_processed_at > 0:
            elapsed_ms = int((time.monotonic() - self.last_processed_at) * 1000)
            if elapsed_ms < self.config.repeat_cooldown_ms:
                return f"same as last text within cooldown ({elapsed_ms}ms)"
        return None

    def _process_pending_text(self, force: bool = False) -> None:
        self._debounce_after_id = None
        text = self.pending_text
        self.pending_text = ""
        if not text:
            return

        reason = None if force else self._skip_reason(text)
        if reason:
            self._log(f"skip translation: {reason}")
            return

        text = text[: self.config.max_text_length]
        cached = self.cache.get(text)
        if cached is not None:
            self.last_processed_text = text
            self.last_processed_at = time.monotonic()
            self.show_translation(text, cached, "Translated (cache)")
            self._log("translation served from cache")
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
        self.show_status("Translating...")
        worker = threading.Thread(target=self._translate_worker, args=(text,), daemon=True)
        worker.start()

    def _translate_worker(self, text: str) -> None:
        try:
            translated = self.service.translate(text)
            self.result_queue.put((text, translated, None))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.result_queue.put((text, None, str(exc)))

    def _process_result_queue(self) -> None:
        if not self._running:
            return
        while True:
            try:
                source_text, translated, error = self.result_queue.get_nowait()
            except queue.Empty:
                break

            self.in_flight.pop(source_text, None)
            self.last_processed_text = source_text
            self.last_processed_at = time.monotonic()

            if error is not None:
                self.show_error(source_text, error)
                self._log(f"translation request failed: {error}")
                continue

            if translated is None or not translated.strip():
                self.show_error(source_text, "Empty translation output")
                self._log("translation request failed: empty output")
                continue

            self.cache.set(source_text, translated)
            self.show_translation(source_text, translated, "Translated")
            self._log("translation request succeeded")

        self.root.after(80, self._process_result_queue)

    def translate_now(self) -> None:
        text = self._read_clipboard_text()
        if not text:
            self.show_status("Clipboard has no text.")
            self._log("manual translate skipped: clipboard is empty")
            return
        self._log("manual translate requested")
        self.pending_text = text
        self._process_pending_text(force=True)

    def show_status(self, text: str) -> None:
        self.source_var.set("")
        self._set_translated_display("")
        self.status_var.set(text)
        self.root.update_idletasks()

    def show_translation(self, source_text: str, translated_text: str, status: str) -> None:
        source_preview = source_text if len(source_text) <= 160 else source_text[:157] + "..."
        self.source_var.set(source_preview)
        self._set_translated_display(translated_text)
        self.status_var.set(status)
        self.root.update_idletasks()

    def show_error(self, source_text: str, error_message: str) -> None:
        source_preview = source_text[:160]
        short_error = error_message if len(error_message) <= 120 else error_message[:117] + "..."
        self.source_var.set(source_preview)
        self._set_translated_display("")
        self.status_var.set(f"Translation failed: {short_error}")
        self.root.update_idletasks()

    def run(self) -> int:
        self._log("tkinter UI started")
        self.root.mainloop()
        return 0

    def shutdown(self) -> None:
        if not self._running:
            return
        self._running = False
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

    print("[clipboard-translator] starting tkinter UI...", flush=True)
    try:
        service = TranslatorService(config)
        app = TkTranslatorApp(config, service)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[clipboard-translator] GUI init failed: {exc}", flush=True)
        return 2

    print("[clipboard-translator] app running (terminal stays occupied while active).", flush=True)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
