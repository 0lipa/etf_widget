"""
- 한국 ETF: pykrx
- 미국 ETF: yfinance
- 항상 바탕화면 위에 표시 (customtkinter)
- 보유 종목: holdings.json / 위젯 설정: settings.json
"""

import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
import threading
from datetime import datetime, date
import tkinter as tk

def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter 설치 중..."); _install("customtkinter"); import customtkinter as ctk

try:
    import yfinance as yf
except ImportError:
    print("yfinance 설치 중..."); _install("yfinance"); import yfinance as yf

try:
    from pykrx import stock as krx
except ImportError:
    print("pykrx 설치 중..."); _install("pykrx"); from pykrx import stock as krx

ctk.set_appearance_mode("light")

from config import (
    FONT, REFRESH_SECONDS,
    BG, CARD_BG, BORDER,
    TEXT_PRI, TEXT_SEC, TEXT_CODE,
    UP_COLOR, UP_BG, DOWN_COLOR, DOWN_BG, FLAT_COLOR, FLAT_BG,
    FOOTER_BG, BTN_BG, BTN_FG, DOT_RED,
)

HOLDINGS_FILE = Path(__file__).parent / "holdings.json"
SETTINGS_FILE = Path(__file__).parent / "settings.json"


# ── 파일 입출력 ────────────────────────────────────────────────────
def load_holdings() -> list[dict]:
    if not HOLDINGS_FILE.exists():
        return []
    with HOLDINGS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_holding(entry: dict):
    holdings = load_holdings()
    holdings.append(entry)
    with HOLDINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

def delete_holding(ticker: str, market: str):
    holdings = [h for h in load_holdings()
                if not (h["ticker"] == ticker and h["market"] == market)]
    with HOLDINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    with SETTINGS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(data: dict):
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 시장 개장 여부 ─────────────────────────────────────────────────
def market_status(markets: set[str]) -> str:
    parts = []
    if "KRX" in markets:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        if now.weekday() >= 5:
            parts.append("KRX 휴장")
        else:
            o = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
            c = now.replace(hour=15, minute=30, second=0, microsecond=0)
            parts.append("KRX 장중" if o <= now <= c else "KRX 마감")
    if "US" in markets:
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            parts.append("US 휴장")
        else:
            o = now.replace(hour=9,  minute=30, second=0, microsecond=0)
            c = now.replace(hour=16, minute=0,  second=0, microsecond=0)
            parts.append("US 장중" if o <= now <= c else "US 마감")
    return "  ·  ".join(parts)


# ── 가격 조회 ─────────────────────────────────────────────────────
def get_krx_price(ticker: str) -> float | None:
    try:
        today = date.today().strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(
            fromdate=(date.today().replace(day=1)).strftime("%Y%m%d"),
            todate=today, ticker=ticker,
        )
        if df is None or df.empty:
            return None
        return float(df["종가"].iloc[-1])
    except Exception as e:
        print(f"[KRX 오류] {ticker}: {e}"); return None

def get_us_price(ticker: str) -> float | None:
    try:
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        return float(price) if price else None
    except Exception as e:
        print(f"[US 오류] {ticker}: {e}"); return None

def fetch_prices() -> list[dict]:
    holdings = load_holdings()
    groups: dict[tuple, dict] = {}
    for h in holdings:
        key = (h["ticker"], h["market"])
        if key not in groups:
            groups[key] = {"name": h["name"], "ticker": h["ticker"],
                           "market": h["market"], "lots": []}
        groups[key]["lots"].append({"buy_price": h["buy_price"], "quantity": h["quantity"]})

    results = []
    for (ticker, market), g in groups.items():
        lots       = g["lots"]
        total_qty  = sum(l["quantity"] for l in lots)
        total_cost = sum(l["buy_price"] * l["quantity"] for l in lots)
        avg_buy    = total_cost / total_qty
        n_lots     = len(lots)
        if market == "KRX":
            current = get_krx_price(ticker)
            fmt = lambda v: f"₩{v:,.0f}"
        else:
            current = get_us_price(ticker)
            fmt = lambda v: f"${v:,.2f}"
        base = {"name": g["name"], "ticker": ticker, "market": market,
                "buy_price": avg_buy, "quantity": total_qty, "n_lots": n_lots, "fmt": fmt}
        if current is None:
            results.append({**base, "current": None, "pct": None, "pl": None, "total_pl": None})
            continue
        pct      = (current - avg_buy) / avg_buy * 100
        pl       = current - avg_buy
        total_pl = current * total_qty - total_cost
        results.append({**base, "current": current, "pct": pct, "pl": pl, "total_pl": total_pl})
    return results


