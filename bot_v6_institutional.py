#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🦅 BOT QUANT V6.0 INSTITUTIONAL (STEPPED CPPI + BARBELL FRACTAL-VORTEX)
Fitur Utama:
1. Stepped Fixed-Lot Sizing ($3 -> $6 -> $12 -> $24) + Step-Down Buffer 10%
2. CPPI High-Water Mark (HWM) Profit Lock & Drawdown Cushion (-50% size saat DD >= 8%)
3. Microstructure Anti-Rug Gate (Max DPP <= 0.100, Min Liq >= +3.5%, Anti-Late Entry)
4. Asymmetric Scale-Out Exit (TP-1 +15.0% cair 60%, TP-2 +45.0% cair 50% sisa, Moonbag Trail 9.5%)
5. Multi-Level Cooldown & Circuit Breaker + Live Git Sync 15m + Estafet Sesi Sempurna
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import requests

# ==============================================================================
# KONFIGURASI GLOBAL & PARAMETER SISTEM
# ==============================================================================
INITIAL_EQUITY = 12.50
CHECKPOINT_FILE = "checkpoint_v6.json"
LOG_FILE = "hasil_v6_quant.txt"

SCAN_INTERVAL_SEC = 12            # Interval pemindaian pasar (detik)
LEADERBOARD_INTERVAL_SEC = 180    # Cetak tabel klasemen setiap 3 menit
GIT_SYNC_INTERVAL_SEC = 900       # Push otomatis ke GitHub setiap 15 menit
MAX_SESSION_DURATION_SEC = 19500  # 5 Jam 25 Menit (Aman sebelum limit 6 jam GitHub Actions)

SOL_MINT = "So11111111111111111111111111111111111111112"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantEngine/6.0",
    "Accept": "application/json",
}

# Daftar Tier Alokasi Stagnan Bertingkat (Ide User + Step-Down Buffer 10%)
# Format: (tier_id, syarat_naik_ekuitas, batas_rem_turun_ekuitas, nominal_buy_stagnan)
STEP_TIERS = [
    (4, 96.00, 86.40, 24.00),
    (3, 48.00, 43.20, 12.00),
    (2, 24.00, 21.60, 6.00),
    (1, 12.00, 10.80, 3.00),
]

# Konfigurasi 4 Varian untuk Pembuktian Langsung
VARIANTS_CONFIG = {
    "V6_STEPPED_BARBELL": {
        "mode": "BARBELL",          # Gabungan M4_FRACTAL + VORTEX_MOONBAG
        "sizing": "STEPPED_CPPI",   # Stagnan $3 -> $6 -> $12 + CPPI HWM Lock
        "max_dpp": 0.100,           # Blokir MILO (0.129) & COLLECTINU (0.131)
        "min_liq": 3.5,             # Minimal pertumbuhan likuiditas +3.5%
        "tp1_pct": 15.0,            # Cairkan 60% modal di +15.0%
        "tp1_ratio": 0.60,
        "tp2_pct": 45.0,            # Cairkan 50% sisa di +45.0%
        "tp2_ratio": 0.50,
        "trail_pct": 9.5,           # Trailing longgar Moonbag pasca-TP1
        "sl_pct": -14.0,            # Hard Stop Loss terukur
        "max_pos": 2,
    },
    "V6_STEPPED_VORTEX": {
        "mode": "VORTEX_ONLY",      # Murni Vortex Moonbag yang telah disempurnakan
        "sizing": "STEPPED_CPPI",   # Stagnan $3 -> $6 -> $12 + CPPI HWM Lock
        "max_dpp": 0.095,
        "min_liq": 3.5,
        "tp1_pct": 15.5,
        "tp1_ratio": 0.60,
        "tp2_pct": 50.0,
        "tp2_ratio": 0.50,
        "trail_pct": 10.0,
        "sl_pct": -14.0,
        "max_pos": 2,
    },
    "V6_FRACTAL_FORTRESS": {
        "mode": "FORTRESS_SNIPER",  # M4_TEMPORAL_FRACTAL + CHRONOS_P1_FORTRESS
        "sizing": "STEPPED_CPPI",   # Stagnan $3 -> $6 -> $12 + CPPI HWM Lock
        "max_dpp": 0.065,           # Sangat selektif (Target Drawdown mendekati 0%)
        "min_liq": 6.0,
        "tp1_pct": 14.0,
        "tp1_ratio": 0.65,
        "tp2_pct": 40.0,
        "tp2_ratio": 0.50,
        "trail_pct": 7.5,
        "sl_pct": -12.5,
        "max_pos": 1,
    },
    "V6_DYNAMIC_25_OLD": {
        "mode": "BARBELL",          # Sinyal sama dengan V6_STEPPED_BARBELL
        "sizing": "DYNAMIC_25",     # Cara lama: selalu 25% dari ekuitas saat ini
        "max_dpp": 0.100,
        "min_liq": 3.5,
        "tp1_pct": 15.0,
        "tp1_ratio": 0.60,
        "tp2_pct": 45.0,
        "tp2_ratio": 0.50,
        "trail_pct": 9.5,
        "sl_pct": -14.0,
        "max_pos": 2,
    },
}


