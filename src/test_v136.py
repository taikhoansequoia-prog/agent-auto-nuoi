"""Smoke test v1.3.6 — nhóm profile kiểu GPM (chạy từ source, API GPM thật phải bật)."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import tkinter as tk
from src.ui_main import AutomationApp, GROUP_ALL, UNGROUPED_LABEL
from src.browser.browser_factory import BrowserFactory, BROWSER_GPM

FAILS = []
def check(name, cond):
    print(("  OK  " if cond else "  FAIL") + " | " + name)
    if not cond:
        FAILS.append(name)

root = tk.Tk()
app = AutomationApp(root)
root.update()

# 1) Tải profile THẬT từ API GPM
api = BrowserFactory.get_api(BROWSER_GPM, base_url="http://localhost:9495")
lst = api.list_profiles()
print(f"API trả {len(lst)} profile; groups mẫu: " +
      str(sorted({(p.get('group') or UNGROUPED_LABEL) for p in lst})))
app._apply_api_profiles(lst)
root.update()

check("rows == số profile API", len(app.profile_rows) == len(lst))
groups = [(r.get("group") or UNGROUPED_LABEL) for r in app.profile_rows]
distinct = [g for g in dict.fromkeys(groups)]
check("mọi row có key group", all("group" in r for r in app.profile_rows))
check("_group_headers khớp distinct nhóm",
      set(app._group_headers.keys()) == set(distinct))

# 2) Combobox nhóm hiện khi >=2 nhóm
multi = len([g for g in distinct if g != UNGROUPED_LABEL]) >= 1 and len(distinct) >= 2
check("combobox mapped đúng điều kiện multi",
      bool(app.cbo_prof_group.winfo_ismapped()) == multi)
check("multi -> header các nhóm hiện",
      all(h["frame"].winfo_ismapped() for h in app._group_headers.values()))
# v1.3.6 FIX quan trọng: pack() lại trên widget đã pack KHÔNG đổi thứ tự -> header rớt
# xuống đáy canvas (bug thấy trên EXE). Kiểm tra bằng VỊ TRÍ y thật sau update_idletasks.
root.update_idletasks()
hdr_frames = {id(h["frame"]) for h in app._group_headers.values()}
pos = sorted((w.winfo_y(), "HDR" if id(w) in hdr_frames else "ROW", w)
             for w in app.prof_inner.winfo_children() if w.winfo_ismapped())
check("widget đầu canvas là header nhóm (không phải row)",
      bool(pos) and pos[0][1] == "HDR")
bad_order = []
for g, h in app._group_headers.items():
    if not h["frame"].winfo_ismapped():
        continue
    hy = h["frame"].winfo_y()
    rows_g = [r for r in app.profile_rows
              if (r["group"] or UNGROUPED_LABEL) == g and not r["hidden"]
              and r["frame"].winfo_ismapped()]
    if rows_g and hy >= min(r["frame"].winfo_y() for r in rows_g):
        bad_order.append(g)
check("mọi header đứng TRƯỚC dòng đầu nhóm mình (xen kẽ đúng)", not bad_order)
vals = list(app.cbo_prof_group.cget("values"))
check("values = [GROUP_ALL]+groups", vals[0] == GROUP_ALL and set(vals[1:]) == set(distinct))

# 3) Lọc theo 1 nhóm thật -> chỉ row nhóm đó hiện, header khác ẩn
if multi:
    real = [g for g in distinct if g != UNGROUPED_LABEL][0]
    app.var_prof_group.set(real)
    app._filter_profiles()
    root.update()
    shown = [r for r in app.profile_rows if not r["hidden"]]
    check("lọc 1 nhóm: mọi row hiện thuộc nhóm đó",
          all((r["group"] or UNGROUPED_LABEL) == real for r in shown))
    check("lọc 1 nhóm: số hiện == số row nhóm đó",
          len(shown) == sum(1 for r in app.profile_rows if (r["group"] or UNGROUPED_LABEL) == real))
    # header nhóm khác phải ẩn
    other = [g for g in distinct if g != real]
    for g in other:
        h = app._group_headers.get(g)
        if h:
            check(f"header nhóm phụ '{g}' ẩn", h["frame"].winfo_ismapped() == 0)
    # _set_all_profiles chỉ ảnh hưởng row hiện: bỏ hết (lọc GROUP_ALL) rồi mới lọc + chọn tất cả
    app.var_prof_group.set(GROUP_ALL); app._filter_profiles(); root.update()
    app._set_all_profiles(False); root.update()
    app.var_prof_group.set(real); app._filter_profiles(); root.update()
    shown = [r for r in app.profile_rows if not r["hidden"]]
    app._set_all_profiles(True); root.update()
    check("chọn tất cả (theo lọc): row hiện (Chrome) được tick",
          all(r["var"].get() for r in shown if not r["firefox"]))
    check("chọn tất cả (theo lọc): row ẨN không bị tick",
          all((not r["var"].get()) for r in app.profile_rows if r["hidden"]))
    app.var_prof_group.set(GROUP_ALL)
    app._filter_profiles()
    root.update()

# 4) Giữ selection qua reload (chọn 1 row Chrome, không Firefox)
chrome = next(r for r in app.profile_rows if not r["firefox"])
keep = {chrome["id"]}
for r in app.profile_rows:
    r["var"].set(r["id"] in keep)
app._apply_api_profiles(lst)
root.update()
_sel_ids = [r["id"] for r in app.profile_rows if r["var"].get()]
_ids_all = [r["id"] for r in app.profile_rows]
_dup = {i for i in _ids_all if _ids_all.count(i) > 1}
print(f"    [dbg] nsel={len(_sel_ids)} sel={_sel_ids} keep={keep} dup_ids={_dup}")
check("giữ selection qua reload", set(_sel_ids) == keep)

# 5) Dán tay -> group "" -> Chưa có nhóm, không crash
app._add_profile_row("a" * 32, "manual", False, True, "")
app._layout_groups(); app._populate_group_filter(); app._filter_profiles()
root.update()
check("row dán tay group='' -> header 'Chưa có nhóm' tồn tại",
      UNGROUPED_LABEL in app._group_headers)

# 6) Danh sách CHƯA phân nhóm -> combobox ẩn (UI như v1.2.x)
app._rebuild_profile_rows([{"id": "x" * 32, "name": "solo", "firefox": False,
                            "selected": True, "group": ""}])
root.update()
check("1 nhóm chưa-phân-nhóm -> combobox ẨN", app.cbo_prof_group.winfo_ismapped() == 0)
check("1 nhóm chưa-phân-nhóm -> header 'Chưa có nhóm' ẨN",
      app._group_headers[UNGROUPED_LABEL]["frame"].winfo_ismapped() == 0)

app._set_all_profiles(False)
root.destroy()
print("\n=== " + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL: {FAILS}") + " ===")
sys.exit(1 if FAILS else 0)