# ── 폰트 헬퍼 ─────────────────────────────────────────────────────
def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


# ── 삭제 확인 다이얼로그 ──────────────────────────────────────────────
class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, message: str, on_confirm):
        super().__init__(parent)
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self.after(50, lambda: (self.lift(), self.focus_force()))

        ctk.CTkLabel(self, text=message, fg_color="transparent",
                      text_color=TEXT_PRI, font=F(12),
                      wraplength=220).pack(padx=24, pady=(20, 16))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=24, pady=(0, 20))

        ctk.CTkButton(row, text="취소", width=90, height=32, corner_radius=10,
                       fg_color=BTN_BG, hover_color=BORDER, text_color=BTN_FG,
                       font=F(11), command=self.destroy).pack(side="left", padx=(0, 8))

        def _go():
            self.destroy()
            on_confirm()

        ctk.CTkButton(row, text="삭제", width=90, height=32, corner_radius=10,
                       fg_color=DOWN_COLOR, hover_color="#A03020", text_color="#FFFFFF",
                       font=F(11, True), command=_go).pack(side="left")


def _search_yfinance(q: str, max_results: int = 7) -> list[tuple[str, str]]:
    try:
        hits = [
            (r.get("symbol", ""), r.get("shortname") or r.get("longname", ""))
            for r in yf.Search(q, max_results=max_results).quotes
            if r.get("symbol")
        ]
        return hits
    except Exception as e:
        print(f"[yfinance 검색 오류] {e}")
        return []


