"""
Backend web du MCP : pilote un navigateur avec Playwright et produit des locators
directement utilisables par Robot Framework Browser library (même moteur Playwright).

Priorité des locators : data-testid > id stable > css name / placeholder > role + nom > texte
> chemin CSS (dernier recours, fragile).

Playwright (API synchrone) tourne dans un thread dédié : le MCP et l'interface web peuvent
l'appeler depuis n'importe quel thread.
"""
from __future__ import annotations

import concurrent.futures
import os
import re
import unicodedata

JS = r"""
(() => {
  if (window.__mcpScan) return;
  const INTER = 'a,button,input,select,textarea,summary,[role],[onclick],[data-testid],[data-test-id],[contenteditable="true"],h1,h2,h3';
  const q = s => String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const uniq = css => { try { return document.querySelectorAll(css).length === 1; } catch (e) { return false; } };
  const stableId = id => /^[A-Za-z][\w-]*$/.test(id) && !/\d{3,}/.test(id);
  window.__mcpDescribe = (el) => {
    const r = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const txt = (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const implicit = {a: 'link', button: 'button', select: 'combobox', textarea: 'textbox'}[tag]
      || (tag === 'input' ? ({checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button'}[type] || 'textbox') : '');
    const role = el.getAttribute('role') || implicit;
    const label = el.labels && el.labels[0] ? el.labels[0].innerText.trim() : '';
    const name = el.getAttribute('aria-label') || label || (['button', 'link', 'tab', 'menuitem'].includes(role) ? txt : '')
      || el.getAttribute('title') || '';
    const testid = el.getAttribute('data-testid') || el.getAttribute('data-test-id') || '';
    const nm = el.getAttribute('name'), ph = el.getAttribute('placeholder');
    const locs = [];
    if (testid) locs.push(['data-testid=' + testid, uniq('[data-testid="' + q(testid) + '"],[data-test-id="' + q(testid) + '"]')]);
    if (el.id && stableId(el.id)) locs.push(['id=' + el.id, uniq('#' + CSS.escape(el.id))]);
    if (nm && ['input', 'select', 'textarea'].includes(tag)) { const c = tag + '[name="' + q(nm) + '"]'; locs.push(['css=' + c, uniq(c)]); }
    if (ph) { const c = '[placeholder="' + q(ph) + '"]'; locs.push(['css=' + c, uniq(c)]); }
    if (role && name && name.length <= 60) locs.push(['role=' + role + '[name="' + q(name) + '"]', null]);
    if (txt && txt.length <= 50 && !['input', 'select', 'textarea'].includes(tag)) locs.push(['text="' + q(txt) + '"', null]);
    if (!locs.length) {
      const p = []; let e = el;
      while (e && e.nodeType === 1 && e !== document.body) {
        let i = 1, s = e; while ((s = s.previousElementSibling)) if (s.tagName === e.tagName) i++;
        p.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + i + ')'); e = e.parentElement;
      }
      locs.push(['css=body > ' + p.join(' > '), true]);
    }
    return {tag, type, role, libelle: name || txt || ph || nm || '', testid, id: el.id || '', name: nm || '',
            locators: locs.map(l => l[0]), unique: locs[0][1], rect: [r.x, r.y, r.width, r.height]};
  };
  window.__mcpScan = (max) => {
    const out = [];
    for (const el of document.querySelectorAll(INTER)) {
      const r = el.getBoundingClientRect(), st = getComputedStyle(el);
      if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
      if (r.bottom < 0 || r.top > innerHeight * 2) continue;
      out.push(window.__mcpDescribe(el));
      if (out.length >= max) break;
    }
    return out;
  };
  window.__mcpAt = (x, y) => {
    const el = document.elementFromPoint(x, y);
    if (!el || el === document.body || el === document.documentElement) return null;
    return window.__mcpDescribe(el.closest(INTER) || el);
  };
})()
"""


