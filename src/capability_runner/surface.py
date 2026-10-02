"""Surface port. Browser mechanics and perception never live in capability steps."""
from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import hashlib
import json
from typing import Any
import uuid
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, async_playwright

from .policy import Policy, PolicyViolation
from .profile import HANDLERS, SAFE_TEXT, SCREENS, TARGETS
from .schema import Action, ControlObservation, Observation, TargetSpec
from .settings import Settings


class SurfaceError(Exception):
    def __init__(self, code: str, target: str | None = None):
        self.code, self.target = code, target
        super().__init__(code)


class Surface(ABC):
    session_id: str

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def observe(self) -> Observation: ...

    @abstractmethod
    async def act(self, action: Action, inputs: dict[str, Any], actor: str = "automation") -> Any: ...

    @abstractmethod
    async def snapshot(self) -> dict: ...

    @abstractmethod
    async def screenshot(self) -> bytes: ...

    @abstractmethod
    async def close(self) -> None: ...


class BrowserSurface(Surface):
    def __init__(self, settings: Settings, policy: Policy, target_url: str):
        if not policy.allows_url(target_url):
            raise PolicyViolation("TARGET_DENIED")
        self.settings, self.policy, self.target_url = settings, policy, target_url
        self.session_id = uuid.uuid4().hex
        self.playwright = self.browser = self.context = self.page = None
        self.network_denied = False
        self.dialog_seen = False

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        try:
            options = {"headless": self.settings.headless}
            if self.settings.chromium_executable:
                options["executable_path"] = self.settings.chromium_executable
            self.browser = await self.playwright.chromium.launch(**options)
            self.context = await self.browser.new_context(
                viewport={"width": 1180, "height": 900}, accept_downloads=False,
                service_workers="block", locale="en-US", timezone_id="UTC",
            )
            self.context.set_default_timeout(self.settings.action_timeout_ms)

            async def guard(route):
                if self.policy.allows_url(route.request.url, route.request.method):
                    await route.continue_()
                else:
                    if not route.request.url.endswith("/favicon.ico"):
                        self.network_denied = True
                    await route.abort("blockedbyclient")

            async def block_socket(socket):
                self.network_denied = True
                await socket.close()

            await self.context.route("**/*", guard)
            await self.context.route_web_socket("**/*", block_socket)
            self.page = await self.context.new_page()

            async def dialog_handler(dialog):
                self.dialog_seen = True
                await dialog.dismiss()  # Never accept an unknown native confirmation.

            async def popup_handler(popup):
                self.network_denied = True
                await popup.close()

            self.page.on("dialog", dialog_handler)
            self.page.on("popup", popup_handler)
            self.page.on("download", lambda item: asyncio.create_task(item.cancel()))
        except BaseException:
            await self.close()
            raise

    def locator(self, target: TargetSpec, spec):
        root = self.page
        for title in target.frames:
            # Titles are fixed, reviewed binding data, not model-supplied selectors.
            root = root.frame_locator('iframe[title=' + json.dumps(title) + ']')
        if spec.strategy == "label":
            locator = root.get_by_label(spec.value, exact=True)
        elif spec.strategy == "role":
            locator = root.get_by_role(spec.role, name=spec.value, exact=True)
        elif spec.strategy == "text":
            locator = root.get_by_text(spec.value, exact=True)
        elif spec.strategy == "table_input":
            locator = root.get_by_text(spec.value, exact=True).locator("xpath=ancestor::tr[1]//input[not(@type='hidden')]")
        else:
            locator = root.get_by_text(spec.value, exact=True).locator("xpath=ancestor::tr[1]/td[2]")
        return locator.filter(visible=True)

    async def resolve(self, key: str):
        target = TARGETS[key]
        for spec in target.locators:
            locator = self.locator(target, spec)
            count = await locator.count()
            if count > 1:
                raise SurfaceError("AMBIGUOUS_TARGET", key)
            if count == 1:
                return locator
        raise SurfaceError("TARGET_MISSING", key)

    async def observe(self) -> Observation:
        if not self.page:
            raise SurfaceError("SESSION_UNAVAILABLE")
        controls, signals = [], []
        screen = "unknown"
        version_ok = False
        for key, target in TARGETS.items():
            populated = False
            try:
                locator = await self.resolve(key)
                enabled = await locator.is_enabled()
                matches = 1
                if target.action == "fill":
                    populated = bool(await locator.input_value())
            except SurfaceError as error:
                matches = 2 if error.code == "AMBIGUOUS_TARGET" else 0
                enabled = False
            except PlaywrightError:
                matches, enabled = 0, False
            if key == "version_marker":
                version_ok = matches == 1
            elif key in SCREENS and matches == 1:
                screen = SCREENS[key]
            elif target.action == "signal" and matches:
                signals.append(key)
            elif target.action != "signal" and matches:
                controls.append(ControlObservation(key=key, matches=matches, enabled=enabled, populated=populated))
        if self.network_denied:
            signals.append("network_denied")
        if self.dialog_seen and "unexpected_dialog" not in signals:
            signals.append("unexpected_dialog")
        data = {"screen": screen, "signals": sorted(signals),
                "controls": [control.model_dump() for control in controls], "app_version_ok": version_ok}
        return Observation(**data, digest=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())

    async def act(self, action: Action, inputs: dict[str, Any], actor: str = "automation") -> Any:
        self.policy.check_action(action, self.settings.target_origin, actor)
        if self.network_denied:
            raise SurfaceError("NETWORK_POLICY_DENIED")
        try:
            if action.kind == "navigate":
                # Only the trusted invocation entry carries a fault-injection scenario.
                url = self.target_url if action.path == "/legacy" else self.settings.target_origin + action.path
                if self.target_url.startswith("sandbox://"):
                    if action.path != "/legacy":
                        raise PolicyViolation("TARGET_DENIED")
                    from .sandbox import sandbox_html
                    scenario = parse_qs(urlsplit(self.target_url).query).get("scenario", ["normal"])[0]
                    await self.page.set_content(sandbox_html(scenario), wait_until="load", timeout=self.settings.action_timeout_ms)
                else:
                    await self.page.goto(url, wait_until="load", timeout=self.settings.action_timeout_ms)
                return None
            locator = await self.resolve(action.target)
            if action.kind == "fill":
                await locator.fill(str(inputs[action.parameter]))
            elif action.kind == "click":
                await locator.click()
                if action.target == "acknowledge_warning" and actor == "human":
                    self.dialog_seen = False
            else:
                return (await locator.inner_text()).strip()
        except PlaywrightTimeout as error:
            raise SurfaceError("ACTION_TIMEOUT", action.target) from error
        except PlaywrightError as error:
            raise SurfaceError("SURFACE_ERROR", action.target) from error
        return None

    async def snapshot(self) -> dict:
        """A structural DOM snapshot, not raw HTML. No attributes or input values are retained.

        All unreviewed text becomes [REDACTED]. Bounding boxes retain useful failure evidence
        even when the page contains unknown sensitive fields. Never write raw screenshots.
        """
        frames = []
        if self.page:
            for index, frame in enumerate(self.page.frames):
                try:
                    nodes = await frame.evaluate("""(safe) => {
                        const allowed = new Set(safe);
                        return Array.from(document.body.querySelectorAll('*')).slice(0, 500).map(el => {
                            const rect = el.getBoundingClientRect();
                            const ownText = Array.from(el.childNodes).filter(n => n.nodeType === 3)
                                .map(n => n.textContent.trim()).filter(Boolean).join(' ');
                            return {tag:el.tagName.toLowerCase(), text:ownText ? (allowed.has(ownText) ? ownText : '[REDACTED]') : '',
                                x:Math.round(rect.x), y:Math.round(rect.y), width:Math.round(rect.width), height:Math.round(rect.height)};
                        });
                    }""", sorted(SAFE_TEXT))
                except PlaywrightError:
                    nodes = [{"state": "unavailable"}]
                frames.append({"index": index, "nodes": nodes})
        return {"format": "redacted-dom-v1", "session_id": self.session_id, "frames": frames}

    async def screenshot(self) -> bytes:
        if not self.page:
            raise SurfaceError("SESSION_UNAVAILABLE")
        return await self.page.screenshot(type="png", timeout=self.settings.action_timeout_ms)

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        finally:
            if self.playwright:
                await self.playwright.stop()
            self.context = self.browser = self.playwright = self.page = None