# ==============================================================================
# UTILITAS LOGGING & GIT SYNC OTOMATIS
# ==============================================================================
def write_log(message: str, print_console: bool = True):
    if print_console:
        print(message, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"[WARN] Gagal menulis log: {e}", flush=True)


def git_sync(commit_msg: str = "chore: live quant v6 sync"):
    """Melakukan auto-commit dan push state terbaru ke repositori GitHub."""
    try:
        subprocess.run(["git", "config", "user.name", "QuantBot-V6"], check=False)
        subprocess.run(["git", "config", "user.email", "quantbot-v6@users.noreply.github.com"], check=False)
        subprocess.run(["git", "add", CHECKPOINT_FILE, LOG_FILE], check=False)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], check=False, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "HEAD"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[GIT SYNC WARN] {e}", flush=True)


def get_session_name(utc_hour: int) -> Tuple[str, bool]:
    """Menentukan nama sesi pasar & apakah sedang berada di jam rawan rug pull."""
    # Jam 18:00 - 21:59 UTC (01:00 - 04:59 WIB) adalah jam rawan flash-rug dini hari
    is_danger_night = 18 <= utc_hour < 22
    if 0 <= utc_hour < 7:
        return "S1_ASIA", False
    elif 7 <= utc_hour < 13:
        return "S2_LONDON", False
    elif 13 <= utc_hour < 20:
        return "S3_NEWYORK", is_danger_night
    else:
        return "S4_NIGHT", is_danger_night