def _slug(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or "element"


def _kind(d: dict) -> str:
    role, tag, typ = d.get("role", ""), d.get("tag", ""), d.get("type", "")
    if tag in ("h1", "h2", "h3") or role == "heading":
        return "texte"
    if typ in ("checkbox", "radio") or role in ("checkbox", "radio", "switch"):
        return "case"
    if tag == "select" or role in ("combobox", "listbox"):
        return "liste"
    if role == "textbox" or tag in ("input", "textarea"):
        return "champ"
    if role == "link" or tag == "a":
        return "lien"
    if role in ("button", "tab", "menuitem") or tag == "button":
        return "bouton"
    return "element"


class WebBackend:
    def __init__(self):
        self._ex = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
        self.pw = self.browser = self.page = None

    def _run(self, fn, *args, **kwargs):
        return self._ex.submit(fn, *args, **kwargs).result()

    @property
    def active(self) -> bool:
        return self.page is not None

    def _page(self):
        if self.page is None:
            raise RuntimeError("Aucune session web. Appelle start_session(platform='web', url=...).")
        self.page.evaluate(JS)
        return self.page

    # ------------------------------------------------------------------ session
    def start(self, url: str, browser: str = "chromium", headless: bool = True,
              width: int = 1366, height: int = 768) -> dict:
        return self._run(self._start, url, browser, headless, width, height)

    def _start(self, url, browser, headless, width, height):
        from playwright.sync_api import sync_playwright

        if self.pw is None:
            self.pw = sync_playwright().start()
        if self.browser:
            self.browser.close()
        self.browser = getattr(self.pw, browser).launch(headless=headless)
        ctx = self.browser.new_context(viewport={"width": width, "height": height},
                                       ignore_https_errors=os.environ.get("WEB_IGNORE_HTTPS") == "1")
        self.page = ctx.new_page()
        if url:
            self.page.goto(url, wait_until="domcontentloaded")
        return {"url": self.page.url, "titre": self.page.title()}

    def stop(self):
        def _stop():
            if self.browser:
                self.browser.close()
            self.browser = self.page = None
        self._run(_stop)

    # ------------------------------------------------------------------ lecture
    def screenshot(self) -> bytes:
        return self._run(lambda: self._page().screenshot(type="png"))

    def window(self) -> dict:
        return self._run(lambda: dict(self._page().viewport_size))

    def source(self, max_chars: int) -> str:
        return self._run(lambda: self._page().content()[:max_chars])

    def info(self) -> dict:
        return self._run(lambda: {"url": self._page().url, "titre": self._page().title()})

    def elements(self, max_elements: int = 120) -> list[dict]:
        raw = self._run(lambda: self._page().evaluate(f"window.__mcpScan({int(max_elements)})"))
        return [self._format(d) for d in raw]

    def element_at(self, xr: float, yr: float) -> dict | None:
        def at():
            p = self._page()
            vp = p.viewport_size
            return p.evaluate(f"window.__mcpAt({xr * vp['width']}, {yr * vp['height']})")
        d = self._run(at)
        return self._format(d) if d else None

    def _format(self, d: dict) -> dict:
        kind = _kind(d)
        base = d.get("testid") or (d.get("id") if d["locators"][0].startswith("id=") else "") \
            or d.get("name") or d.get("libelle") or d.get("tag")
        return {"key": f"{kind}_{_slug(base)}", "type": kind, "classe": d.get("tag"),
                "libelle": d.get("libelle", ""), "locators": d["locators"],
                "locator_unique": d.get("unique"), "rect": d.get("rect")}

    def rect(self, locator: str) -> dict | None:
        def r():
            p = self._page()
            box = p.locator(locator).first.bounding_box(timeout=3000)
            vp = p.viewport_size
            return box and {"x": box["x"] / vp["width"], "y": box["y"] / vp["height"],
                            "w": box["width"] / vp["width"], "h": box["height"] / vp["height"]}
        return self._run(r)

    def check(self, locator: str) -> dict:
        def c():
            loc = self._page().locator(locator)
            n = loc.count()
            info = {"locator": locator, "nb_trouves": n}
            if n:
                first = loc.first
                info.update({"texte": (first.inner_text(timeout=2000) or "")[:200],
                             "affiche": first.is_visible()})
            return info
        return self._run(c)

    # ------------------------------------------------------------------ actions
    def click(self, locator: str, timeout: float):
        self._run(lambda: self._page().locator(locator).first.click(timeout=timeout * 1000))

    def fill(self, locator: str, text: str, clear: bool):
        def f():
            loc = self._page().locator(locator).first
            if clear:
                loc.fill(text)
            else:
                loc.press_sequentially(text)
        self._run(f)

    def press(self, key: str):
        self._run(lambda: self._page().keyboard.press(key))

    def scroll(self, direction: str, ratio: float):
        def s():
            p = self._page()
            vp = p.viewport_size
            dx = {"left": -1, "right": 1}.get(direction, 0) * vp["width"] * ratio
            dy = {"up": 1, "down": -1}.get(direction, 0) * vp["height"] * ratio
            p.mouse.move(vp["width"] / 2, vp["height"] / 2)
            p.mouse.wheel(dx, dy)
        self._run(s)

    def back(self):
        self._run(lambda: self._page().go_back())

    def goto(self, url: str) -> dict:
        def g():
            p = self._page()
            p.goto(url, wait_until="domcontentloaded")
            return {"url": p.url, "titre": p.title()}
        return self._run(g)

    def wait(self, locator: str, timeout: float):
        self._run(lambda: self._page().locator(locator).first.wait_for(state="visible", timeout=timeout * 1000))