# ── 종목 추가 다이얼로그 ──────────────────────────────────────────────
class AddDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_save, prefill=None):
        super().__init__(parent)
        self.on_save = on_save
        self.title("종목 추가")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.minsize(380, 0)
        self.attributes("-topmost", True)
        self.grab_set()
        self.after(50, lambda: (self.lift(), self.focus_force()))

        self._ticker = ""
        self._name   = ""
        self._us_job = None

        # ── 헤더
        ctk.CTkLabel(self, text="종목 추가", fg_color="transparent",
                      text_color=TEXT_PRI, font=F(15, True)).pack(
                      anchor="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(self, text="보유 ETF 포지션을 입력하세요", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(
                      anchor="w", padx=24, pady=(0, 16))

        # ── 시장 선택
        mkt = ctk.CTkFrame(self, fg_color="transparent")
        mkt.pack(fill="x", padx=24, pady=(0, 12))
        ctk.CTkLabel(mkt, text="시장", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(anchor="w", pady=(0, 4))
        self._market_var = tk.StringVar(value="KRX")
        ctk.CTkSegmentedButton(
            mkt, values=["KRX", "US"], variable=self._market_var,
            font=F(12, True), height=38, corner_radius=10,
            fg_color=CARD_BG,
            selected_color=UP_COLOR, selected_hover_color="#166039",
            unselected_color=CARD_BG, unselected_hover_color=BORDER,
            text_color=TEXT_PRI,
            command=self._on_market_change,
        ).pack(fill="x")

        # ── 종목 검색
        src_wrap = ctk.CTkFrame(self, fg_color="transparent")
        src_wrap.pack(fill="x", padx=24, pady=(0, 0))
        ctk.CTkLabel(src_wrap, text="종목 검색", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(anchor="w", pady=(0, 4))
        self._q_var = tk.StringVar()
        self._q_var.trace_add("write", self._on_q_change)
        self._q_entry = ctk.CTkEntry(
            src_wrap, textvariable=self._q_var,
            fg_color=CARD_BG, text_color=TEXT_PRI, border_color=BORDER,
            corner_radius=10, font=F(12), height=38,
            placeholder_text="종목명 또는 코드 입력...",
        )
        self._q_entry.pack(fill="x")

        # ── 드롭다운 (동적 삽입, 초기엔 pack 안 함)
        self._dd = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10,
                                 border_width=1, border_color=BORDER)

        # ── 선택 배지 (동적 삽입, 초기엔 pack 안 함)
        self._sel_frame = ctk.CTkFrame(self, fg_color=UP_BG, corner_radius=8)
        self._sel_lbl = ctk.CTkLabel(
            self._sel_frame, text="", fg_color="transparent",
            text_color=UP_COLOR, font=F(11, True),
        )
        self._sel_lbl.pack(side="left", padx=(12, 4), pady=8)
        ctk.CTkButton(
            self._sel_frame, text="×", width=22, height=22, corner_radius=11,
            fg_color="transparent", hover_color=UP_BG, text_color=UP_COLOR,
            font=F(12, True),
            command=lambda: (self._clear_selection(), self._q_var.set("")),
        ).pack(side="right", padx=(0, 8), pady=8)

        # ── 매입 단가 (before= 기준점)
        self._price_wrap = ctk.CTkFrame(self, fg_color="transparent")
        self._price_wrap.pack(fill="x", padx=24, pady=(12, 10))
        ctk.CTkLabel(self._price_wrap, text="매입 단가", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(anchor="w", pady=(0, 4))
        self._price_var = tk.StringVar()
        self._price_entry = ctk.CTkEntry(
            self._price_wrap, textvariable=self._price_var,
            fg_color=CARD_BG, text_color=TEXT_PRI, border_color=BORDER,
            corner_radius=10, font=F(12), height=38,
        )
        self._price_entry.pack(fill="x")

        # ── 수량
        qty_wrap = ctk.CTkFrame(self, fg_color="transparent")
        qty_wrap.pack(fill="x", padx=24, pady=(0, 10))
        ctk.CTkLabel(qty_wrap, text="수량", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(anchor="w", pady=(0, 4))
        self._qty_var = tk.StringVar()
        ctk.CTkEntry(qty_wrap, textvariable=self._qty_var,
                      fg_color=CARD_BG, text_color=TEXT_PRI, border_color=BORDER,
                      corner_radius=10, font=F(12), height=38).pack(fill="x")

        # ── 에러
        self._err_lbl = ctk.CTkLabel(self, text="", fg_color="transparent",
                                      text_color=DOWN_COLOR, font=F(9))
        self._err_lbl.pack(pady=(2, 6), padx=24, anchor="w")

        # ── 버튼
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 22))
        ctk.CTkButton(btn_row, text="취소", height=40, corner_radius=12,
                       fg_color=BTN_BG, hover_color=BORDER, text_color=BTN_FG,
                       font=F(12, True), command=self.destroy).pack(
                       side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(btn_row, text="저장", height=40, corner_radius=12,
                       fg_color=UP_COLOR, hover_color="#166039", text_color="#FFFFFF",
                       font=F(12, True), command=self._save).pack(
                       side="left", expand=True, fill="x")
        self.bind("<Return>", lambda e: self._save())

        if prefill:
            self._market_var.set(prefill.get("market", "KRX"))
            self._price_var.set(str(prefill.get("buy_price", "")))
            self._qty_var.set(str(prefill.get("quantity", "")))
            if prefill.get("ticker") and prefill.get("name"):
                self._pick(prefill["ticker"], prefill["name"])

    # ── 시장 변경
    def _on_market_change(self, _=None):
        self._clear_selection()
        self._q_var.set("")
        self._hide_dd()

    # ── 검색어 변경
    def _on_q_change(self, *_):
        q = self._q_var.get().strip()
        if self._ticker and q == f"{self._ticker}  {self._name}":
            return
        if self._ticker:
            self._ticker = ""
            self._name   = ""
            if self._sel_frame.winfo_ismapped():
                self._sel_frame.pack_forget()
        if not q:
            self._hide_dd(); return
        self._debounce_search(q)

    def _debounce_search(self, q):
        if self._us_job:
            self.after_cancel(self._us_job)
        if len(q) < 1:
            self._hide_dd(); return
        self._show_status("검색 중...")
        self._us_job = self.after(400, lambda: self._fetch(q))

    def _fetch(self, q):
        market = self._market_var.get()
        def worker():
            hits = _search_yfinance(q)
            # KRX 선택 시 한국 종목(.KS/.KQ)만 필터링, 없으면 전체 표시
            if market == "KRX":
                krx_hits = [(s, n) for s, n in hits if s.endswith(".KS") or s.endswith(".KQ")]
                hits = krx_hits if krx_hits else hits
            self.after(0, lambda: self._show_dd(hits))
        threading.Thread(target=worker, daemon=True).start()

    # ── 드롭다운 표시/숨김
    def _show_dd(self, hits):
        for w in self._dd.winfo_children():
            w.destroy()
        if not hits:
            self._show_status("검색 결과 없음"); return
        for ticker, name in hits:
            label = f"{ticker}  {name}" if name else ticker
            ctk.CTkButton(
                self._dd, text=label, anchor="w", height=34,
                fg_color="transparent", hover_color=BORDER,
                text_color=TEXT_PRI, font=F(11), corner_radius=6,
                command=lambda t=ticker, n=name: self._pick(t, n),
            ).pack(fill="x", padx=6, pady=2)
        self._mount_dd()

    def _show_status(self, msg: str):
        for w in self._dd.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._dd, text=msg, fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10)).pack(padx=12, pady=10, anchor="w")
        self._mount_dd()

    def _mount_dd(self):
        if not self._dd.winfo_ismapped():
            try:
                self._dd.pack(fill="x", padx=24, pady=(4, 0), before=self._price_wrap)
            except Exception:
                self._dd.pack(fill="x", padx=24, pady=(4, 0))

    def _hide_dd(self):
        if self._dd.winfo_ismapped():
            self._dd.pack_forget()

    # ── 종목 선택
    def _pick(self, ticker, name):
        self._ticker = ticker
        self._name   = name
        self._q_var.set(f"{ticker}  {name}")
        self._hide_dd()
        self._sel_lbl.configure(text=f"✓  {ticker}  {name}")
        if not self._sel_frame.winfo_ismapped():
            self._sel_frame.pack(fill="x", padx=24, pady=(4, 0), before=self._price_wrap)
        self._price_entry.focus_set()

    def _clear_selection(self):
        self._ticker = ""
        self._name   = ""
        if self._sel_frame.winfo_ismapped():
            self._sel_frame.pack_forget()

    # ── 저장
    def _save(self):
        if not self._ticker or not self._name:
            self._err_lbl.configure(text="종목을 검색해서 선택해주세요."); return
        market = self._market_var.get()
        try:
            buy_price = float(self._price_var.get().replace(",", ""))
            quantity  = int(self._qty_var.get().replace(",", ""))
        except ValueError:
            self._err_lbl.configure(text="단가와 수량을 올바르게 입력해주세요."); return
        if buy_price <= 0 or quantity <= 0:
            self._err_lbl.configure(text="단가와 수량은 0보다 커야 합니다."); return
        self.on_save({"name": self._name, "ticker": self._ticker, "market": market,
                      "buy_price": buy_price, "quantity": quantity})
        self.destroy()