# ==============================================================================
# MESIN UTAMA BOT QUANT V6.0
# ==============================================================================
class QuantBotV6:
    def __init__(self):
        self.accumulated_hours = 0.0
        self.last_tick_ts = time.time()
        self.session_start_ts = time.time()
        self.last_leaderboard_ts = 0.0
        self.last_git_sync_ts = time.time()
        self.running = True

        self.sol_price = 0.0
        self.sol_m5 = 0.0
        self.sol_h1 = 0.0

        self.variants: Dict[str, dict] = {}
        self.init_default_state()
        self.load_checkpoint()

    def init_default_state(self):
        for name in VARIANTS_CONFIG:
            self.variants[name] = {
                "equity": INITIAL_EQUITY,
                "hwm": INITIAL_EQUITY,
                "max_dd": 0.0,
                "tier": 1,
                "wins": 0,
                "losses": 0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "consec_losses": 0,
                "cooldown_until": 0.0,
                "positions": {},       # address -> dict posisi aktif
                "token_history": {},   # address -> timestamp terakhir keluar (Anti-Late Reentry)
                "watchlist_count": 0,
            }

    def load_checkpoint(self):
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.accumulated_hours = float(data.get("accumulated_hours", 0.0))
                saved_vars = data.get("variants", {})
                for name in VARIANTS_CONFIG:
                    if name in saved_vars:
                        self.variants[name].update(saved_vars[name])
                write_log(
                    f"\n♻️ [CHECKPOINT V6 LOADED] Melanjutkan sesi secara akurat "
                    f"(Durasi Akumulasi: {self.accumulated_hours:.2f} Jam)"
                )
            except Exception as e:
                write_log(f"[WARN] Gagal memuat checkpoint, memulai dari awal: {e}")
        write_log(
            "🦅 BOT QUANT V6.0 AKTIF (Stepped $3->$6->$12 + CPPI HWM Floor + Barbell Fractal-Vortex)"
        )

    def save_checkpoint(self):
        try:
            now = time.time()
            delta_hours = max(0.0, (now - self.last_tick_ts) / 3600.0)
            self.accumulated_hours += delta_hours
            self.last_tick_ts = now

            payload = {
                "accumulated_hours": round(self.accumulated_hours, 4),
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "variants": self.variants,
            }
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[WARN] Gagal menyimpan checkpoint: {e}", flush=True)

    # --------------------------------------------------------------------------
    # MANAJEMEN UKURAN POSISI: STEPPED FIXED-LOT ($3 -> $6 -> $12) + CPPI HWM
    # --------------------------------------------------------------------------
    def calculate_allocation(self, var_name: str, signal_grade: str = "A") -> float:
        st = self.variants[var_name]
        cfg = VARIANTS_CONFIG[var_name]
        equity = float(st["equity"])
        hwm = float(st["hwm"])
        current_tier = int(st.get("tier", 1))

        # Jika varian pembanding lama (Dinamis 25% Ekuitas)
        if cfg["sizing"] == "DYNAMIC_25":
            return round(equity * 0.25, 2)

        # Sistem Baru: Stepped Fixed-Lot ($3 -> $6 -> $12 -> $24) + Step-Down Buffer 10%
        base_buy = round(equity * 0.20, 2)
        new_tier = 0

        # 1. Cek kenaikan level (Step-Up)
        for tier_id, step_up_eq, step_down_eq, fixed_buy in STEP_TIERS:
            if equity >= step_up_eq:
                base_buy = fixed_buy
                new_tier = tier_id
                break
        else:
            # 2. Pertahankan Tier selama masih di atas batas rem (Step-Down Buffer)
            for tier_id, step_up_eq, step_down_eq, fixed_buy in STEP_TIERS:
                if current_tier == tier_id and equity >= step_down_eq:
                    base_buy = fixed_buy
                    new_tier = tier_id
                    break
            else:
                # 3. Turunkan Tier jika menembus batas rem bawah
                for tier_id, step_up_eq, step_down_eq, fixed_buy in STEP_TIERS:
                    if equity >= step_down_eq:
                        base_buy = fixed_buy
                        new_tier = tier_id
                        break

        st["tier"] = new_tier

        # 4. CPPI High-Water Mark Cushion:
        # Jika ekuitas terkoreksi >= 8% dari puncak HWM, pangkas ukuran beli 50%
        if hwm > 0 and ((hwm - equity) / hwm) >= 0.08:
            base_buy *= 0.50

        # 5. Penyesuaian Kualitas Sinyal (Grade A = 100%, Grade B = 75%)
        if signal_grade == "B":
            base_buy *= 0.75

        # Batas pengaman absolut maksimal 25% dari ekuitas saat ini
        return round(min(base_buy, equity * 0.25), 2)

    # --------------------------------------------------------------------------
    # PEMINDAIAN DATA PASAR DEXSCREENER (SOLANA MICRO-CAPS)
    # --------------------------------------------------------------------------
    def update_sol_macro(self):
        try:
            resp = requests.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}",
                headers=HEADERS,
                timeout=8,
            )
            if resp.status_code == 200:
                pairs = resp.json().get("pairs") or []
                for p in pairs:
                    if p.get("chainId") == "solana" and p.get("quoteToken", {}).get("symbol") in ("USDC", "USDT"):
                        self.sol_price = float(p.get("priceUsd") or 0.0)
                        pc = p.get("priceChange") or {}
                        self.sol_m5 = float(pc.get("m5") or 0.0)
                        self.sol_h1 = float(pc.get("h1") or 0.0)
                        break
        except Exception:
            pass

    def fetch_candidate_pairs(self) -> List[dict]:
        candidates = []
        mint_addresses = set()

        # Ambil profil & boost terbaru di jaringan Solana
        endpoints = [
            "https://api.dexscreener.com/token-boosts/latest/v1",
            "https://api.dexscreener.com/token-profiles/latest/v1",
        ]
        for url in endpoints:
            try:
                r = requests.get(url, headers=HEADERS, timeout=8)
                if r.status_code == 200:
                    items = r.json()
                    if isinstance(items, list):
                        for item in items:
                            if item.get("chainId") == "solana" and item.get("tokenAddress"):
                                mint_addresses.add(item["tokenAddress"])
            except Exception:
                continue

        # Tambahkan pencarian kata kunci likuiditas aktif Solana
        try:
            r = requests.get(
                "https://api.dexscreener.com/latest/dex/search?q=solana%20pump",
                headers=HEADERS,
                timeout=8,
            )
            if r.status_code == 200:
                for p in r.json().get("pairs") or []:
                    if p.get("chainId") == "solana":
                        candidates.append(p)
        except Exception:
            pass

        # Ambil detail pair dari daftar mint (batch per 25 token)
        mint_list = list(mint_addresses)[:25]
        if mint_list:
            try:
                joined = ",".join(mint_list)
                r = requests.get(
                    f"https://api.dexscreener.com/latest/dex/tokens/{joined}",
                    headers=HEADERS,
                    timeout=8,
                )
                if r.status_code == 200:
                    for p in r.json().get("pairs") or []:
                        if p.get("chainId") == "solana":
                            candidates.append(p)
            except Exception:
                pass

        # Deduplikasi berdasarkan pairAddress
        unique_pairs = {}
        for p in candidates:
            p_addr = p.get("pairAddress")
            if p_addr and p_addr not in unique_pairs:
                unique_pairs[p_addr] = p

        return list(unique_pairs.values())

    def fetch_pair_by_address(self, pair_address: str) -> Optional[dict]:
        try:
            r = requests.get(
                f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}",
                headers=HEADERS,
                timeout=8,
            )
            if r.status_code == 200:
                pairs = r.json().get("pairs") or []
                return pairs[0] if pairs else None
        except Exception:
            pass
        return None

    # --------------------------------------------------------------------------
    # EKSTRAKSI METRIK MIKROSTRUKTUR (DPP, LIQ SURGE, FRACTAL SURGE)
    # --------------------------------------------------------------------------
    @staticmethod
    def compute_microstructure(pair: dict) -> Optional[dict]:
        try:
            price_usd = float(pair.get("priceUsd") or 0.0)
            if price_usd <= 0:
                return None

            liq_usd = float((pair.get("liquidity") or {}).get("usd") or 0.0)
            if liq_usd < 12000.0:  # Tolak kolam likuiditas terlalu dangkal (< $12k)
                return None

            vol = pair.get("volume") or {}
            vol_m5 = float(vol.get("m5") or 0.0)
            vol_h1 = float(vol.get("h1") or 0.0)
            if vol_m5 < 2500.0:
                return None

            txns_m5 = (pair.get("txns") or {}).get("m5") or {}
            buys_m5 = int(txns_m5.get("buys") or 0)
            sells_m5 = int(txns_m5.get("sells") or 0)
            total_tx_m5 = buys_m5 + sells_m5
            if total_tx_m5 < 25 or buys_m5 <= sells_m5:
                return None

            pc = pair.get("priceChange") or {}
            m5_chg = float(pc.get("m5") or 0.0)
            h1_chg = float(pc.get("h1") or 0.0)

            # Hitung DPP (Dislocation & Price-to-Liquidity Pressure)
            # Semakin kecil & positif DPP (0.020 - 0.095), semakin sehat penyerapan likuiditasnya
            buy_ratio = buys_m5 / max(1, total_tx_m5)
            vol_to_liq = vol_m5 / max(1.0, liq_usd)
            dpp = round(abs(m5_chg) / 100.0 * (1.0 / max(0.25, buy_ratio)) * min(1.8, vol_to_liq), 3)

            # Estimasi pertumbuhan likuiditas bersih (Liq +%)
            net_inflow_ratio = ((buys_m5 - sells_m5) / max(1, total_tx_m5)) * vol_to_liq * 100.0
            liq_change_pct = round(max(0.0, min(35.0, net_inflow_ratio)), 1)

            # Hitung Fractal Surge (Rasio akselerasi volume m5 terhadap rata-rata 5 menit di h1)
            avg_m5_in_h1 = max(500.0, vol_h1 / 12.0)
            fractal_surge = round(vol_m5 / avg_m5_in_h1, 2)

            symbol = (pair.get("baseToken") or {}).get("symbol", "UNKNOWN")[:10]
            token_addr = (pair.get("baseToken") or {}).get("address", "")
            pair_addr = pair.get("pairAddress", "")

            return {
                "symbol": symbol,
                "token_addr": token_addr,
                "pair_addr": pair_addr,
                "price": price_usd,
                "liq_usd": liq_usd,
                "dpp": dpp,
                "liq_change_pct": liq_change_pct,
                "fractal_surge": fractal_surge,
                "m5_chg": m5_chg,
                "h1_chg": h1_chg,
                "buys_m5": buys_m5,
                "sells_m5": sells_m5,
            }
        except Exception:
            return None

    # --------------------------------------------------------------------------
    # EVALUASI SINYAL MASUK (ENTRY GATE)
    # --------------------------------------------------------------------------
    def evaluate_entry_for_variant(
        self, var_name: str, m: dict, is_danger_night: bool
    ) -> Tuple[bool, str, str]:
        st = self.variants[var_name]
        cfg = VARIANTS_CONFIG[var_name]
        now = time.time()

        # 1. Cek Cooldown / Circuit Breaker
        if now < float(st.get("cooldown_until", 0.0)):
            return False, "", ""

        # 2. Cek kapasitas posisi aktif
        if len(st["positions"]) >= cfg["max_pos"]:
            return False, "", ""

        # 3. Cek apakah token sudah dipegang atau baru saja ditransaksikan (Anti-Late Reentry 45m)
        t_addr = m["token_addr"]
        if t_addr in st["positions"]:
            return False, "", ""
        last_seen = float(st["token_history"].get(t_addr, 0.0))
        if now - last_seen < 2700:
            return False, "", ""

        # 4. Filter Makro Solana (Blokir beli jika SOL sedang dump tajam)
        if self.sol_m5 <= -0.85:
            return False, "", ""

        # 5. Evaluasi Sinyal A+: M4_TEMPORAL_FRACTAL (100% WR di Lab V3)
        is_fractal_sniper = (
            2.4 <= m["fractal_surge"] <= 6.5
            and 8.0 <= m["m5_chg"] <= 28.0
            and 0.020 <= m["dpp"] <= 0.075
            and m["liq_change_pct"] >= 4.5
            and m["buys_m5"] >= int(m["sells_m5"] * 1.45)
        )

        if cfg["mode"] in ("BARBELL", "FORTRESS_SNIPER") and is_fractal_sniper:
            reason = f"Fractal Surge {m['fractal_surge']:.1f}x | Shift +{m['m5_chg']:.0f}%"
            return True, "A", reason

        # 6. Jika mode FORTRESS_SNIPER pada jam rawan malam, hanya izinkan Fractal Sniper
        if is_danger_night and cfg["mode"] == "FORTRESS_SNIPER":
            return False, "", ""

        # 7. Evaluasi Sinyal Vortex Absorb (Sintesis M5_VORTEX V3 + P3_MOONBAG V5)
        max_dpp = cfg["max_dpp"] * (0.70 if is_danger_night else 1.0)
        min_liq = cfg["min_liq"] * (1.35 if is_danger_night else 1.0)

        is_vortex_absorb = (
            0.020 <= m["dpp"] <= max_dpp
            and m["liq_change_pct"] >= min_liq
            and 2.5 <= m["m5_chg"] <= 22.0
            and m["buys_m5"] >= int(m["sells_m5"] * 1.30)
        )

        if is_vortex_absorb:
            grade = "A" if (m["dpp"] <= 0.060 and m["liq_change_pct"] >= 6.0) else "B"
            reason = f"Vortex Absorb (DPP {m['dpp']:.3f} | Liq +{m['liq_change_pct']:.1f}%)"
            return True, grade, reason

        return False, "", ""

    # --------------------------------------------------------------------------
    # EVALUASI POSISI AKTIF & MEKANISME EXIT ASIMETRIS
    # --------------------------------------------------------------------------
    def manage_active_positions(self):
        now = time.time()
        ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

        # Kumpulkan semua pair_addr aktif lintas varian agar cukup 1x fetch per pair
        active_pairs: Dict[str, Optional[dict]] = {}
        for var_name, st in self.variants.items():
            for t_addr, pos in st["positions"].items():
                p_addr = pos["pair_addr"]
                if p_addr not in active_pairs:
                    active_pairs[p_addr] = self.fetch_pair_by_address(p_addr)

        for var_name, st in self.variants.items():
            cfg = VARIANTS_CONFIG[var_name]
            closed_tokens = []

            for t_addr, pos in list(st["positions"].items()):
                pair_data = active_pairs.get(pos["pair_addr"])
                if not pair_data:
                    continue

                cur_price = float(pair_data.get("priceUsd") or pos["entry_price"])
                cur_liq = float((pair_data.get("liquidity") or {}).get("usd") or pos["entry_liq"])
                txns_m5 = (pair_data.get("txns") or {}).get("m5") or {}
                buys = int(txns_m5.get("buys") or 1)
                sells = int(txns_m5.get("sells") or 1)

                if cur_price > pos["highest_price"]:
                    pos["highest_price"] = cur_price

                chg_pct = ((cur_price - pos["entry_price"]) / pos["entry_price"]) * 100.0
                drop_from_peak_pct = (
                    ((pos["highest_price"] - cur_price) / pos["highest_price"]) * 100.0
                    if pos["highest_price"] > 0
                    else 0.0
                )
                liq_drop_pct = (
                    ((pos["entry_liq"] - cur_liq) / pos["entry_liq"]) * 100.0
                    if pos["entry_liq"] > 0
                    else 0.0
                )

                symbol = pos["symbol"]

                # 1. Deteksi Darurat Anti-Rug (Likuiditas dikuras >= 25% atau tekanan jual ekstrem)
                is_rug = (liq_drop_pct >= 25.0) or (chg_pct <= -19.0) or (sells > buys * 2.6 and chg_pct < -9.0)
                if is_rug:
                    rem_alloc = float(pos["remaining_alloc"])
                    cair = rem_alloc * (1.0 + (chg_pct / 100.0))
                    pnl_rem = cair - rem_alloc
                    total_pnl = float(pos["realized_pnl"]) + pnl_rem
                    total_pct = (total_pnl / float(pos["initial_alloc"])) * 100.0
                    self.finalize_trade(var_name, t_addr, symbol, "🚨 ANTI-RUG EXIT   ", total_pnl, total_pct, ts_str)
                    closed_tokens.append(t_addr)
                    continue

                # 2. Eksekusi Partial TP-1 (+15.0% -> Cairkan 60% Modal!)
                if not pos["tp1_hit"] and chg_pct >= cfg["tp1_pct"]:
                    pos["tp1_hit"] = True
                    part_alloc = float(pos["remaining_alloc"]) * cfg["tp1_ratio"]
                    cair_tp1 = part_alloc * (1.0 + (chg_pct / 100.0))
                    pnl_tp1 = cair_tp1 - part_alloc
                    pos["remaining_alloc"] = round(float(pos["remaining_alloc"]) - part_alloc, 4)
                    pos["realized_pnl"] = round(float(pos["realized_pnl"]) + pnl_tp1, 4)
                    write_log(
                        f"💵 [{var_name:<20}] TP-1 (+{chg_pct:.1f}%) pada {symbol:<10} | Cair: +${cair_tp1:.2f}"
                    )

                # 3. Eksekusi Partial TP-2 (+45.0% -> Cairkan 50% dari sisa Moonbag)
                if pos["tp1_hit"] and not pos["tp2_hit"] and chg_pct >= cfg["tp2_pct"]:
                    pos["tp2_hit"] = True
                    part_alloc = float(pos["remaining_alloc"]) * cfg["tp2_ratio"]
                    cair_tp2 = part_alloc * (1.0 + (chg_pct / 100.0))
                    pnl_tp2 = cair_tp2 - part_alloc
                    pos["remaining_alloc"] = round(float(pos["remaining_alloc"]) - part_alloc, 4)
                    pos["realized_pnl"] = round(float(pos["realized_pnl"]) + pnl_tp2, 4)
                    write_log(
                        f"💵 [{var_name:<20}] TP-2 (+{chg_pct:.1f}%) pada {symbol:<10} | Cair: +${cair_tp2:.2f}"
                    )

                # 4. Manajemen Sisa Posisi SETELAH TP-1 Tercapai (Bebas Choking Dini)
                if pos["tp1_hit"]:
                    # a) Trailing Profit Longgar ala VORTEX_P3_MOONBAG
                    if drop_from_peak_pct >= cfg["trail_pct"] and chg_pct >= 4.0:
                        rem_alloc = float(pos["remaining_alloc"])
                        cair = rem_alloc * (1.0 + (chg_pct / 100.0))
                        total_pnl = float(pos["realized_pnl"]) + (cair - rem_alloc)
                        total_pct = (total_pnl / float(pos["initial_alloc"])) * 100.0
                        self.finalize_trade(var_name, t_addr, symbol, "🎯 TRAILING PROFIT ", total_pnl, total_pct, ts_str)
                        closed_tokens.append(t_addr)
                        continue

                    # b) Breakeven Floor pada sisa Moonbag (Jika harga turun kembali ke +1.5%)
                    if chg_pct <= 1.5:
                        rem_alloc = float(pos["remaining_alloc"])
                        cair = rem_alloc * (1.0 + (chg_pct / 100.0))
                        total_pnl = float(pos["realized_pnl"]) + (cair - rem_alloc)
                        total_pct = (total_pnl / float(pos["initial_alloc"])) * 100.0
                        self.finalize_trade(var_name, t_addr, symbol, "🛡️ BREAKEVEN PROFIT", total_pnl, total_pct, ts_str)
                        closed_tokens.append(t_addr)
                        continue

                # 5. Manajemen Posisi SEBELUM TP-1 Tercapai
                else:
                    # a) Hard Stop Loss (-14.0%)
                    if chg_pct <= cfg["sl_pct"]:
                        rem_alloc = float(pos["remaining_alloc"])
                        cair = rem_alloc * (1.0 + (chg_pct / 100.0))
                        total_pnl = float(pos["realized_pnl"]) + (cair - rem_alloc)
                        total_pct = (total_pnl / float(pos["initial_alloc"])) * 100.0
                        self.finalize_trade(var_name, t_addr, symbol, "❌ HARD STOP LOSS  ", total_pnl, total_pct, ts_str)
                        closed_tokens.append(t_addr)
                        continue

                    # b) Time-Stop Stagnasi (Jika 4.5 menit belum TP-1 dan momentum mati)
                    if (now - float(pos["entry_time"])) >= 270 and -4.0 <= chg_pct <= 2.5:
                        rem_alloc = float(pos["remaining_alloc"])
                        cair = rem_alloc * (1.0 + (chg_pct / 100.0))
                        total_pnl = float(pos["realized_pnl"]) + (cair - rem_alloc)
                        total_pct = (total_pnl / float(pos["initial_alloc"])) * 100.0
                        self.finalize_trade(var_name, t_addr, symbol, "⏱️ TIME-STOP EXIT  ", total_pnl, total_pct, ts_str)
                        closed_tokens.append(t_addr)
                        continue

            for t_addr in closed_tokens:
                st["positions"].pop(t_addr, None)

    def finalize_trade(
        self,
        var_name: str,
        t_addr: str,
        symbol: str,
        exit_label: str,
        net_pnl: float,
        pnl_pct: float,
        ts_str: str,
    ):
        st = self.variants[var_name]
        now = time.time()

        st["equity"] = round(float(st["equity"]) + net_pnl, 2)
        st["token_history"][t_addr] = now

        # Update High-Water Mark & Max Drawdown
        if st["equity"] > st["hwm"]:
            st["hwm"] = st["equity"]
        dd_pct = ((st["equity"] - INITIAL_EQUITY) / INITIAL_EQUITY) * 100.0
        if dd_pct < st["max_dd"]:
            st["max_dd"] = round(dd_pct, 1)

        if net_pnl >= 0:
            st["wins"] += 1
            st["gross_profit"] = round(float(st["gross_profit"]) + net_pnl, 4)
            st["consec_losses"] = 0
        else:
            st["losses"] += 1
            st["gross_loss"] = round(float(st["gross_loss"]) + abs(net_pnl), 4)
            st["consec_losses"] += 1

            # Multi-Level Cooldown (Proteksi Pasar Buruk)
            if st["consec_losses"] == 1:
                st["cooldown_until"] = now + (25 * 60)
                write_log(f"🛡️ [{var_name}] Mengaktifkan Cooldown 25 Menit (Proteksi Pasar Buruk)")
            elif st["consec_losses"] == 2:
                st["cooldown_until"] = now + (60 * 60)
                write_log(f"🛡️ [{var_name}] 2x Loss Beruntun -> Cooldown 60 Menit Aktif")
            else:
                st["cooldown_until"] = now + (180 * 60)
                write_log(f"🛡️ [{var_name}] Circuit Breaker 180 Menit Aktif (Pasar Ekstrem)")

        total_trades = st["wins"] + st["losses"]
        wr = int((st["wins"] / total_trades) * 100) if total_trades > 0 else 0
        roi = ((st["equity"] - INITIAL_EQUITY) / INITIAL_EQUITY) * 100.0
        sign_pnl = "+" if net_pnl >= 0 else ""
        sign_pct = "+" if pnl_pct >= 0 else ""
        sign_roi = "+" if roi >= 0 else ""

        write_log(
            f"🏁 [{ts_str}] [{var_name:<20}] {exit_label} | {symbol:<10} | "
            f"PnL: {sign_pnl}{net_pnl:.2f} USD ({sign_pct}{pnl_pct:.1f}%) | "
            f"Ekuitas: ${st['equity']:.2f} ({sign_roi}{roi:.1f}%) | "
            f"WR: {st['wins']}W/{st['losses']}L ({wr}%)"
        )

    # --------------------------------------------------------------------------
    # CETAK TABEL KLASEMEN REAL-TIME
    # --------------------------------------------------------------------------
    def print_leaderboard(self):
        now = time.time()
        delta_hours = max(0.0, (now - self.last_tick_ts) / 3600.0)
        self.accumulated_hours += delta_hours
        self.last_tick_ts = now

        utc_now = datetime.now(timezone.utc)
        wib_hour = (utc_now.hour + 7) % 24
        session_name, _ = get_session_name(utc_now.hour)
        sol_m5_sign = "+" if self.sol_m5 >= 0 else ""
        sol_h1_sign = "+" if self.sol_h1 >= 0 else ""

        lines = [
            "\n" + "=" * 120,
            f"🏆 KLASEMEN BOT QUANT V6.0 (STEPPED $3->$6->$12 vs DYNAMIC) | "
            f"Durasi: {self.accumulated_hours:.2f} Jam | {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC ({wib_hour:02d}:{utc_now.minute:02d} WIB)",
            f"🌐 Sesi Aktif: {session_name} | SOL: ${self.sol_price:.2f} (m5: {sol_m5_sign}{self.sol_m5:.1f}%, h1: {sol_h1_sign}{self.sol_h1:.1f}%)",
            "-" * 120,
            f"{'METODE VARIAN':<22} | {'EKUITAS':<10} | {'ROI (%)':<9} | {'WIN/LOSS':<10} | {'WIN RATE':<9} | {'PROFIT FACTOR':<13} | {'MAX DD':<8} | {'TIER/POS'}",
            "-" * 120,
        ]

        # Urutkan berdasarkan ekuitas tertinggi
        sorted_vars = sorted(
            self.variants.items(), key=lambda x: float(x[1]["equity"]), reverse=True
        )

        for var_name, st in sorted_vars:
            eq = float(st["equity"])
            roi = ((eq - INITIAL_EQUITY) / INITIAL_EQUITY) * 100.0
            roi_str = f"{'+' if roi >= 0 else ''}{roi:.1f}%"
            w = int(st["wins"])
            l = int(st["losses"])
            wl_str = f"{w:>3}W/{l:<3}L"
            wr = (w / (w + l) * 100.0) if (w + l) > 0 else 0.0
            wr_str = f"{wr:>6.1f}%"

            gp = float(st["gross_profit"])
            gl = float(st["gross_loss"])
            if gl == 0 and gp > 0:
                pf_str = "INF (0 Loss)"
            elif gl == 0:
                pf_str = "0.00x"
            else:
                pf_str = f"{(gp / gl):.2f}x"

            dd_str = f"{float(st['max_dd']):>6.1f}%"
            tier_label = f"T{st.get('tier', 1)}" if VARIANTS_CONFIG[var_name]["sizing"] == "STEPPED_CPPI" else "DYN"
            pos_str = f"{tier_label} / {len(st['positions'])}Pos"

            lines.append(
                f"{var_name:<22} | ${eq:<9.2f} | {roi_str:>9} | {wl_str:<10} | {wr_str:<9} | {pf_str:<13} | {dd_str:<8} | {pos_str}"
            )

        lines.append("=" * 120 + "\n")
        write_log("\n".join(lines))

    # --------------------------------------------------------------------------
    # LOOP EKSEKUSI UTAMA & ESTAFET SESI SEMPURNA
    # --------------------------------------------------------------------------
    def run(self):
        def handle_sigterm(signum, frame):
            self.running = False

        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

        while self.running:
            loop_start = time.time()

            # 1. Cek batas waktu sesi GitHub Actions untuk Estafet Sesi Sempurna
            if (loop_start - self.session_start_ts) >= MAX_SESSION_DURATION_SEC:
                self.save_checkpoint()
                write_log(
                    "🔄 [ESTAFET SESI SEMPURNA] State berhasil di-push ke GitHub, siap dilanjutkan sesi berikutnya!"
                )
                git_sync("chore: estafet sesi sempurna quant v6")
                break

            # 2. Update kondisi makro SOL & kelola posisi yang sedang terbuka
            self.update_sol_macro()
            self.manage_active_positions()

            # 3. Pindai kandidat token baru dari DexScreener
            utc_now = datetime.now(timezone.utc)
            _, is_danger_night = get_session_name(utc_now.hour)
            raw_pairs = self.fetch_candidate_pairs()
            ts_str = utc_now.strftime("%H:%M:%S")

            for pair in raw_pairs:
                m = self.compute_microstructure(pair)
                if not m:
                    continue

                for var_name, st in self.variants.items():
                    ok, grade, reason = self.evaluate_entry_for_variant(
                        var_name, m, is_danger_night
                    )
                    if ok:
                        alloc_usd = self.calculate_allocation(var_name, grade)
                        if alloc_usd < 1.0:
                            continue

                        st["positions"][m["token_addr"]] = {
                            "symbol": m["symbol"],
                            "token_addr": m["token_addr"],
                            "pair_addr": m["pair_addr"],
                            "entry_price": m["price"],
                            "highest_price": m["price"],
                            "entry_liq": m["liq_usd"],
                            "initial_alloc": alloc_usd,
                            "remaining_alloc": alloc_usd,
                            "realized_pnl": 0.0,
                            "entry_time": time.time(),
                            "tp1_hit": False,
                            "tp2_hit": False,
                        }
                        write_log(
                            f"🚀 [{ts_str}] [{var_name:<20}] BELI {m['symbol']:<10} "
                            f"(${m['price']:.6f}) | Alokasi: ${alloc_usd:.2f} | {reason}"
                        )

            # 4. Cetak tabel klasemen setiap 3 menit
            if (time.time() - self.last_leaderboard_ts) >= LEADERBOARD_INTERVAL_SEC:
                self.print_leaderboard()
                self.save_checkpoint()
                self.last_leaderboard_ts = time.time()

            # 5. Live Git Sync setiap 15 menit
            if (time.time() - self.last_git_sync_ts) >= GIT_SYNC_INTERVAL_SEC:
                self.save_checkpoint()
                git_sync("chore: live sync 15m quant v6")
                self.last_git_sync_ts = time.time()

            elapsed = time.time() - loop_start
            sleep_sec = max(2.0, SCAN_INTERVAL_SEC - elapsed)
            time.sleep(sleep_sec)

        # Simpan state terakhir jika dihentikan manual
        self.save_checkpoint()
        git_sync("chore: final state save quant v6")


if __name__ == "__main__":
    bot = QuantBotV6()
    bot.run()