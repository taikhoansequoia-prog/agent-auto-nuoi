# -*- coding: utf-8 -*-
"""Smoke test v1.8.3 — MỖI PROFILE 1 CHỦ ĐỀ RIÊNG + AI DỰNG CHUỖI HÀNH ĐỘNG CÓ LOGIC.

Bug user thấy (19/11/2026): danh sách 75 dòng liền nhau -> v1.7.7 coi là 1 cụm -> 8 profile
dùng CHUNG 1 bộ 75 từ khóa. User muốn: mỗi profile 1 chủ đề riêng, AI tìm từ khóa + sắp
hành động xoay quanh chủ đề có logic; ~80% theo kế hoạch, ~20% ngẫu nhiên.
Đồng thời: AI đã chọn mà chết (vd Claude hết số dư) -> tự dùng AI khác còn sống.

Chạy OFFLINE: python src\\test_v183.py
"""
import os
import random
import sys
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v183_")
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(os.environ["GPM_BOT_DATA_DIR"], ".env")

import src.ui_main as ui  # noqa: E402
import src.workflow.warmup as W  # noqa: E402

PASS = 0
FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}" + (f"  ({extra})" if extra else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"  ({extra})" if extra else ""))


print("\n== 1. Mỗi profile 1 chủ đề riêng")
block = [{"google_query": f"topic {i}", "youtube_query": f"topic {i}"} for i in range(75)]
themes = ui.lines_to_themes([block])
check("75 dòng liền nhau -> 75 chủ đề (không còn 1 cụm)", len(themes) == 75)
check("không còn khóa cluster (không ép dùng chung)", all("cluster" not in t for t in themes))
check("mỗi chủ đề kèm 74 từ khóa liên quan làm gợi ý", len(themes[0]["related"]) == 74
      and "topic 0" not in themes[0]["related"])
pids = [f"P{i}" for i in range(8)]
amap, rows = ui.assign_topics_for_run(pids, themes)
got = [amap[p]["google_query"] for p in pids]
check("8 profile nhận 8 chủ đề KHÁC nhau", len(set(got)) == 8, str(got))
check("bảng xác nhận hiện đúng 1 chủ đề/dòng (không '(75 từ khóa)')", all("từ khóa)" not in r["google"] for r in rows))
two = ui.lines_to_themes([[{"google_query": "a1", "youtube_query": "a1"}, {"google_query": "a2", "youtube_query": "a2"}],
                          [{"google_query": "b1", "youtube_query": "b1"}]])
check("gợi ý chỉ lấy trong CÙNG cụm", two[0]["related"] == ["a2"] and two[2]["related"] == [])
src_u = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("start_automation dùng lines_to_themes", "_themes_now = lines_to_themes(self._collect_kw_clusters())" in src_u)

print("\n== 2. Kế hoạch AI có gợi ý + thứ tự")


class Ctx:
    def on(self, *a, **k):
        pass


class Brain:
    prompts = []

    def ask_text(self, p):
        Brain.prompts.append(p)
        return "\n".join(["google | best morning routine", "youtube | 15 minute morning workout",
                          "google | where to buy yoga mat", "maps | gym near me", "news | sleep study 2026"])


wf = W.WarmupWorkflow(context=Ctx(), brain=Brain())
plan = wf._safe_ask_plan(topic_hint="morning routine", related=["yoga mat", "healthy breakfast"])
check("prompt có từ khóa liên quan", "yoga mat, healthy breakfast" in Brain.prompts[-1])
check("prompt yêu cầu THỨ TỰ hợp lý", "ORDER MATTERS" in Brain.prompts[-1])
check("parse đủ 5 bước", plan and len(plan) == 5)

print("\n== 3. Chọn hành động theo bước kế hoạch")
wf.plan_steps = plan
wf._plan_used = set()
valid = {k: 1 for k in ("search_google", "read_news", "action_search_youtube", "watch_video",
                         "action_search_maps", "action_read_wikipedia")}
check("bước 1 google -> search_google", wf._pick_plan_action(valid) == ("search_google", 0))
wf._pending_step_idx = 0
q = wf._plan_keyword("news", "google_query", "x")
check("hành động dùng ĐÚNG từ khóa của bước đã chốt (dù hỏi nền tảng khác)", q == "best morning routine", q)
check("bước kế: youtube -> tìm kiếm YouTube (không phải trang chủ)",
      wf._pick_plan_action(valid) == ("action_search_youtube", 1))
no_yt = {k: v for k, v in valid.items() if "youtube" not in k and k != "watch_video"}
check("pha không có YouTube -> bỏ qua bước youtube, sang bước kế làm được",
      wf._pick_plan_action(no_yt) == ("search_google", 2))
check("tỉ lệ theo kế hoạch 80%", W.WarmupWorkflow.PLAN_FOLLOW_P == 0.8)
src_w = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("bộ chọn: theo kế hoạch rồi mới bốc ngẫu nhiên",
      "random.random() < self.PLAN_FOLLOW_P" in src_w and "self._pick_plan_action(valid_actions)" in src_w)
check("xoá bước đang chờ sau mỗi hành động", "self._pending_step_idx = None\n" in src_w.replace("\r\n", "\n"))

print("\n== 4. Kế hoạch dự phòng (không AI) cũng dùng từ khóa liên quan")
wf2 = W.WarmupWorkflow(context=Ctx(), keyword_lang="en")
wf2.related_keywords = ["gym near me", "how to do squats"]
steps = wf2._local_plan_steps("fitness")
qs = [(s["platform"], s["query"]) for s in steps]
check("có từ khóa liên quan với nền tảng hợp lý", ("maps", "gym near me") in qs and ("youtube", "how to do squats") in qs, str(qs[:4]))
check("bước mở màn vẫn là google", steps[0]["platform"] == "google")

print("\n== 5. Tự dùng AI còn sống")
real = ui._pick_live_brain, ui._brain_candidates_from_env
logs = []
try:
    ui._brain_candidates_from_env = lambda: ["claude-sonnet", "gemini"]
    seen_cands = []
    ui._pick_live_brain = lambda cands, log=None: (seen_cands.extend(cands), (None, "", "x"))[1]
    ui.resolve_run_brain("claude-sonnet", log=logs.append)
    check("thử AI đã chọn TRƯỚC, rồi tới AI khác", seen_cands == ["claude-sonnet", "gemini"], str(seen_cands))
    ui._pick_live_brain = lambda cands, log=None: (object(), "gemini", "")
    out = ui.resolve_run_brain("claude-sonnet", log=logs.append)
    check("trả tên AI đang sống", out == "gemini", out)
    check("log nói rõ đã tự đổi", any("tự dùng 'gemini'" in l for l in logs), str(logs[-1:]))
    ui._pick_live_brain = lambda cands, log=None: (None, "", "HẾT SỐ DƯ")
    check("tất cả chết -> 'none' (chạy kế hoạch dự phòng)", ui.resolve_run_brain("gemini", log=logs.append) == "none")
    check("'none' giữ nguyên, không dò mạng", ui.resolve_run_brain("none", log=logs.append) == "none")
finally:
    ui._pick_live_brain, ui._brain_candidates_from_env = real

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.3: ALL PASS" if FAIL == 0 else "SMOKE v1.8.3: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