# ── 위젯 ──────────────────────────────────────────────────────────
class ETFWidget:
    WIDTH = 340

    def __init__(self, root: ctk.CTk):
        self.root = root
        self._drag_x = self._drag_y = 0
        self._collapsed = False
        self._editing   = False
        self._card_widgets: list[dict] = []
        self._last_results: list[dict] = []
        self._setup_window()
        self._build_ui()
        self._refresh_data()

    def _setup_window(self):
        r = self.root
        r.title("ETF Widget")
        r.configure(fg_color=BG)
        r.resizable(False, False)
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", 0.97)
        s = load_settings()
        if "window_x" in s and "window_y" in s:
            r.geometry(f"+{s['window_x']}+{s['window_y']}")
        else:
            r.geometry(f"+{r.winfo_screenwidth() - self.WIDTH - 24}+64")

    def _close(self):
        s = load_settings()
        s["window_x"] = self.root.winfo_x()
        s["window_y"] = self.root.winfo_y()
        save_settings(s)
        self.root.destroy()

    def _bind_drag(self, w):
        w.bind("<ButtonPress-1>", self._drag_start)
        w.bind("<B1-Motion>",     self._drag_move)

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _build_ui(self):
        # ── 헤더 ────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.root, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 8))
        self._bind_drag(hdr)

        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        self._bind_drag(left)

        t = ctk.CTkLabel(left, text="ETF 위젯", fg_color="transparent",
                          text_color=TEXT_PRI, font=F(13, True), anchor="w")
        t.pack(anchor="w")
        self._bind_drag(t)

        self._subtitle_lbl = ctk.CTkLabel(left, text="— 개 종목 추적 중",
                                           fg_color="transparent", text_color=TEXT_SEC,
                                           font=F(10), anchor="w")
        self._subtitle_lbl.pack(anchor="w")
        self._bind_drag(self._subtitle_lbl)

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right")

        ctk.CTkButton(right, text="+", width=28, height=28, corner_radius=14,
                       fg_color=UP_COLOR, hover_color="#166039", text_color="#FFFFFF",
                       font=F(15, True), command=self._open_add_dialog
                       ).pack(side="left", padx=(0, 5))

        self._edit_btn = ctk.CTkButton(
            right, text="−", width=28, height=28, corner_radius=14,
            fg_color=BTN_BG, hover_color=BORDER, text_color=BTN_FG,
            font=F(15, True), command=self._toggle_edit,
        )
        self._edit_btn.pack(side="left", padx=(0, 5))

        self._toggle_btn = ctk.CTkButton(
            right, text="접기", width=46, height=28, corner_radius=14,
            fg_color=BTN_BG, hover_color=BORDER, text_color=BTN_FG,
            font=F(10, True), command=self._toggle,
        )
        self._toggle_btn.pack(side="left", padx=(0, 5))

        ctk.CTkButton(right, text="×", width=28, height=28, corner_radius=14,
                       fg_color="transparent", hover_color=BORDER, text_color=TEXT_SEC,
                       font=F(14), command=self._close,
                       ).pack(side="left")

        # ── 포트폴리오 요약 ──────────────────────────────────
        self._summary_outer = ctk.CTkFrame(self.root, fg_color="transparent")
        self._summary_outer.pack(fill="x", padx=10, pady=(0, 4))

        # ── 카드 컨테이너 ────────────────────────────────────
        self.container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=10)

        # ── 푸터 ────────────────────────────────────────────
        footer = ctk.CTkFrame(self.root, fg_color=FOOTER_BG, corner_radius=12)
        footer.pack(fill="x", padx=10, pady=(4, 12))

        self._status_lbl = ctk.CTkLabel(
            footer, text="갱신: --:--:--  ·  60s마다 자동 갱신",
            fg_color="transparent", text_color=TEXT_SEC, font=F(9),
        )
        self._status_lbl.pack(pady=8, padx=14, anchor="w")

    # ── 액션 ──────────────────────────────────────────────────────
    def _open_add_dialog(self):
        AddDialog(self.root, on_save=self._on_holding_saved)

    def _on_holding_saved(self, entry: dict):
        save_holding(entry)
        self._async_refresh(force_rebuild=True)

    def _on_holding_deleted(self, ticker: str, market: str, name: str):
        def do_delete():
            delete_holding(ticker, market)
            self._async_refresh(force_rebuild=True)
        ConfirmDialog(self.root, f"'{name}' 포지션을\n삭제할까요?", on_confirm=do_delete)

    def _async_refresh(self, force_rebuild: bool = False):
        def worker():
            results = fetch_prices()
            self.root.after(0, lambda: self._update_ui(results, force_rebuild))
        threading.Thread(target=worker, daemon=True).start()

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._toggle_btn.configure(text="펼치기" if self._collapsed else "접기")
        self._rebuild_cards(self._last_results)

    def _toggle_edit(self):
        self._editing = not self._editing
        if self._editing:
            self._edit_btn.configure(fg_color=DOT_RED, hover_color="#D06050",
                                      text_color="#FFFFFF")
        else:
            self._edit_btn.configure(fg_color=BTN_BG, hover_color=BORDER,
                                      text_color=BTN_FG)
        self._rebuild_cards(self._last_results)

    # ── 카드 ──────────────────────────────────────────────────────
    def _make_card(self, parent, result: dict) -> dict:
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="x", pady=4)

        ticker = result["ticker"]
        market = result["market"]
        name   = result["name"]
        w      = {"outer": card}

        if self._collapsed:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=11)

            name_lbl = ctk.CTkLabel(row, text="", fg_color="transparent",
                                     text_color=TEXT_PRI, font=F(12, True), anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)

            right = ctk.CTkFrame(row, fg_color="transparent")
            right.pack(side="right")

            badge = ctk.CTkLabel(right, text="", fg_color=FLAT_BG, text_color=FLAT_COLOR,
                                  corner_radius=8, font=F(11, True), padx=6, pady=4)
            badge.pack(side="left")

            if self._editing:
                ctk.CTkButton(
                    right, text="×", width=26, height=26, corner_radius=13,
                    fg_color=DOWN_BG, hover_color=DOWN_COLOR, text_color=DOWN_COLOR,
                    font=F(13, True),
                    command=lambda t=ticker, m=market, n=name:
                        self._on_holding_deleted(t, m, n),
                ).pack(side="left", padx=(6, 0))

            w.update({"name": name_lbl, "badge": badge})

        else:
            pad = ctk.CTkFrame(card, fg_color="transparent")
            pad.pack(fill="x", padx=14, pady=13)

            top = ctk.CTkFrame(pad, fg_color="transparent")
            top.pack(fill="x", pady=(0, 8))

            name_area = ctk.CTkFrame(top, fg_color="transparent")
            name_area.pack(side="left", fill="x", expand=True)

            name_lbl = ctk.CTkLabel(name_area, text="", fg_color="transparent",
                                     text_color=TEXT_PRI, font=F(13, True), anchor="w")
            name_lbl.pack(anchor="w")

            code_lbl = ctk.CTkLabel(name_area, text="", fg_color="transparent",
                                     text_color=TEXT_CODE, font=F(10), anchor="w")
            code_lbl.pack(anchor="w")

            right_area = ctk.CTkFrame(top, fg_color="transparent")
            right_area.pack(side="right", anchor="n")

            badge = ctk.CTkLabel(right_area, text="", fg_color=FLAT_BG, text_color=FLAT_COLOR,
                                  corner_radius=8, font=F(12, True), padx=10, pady=5)
            badge.pack(anchor="e")

            if self._editing:
                ctk.CTkButton(
                    right_area, text="× 삭제", width=66, height=26, corner_radius=8,
                    fg_color=DOWN_BG, hover_color=DOWN_COLOR, text_color=DOWN_COLOR,
                    font=F(9, True),
                    command=lambda t=ticker, m=market, n=name:
                        self._on_holding_deleted(t, m, n),
                ).pack(anchor="e", pady=(6, 0))

            price_lbl = ctk.CTkLabel(pad, text="", fg_color="transparent",
                                      text_color=TEXT_PRI, font=F(22, True), anchor="w")
            price_lbl.pack(anchor="w", pady=(0, 8))

            chips = ctk.CTkFrame(pad, fg_color="transparent")
            chips.pack(anchor="w", fill="x")

            buy_chip = ctk.CTkLabel(chips, text="", fg_color=BORDER, text_color=TEXT_SEC,
                                     corner_radius=6, font=F(9), padx=8, pady=3)
            buy_chip.pack(side="left", padx=(0, 4))

            per_chip = ctk.CTkLabel(chips, text="", fg_color=FLAT_BG, text_color=FLAT_COLOR,
                                     corner_radius=6, font=F(9, True), padx=8, pady=3)
            per_chip.pack(side="left", padx=(0, 4))

            total_chip = ctk.CTkLabel(chips, text="", fg_color=FLAT_BG, text_color=FLAT_COLOR,
                                       corner_radius=6, font=F(9, True), padx=8, pady=3)
            total_chip.pack(side="left")

            w.update({
                "name": name_lbl, "code": code_lbl, "badge": badge,
                "price": price_lbl,
                "buy_chip": buy_chip, "per_chip": per_chip, "total_chip": total_chip,
            })

        return w

    def _rebuild_cards(self, results: list[dict]):
        for child in self.container.winfo_children():
            child.destroy()
        self._card_widgets = [self._make_card(self.container, r) for r in results]
        self._fill_cards(results)

    def _fill_summary(self, results: list[dict]):
        for child in self._summary_outer.winfo_children():
            child.destroy()

        valid = [r for r in results if r["current"] is not None]
        if not valid:
            return

        by_market: dict[str, dict] = {}
        for r in valid:
            m = r["market"]
            if m not in by_market:
                by_market[m] = {"invested": 0.0, "current_val": 0.0}
            by_market[m]["invested"]    += r["buy_price"] * r["quantity"]
            by_market[m]["current_val"] += r["current"]   * r["quantity"]
        for s in by_market.values():
            s["total_pl"] = s["current_val"] - s["invested"]
            s["pct"]      = s["total_pl"] / s["invested"] * 100 if s["invested"] > 0 else 0

        card = ctk.CTkFrame(self._summary_outer, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="x", pady=4)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=14, pady=13)

        ctk.CTkLabel(content, text="포트폴리오 요약", fg_color="transparent",
                      text_color=TEXT_SEC, font=F(10), anchor="w").pack(
                      anchor="w", pady=(0, 8))

        markets_list = list(by_market.items())
        for i, (m, s) in enumerate(markets_list):
            fmt  = (lambda v: f"₩{v:,.0f}") if m == "KRX" else (lambda v: f"${v:,.2f}")
            c_fg = UP_COLOR if s["total_pl"] > 0 else (DOWN_COLOR if s["total_pl"] < 0 else FLAT_COLOR)
            c_bg = UP_BG    if s["total_pl"] > 0 else (DOWN_BG    if s["total_pl"] < 0 else FLAT_BG)
            sp   = "+" if s["total_pl"] >= 0 else ""
            sp_p = "+" if s["pct"]      >= 0 else ""

            ctk.CTkLabel(content, text=m, fg_color="transparent",
                          text_color=TEXT_SEC, font=F(10, True), anchor="w").pack(anchor="w")

            ctk.CTkLabel(content, text=fmt(s["current_val"]), fg_color="transparent",
                          text_color=TEXT_PRI, font=F(20, True), anchor="w").pack(
                          anchor="w", pady=(2, 5))

            row = ctk.CTkFrame(content, fg_color="transparent")
            row.pack(anchor="w", pady=(0, 2))
            ctk.CTkLabel(row,
                          text=f"{sp}{fmt(s['total_pl'])}  ({sp_p}{s['pct']:.2f}%)",
                          fg_color=c_bg, text_color=c_fg, corner_radius=8,
                          font=F(11, True), padx=8, pady=3).pack(side="left")

            bot = (4, 12) if i < len(markets_list) - 1 else (4, 0)
            ctk.CTkLabel(content, text=f"투자 {fmt(s['invested'])}", fg_color="transparent",
                          text_color=TEXT_SEC, font=F(10), anchor="w").pack(
                          anchor="w", pady=bot)

    def _refresh_data(self):
        def worker():
            results = fetch_prices()
            self.root.after(0, lambda: self._update_ui(results))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(REFRESH_SECONDS * 1000, self._refresh_data)

    def _update_ui(self, results: list[dict], force_rebuild: bool = False):
        self._last_results = results
        self._subtitle_lbl.configure(text=f"{len(results)}개 종목 추적 중")
        if force_rebuild or len(self._card_widgets) != len(results):
            self._rebuild_cards(results)
        else:
            self._fill_cards(results)
        self._fill_summary(results)

    def _fill_cards(self, results: list[dict]):
        for w, r in zip(self._card_widgets, results):
            name   = r.get("name", r["ticker"])
            n_lots = r.get("n_lots", 1)

            if r["current"] is None:
                w["name"].configure(text=name)
                w["badge"].configure(text="조회 실패", fg_color=FLAT_BG, text_color=FLAT_COLOR)
                if not self._collapsed:
                    w["code"].configure(text=r["ticker"])
                    w["price"].configure(text="—", text_color=TEXT_SEC)
                    w["buy_chip"].configure(text="매입 —",  fg_color=BORDER,  text_color=TEXT_SEC)
                    w["per_chip"].configure(text="주당 —",  fg_color=FLAT_BG, text_color=FLAT_COLOR)
                    w["total_chip"].configure(text="총 —",  fg_color=FLAT_BG, text_color=FLAT_COLOR)
                continue

            pct   = r["pct"]
            fmt   = r["fmt"]
            up    = pct > 0
            c_fg  = UP_COLOR  if up else (DOWN_COLOR  if pct < 0 else FLAT_COLOR)
            c_bg  = UP_BG     if up else (DOWN_BG     if pct < 0 else FLAT_BG)
            arrow = "▲" if up else ("▼" if pct < 0 else "—")

            w["name"].configure(text=name)
            w["badge"].configure(text=f"{arrow} {'+' if up else ''}{pct:.2f}%",
                                  fg_color=c_bg, text_color=c_fg)

            if not self._collapsed:
                lot_suffix = f"  ·  {n_lots}회 매수" if n_lots > 1 else ""
                w["code"].configure(text=f"{r['ticker']}{lot_suffix}")
                w["price"].configure(text=fmt(r["current"]), text_color=TEXT_PRI)
                avg_label = "평균 매입" if n_lots > 1 else "매입"
                sp = "+" if r["pl"] >= 0 else ""
                st = "+" if r["total_pl"] >= 0 else ""
                w["buy_chip"].configure(text=f"{avg_label} {fmt(r['buy_price'])}",
                                        fg_color=BORDER, text_color=TEXT_SEC)
                w["per_chip"].configure(text=f"주당 {sp}{fmt(r['pl'])}",
                                        fg_color=c_bg, text_color=c_fg)
                w["total_chip"].configure(text=f"총 {st}{fmt(r['total_pl'])}",
                                          fg_color=c_bg, text_color=c_fg)

        markets_in_use = {r["market"] for r in results}
        mkt     = market_status(markets_in_use)
        mkt_sep = f"  ·  {mkt}" if mkt else ""
        now = datetime.now().strftime("%H:%M:%S")
        self._status_lbl.configure(
            text=f"갱신: {now}{mkt_sep}  ·  {REFRESH_SECONDS}s마다 자동 갱신")


if __name__ == "__main__":
    root = ctk.CTk()
    ETFWidget(root)
    root.mainloop()
