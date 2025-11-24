#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schedule Helper Functions for CP-SAT Scheduling System
Contains all helper functions extracted from the original 
"""

import pandas as pd
import re
import os
from datetime import datetime
from collections import defaultdict, OrderedDict
from typing import Dict, List, Optional, Any, Tuple

# Try to import matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import fontManager
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Import parsing helpers from the main module
from .schedule_cpsat import norm_date, pick_shift, cat_of_post

def build_rows(assignments, provided):
    """
    Builds the rows for the main schedule sheet and returns a complete
    list of all assignments, which serves as the single source of truth.
    """
    dates = list(
        OrderedDict((norm_date(d), None) for d in (provided.get("schedulePeriod", {}).get("dates") or [])).keys()
    )
    emps = provided.get("employees") or []
    name_by_id = {str(e.get("id")): e.get("name", e.get("id")) for e in emps}

    # Start with solver assignments
    complete_assignments = [a.copy() for a in assignments]

    by_emp = defaultdict(lambda: defaultdict(str))
    for a in complete_assignments:
        eid = a["employeeId"]
        name = a.get("employeeName") or name_by_id.get(eid, eid)
        key = f"{name}/{eid}"
        cell = f'{a["shift"]} {a["post"]}'.strip()
        d = a["date"]
        by_emp[key][d] = (by_emp[key][d] + ("、" if by_emp[key][d] else "") + cell)

    # OFF requests override any assignment
    off_requests = [x for x in (provided.get("leaveRequests", []) or []) if str(x.get("preset", "")).upper() == "OFF"]
    for l in off_requests:
        d = norm_date(l.get("date"))
        eid = str(l.get("employeeId") or "").strip()
        name = name_by_id.get(eid, eid)
        key = f"{name}/{eid}"
        by_emp[key][d] = "OFF"
        
        # FIX: Remove any solver assignments for this employee on this day before adding the OFF record
        complete_assignments = [a for a in complete_assignments if not (a["employeeId"] == eid and a["date"] == d)]
        
        # Add to complete list for other reports
        complete_assignments.append({"date": d, "shift": "OFF", "post": "休假", "employeeId": eid, "employeeName": name})


    # Manually add Head Nurse Admin Shifts to the report and the complete list
    headNurseAdminAssignments = provided.get("headNurseAdminAssignments", [])
    for h in headNurseAdminAssignments:
        d = h["date"]
        eid = h["employeeId"]
        name = name_by_id.get(eid, eid)
        key = f"{name}/{eid}"
        by_emp[key][d] = f"{h['shift']} 行政"
        # Add to complete list for other reports
        complete_assignments.append({"date": d, "shift": h["shift"], "shiftAlias": h["shift"], "post": "行政", "employeeId": eid, "employeeName": name})

    # --- New Logic: Handle flexible head nurses ('Y') who were not assigned by the solver ---
    # They become admin shifts if not needed for support.
    flexible_support_shifts = [pa for pa in provided.get("preAssignments", []) if pa.get("is_support_allowed")]
    # At this point, complete_assignments contains solver results, OFFs, and fixed admin shifts.
    # We create a set for efficient lookup of who is already scheduled on a given day.
    assigned_on_date = {(a["employeeId"], a["date"]) for a in complete_assignments}

    for pa in flexible_support_shifts:
        eid = pa["employeeId"]
        d = pa["date"]
        
        # If this flexible nurse was NOT assigned any shift on this day by the solver or other manual assignments
        if (eid, d) not in assigned_on_date:
            name = name_by_id.get(eid, eid)
            key = f"{name}/{eid}"
            
            # We can directly assign, as the check above ensures we don't overwrite anything.
            by_emp[key][d] = f"{pa['shift']} 行政"
            # Add to the complete list for consistency in all downstream reports.
            complete_assignments.append({
                "date": d, 
                "shift": pa["shift"], 
                "shiftAlias": pa["shift"], 
                "post": "行政", 
                "employeeId": eid, 
                "employeeName": name
            })

    if not dates:
        dates = sorted({a["date"] for a in complete_assignments})

    rows = []

    def id_from_key(k):
        return k.split("/", 1)[1] if "/" in k else k

    # Sort rows by employee ID
    sorted_keys = sorted(by_emp.keys(), key=lambda k: id_from_key(k))
    
    # Ensure all employees have a row, even if they have no shifts
    all_emp_keys = {f"{(e.get('name') or e.get('id'))}/{(e.get('id'))}" for e in emps}
    all_keys = sorted(list(set(sorted_keys) | all_emp_keys), key=lambda k: id_from_key(k))

    for key in all_keys:
        row = {"員工(姓名/ID)": key}
        for d in dates:
            row[d] = by_emp[key].get(d, "")
        rows.append(row)
        
    return rows, complete_assignments


def build_daily_analysis_report(provided, finalAssignments):
    """
    Generates a human-readable, day-by-day report for analyzing schedule
    quality and manpower gaps.
    """
    report_lines = []
    
    # --- Pre-computation for efficient lookups ---
    emps_by_id = {e["id"]: e for e in provided["employees"]}
    dates = provided["schedulePeriod"]["dates"]
    
    # Off days by date
    off_by_day = defaultdict(list)
    for leave in provided.get("leaveRequests", []):
        if leave.get("preset", "").upper() == "OFF":
            emp_name = emps_by_id.get(leave["employeeId"], {}).get("name", leave["employeeId"])
            off_by_day[leave["date"]].append(emp_name)

    # Work days for each employee
    work_days_by_emp = defaultdict(set)
    for a in finalAssignments:
        work_days_by_emp[a["employeeId"]].add(a["date"])

    # Assignments grouped by day and shift
    assignments_by_day = defaultdict(list)
    assignments_by_day_shift_cat = defaultdict(lambda: defaultdict(int))
    assignments_by_day_shift_post = defaultdict(list)
    for a in finalAssignments:
        assignments_by_day[a["date"]].append(a)
        cat = cat_of_post(a["post"])
        key = (a["date"], a["shift"])
        assignments_by_day_shift_cat[key][cat] += 1
        assignments_by_day_shift_post[key].append(f'{a["employeeName"]}({cat}人力)')

    # Demand grouped by day and shift
    demand_by_day_shift_cat = defaultdict(lambda: defaultdict(int))
    for w in provided["weeklyDemand"]:
        cat = cat_of_post(w["post"])
        key = (w["date"], pick_shift(w["shiftAlias"]))
        demand_by_day_shift_cat[key][cat] += w["demand"]

    # --- Generate report day by day --- 
    for idx, d in enumerate(dates):
        report_lines.append("="*50)
        
        # 1. Find available but unscheduled employees
        scheduled_ids = {a["employeeId"] for a in assignments_by_day.get(d, [])}
        off_ids = {eid for eid, emp in emps_by_id.items() if emp["name"] in off_by_day.get(d, [])}
        available_unscheduled_ids = set(emps_by_id.keys()) - scheduled_ids - off_ids
        
        unscheduled_texts = []
        for eid in sorted(list(available_unscheduled_ids)):
            consecutive_days = 0
            # Check backwards from the previous day
            for i in range(idx - 1, -1, -1):
                prev_date = dates[i]
                if prev_date in work_days_by_emp[eid]:
                    consecutive_days += 1
                else:
                    break
            emp_name = emps_by_id[eid]["name"]
            unscheduled_texts.append(f"{emp_name}(已連上{consecutive_days}天)")
        
        report_lines.append(f"{d} 本日未排班人力: {'、'.join(unscheduled_texts) if unscheduled_texts else '無'}")

        # 2. List employees on leave
        on_leave_names = sorted(off_by_day.get(d, []))
        report_lines.append(f"{d} 當日休假人員: {'、'.join(on_leave_names) if on_leave_names else '無'}")
        
        # 3. Per-shift status
        for s in ["A", "B", "C"]:
            demand_cat = demand_by_day_shift_cat.get((d, s), defaultdict(int))
            assigned_cat = assignments_by_day_shift_cat.get((d, s), defaultdict(int))
            
            demand_str = f"{demand_cat['櫃']}/{demand_cat['護']}/{demand_cat['二線']}/{demand_cat['藥局']}"
            assigned_str = f"{assigned_cat['櫃']}/{assigned_cat['護']}/{assigned_cat['二線']}/{assigned_cat['藥局']}"
            
            is_gap = any(assigned_cat[cat] < demand_cat[cat] for cat in ['櫃', '護', '二線', '藥局'])
            status = "❌ 人力缺口" if is_gap else "✔ OK"
            
            report_lines.append(f"{d} {s}班 狀態需求: {demand_str}, 排班: {assigned_str}, {status}")
            
            assigned_staff = assignments_by_day_shift_post.get((d, s), [])
            report_lines.append(f"{d} {s}班 排班: {'、'.join(sorted(assigned_staff)) if assigned_staff else '無'}")

    return report_lines


def check_hard_constraints(assignments, provided):
    violations = []
    
    # Pre-build lookups for efficiency
    emps_by_id = {e["id"]: e for e in provided["employees"]}
    off_set = {(norm_date(l["date"]), l["employeeId"]) for l in provided["leaveRequests" ] if l.get("preset", "").upper() == "OFF"}
    
    assignments_by_day = defaultdict(list)
    assignments_by_shift = defaultdict(list)
    for a in assignments:
        assignments_by_day[(a["employeeId"], a["date"])].append(a)
        assignments_by_shift[(a["employeeId"], a["date"], a["shift"])].append(a)

    # 1. Check individual assignments for date/shift/off violations
    for a in assignments:
        emp = emps_by_id.get(a["employeeId"])
        if not emp: continue

        if (a["date"], a["employeeId"]) in off_set:
            violations.append({"日期": a["date"], "員工ID": a["employeeId"], "違規類型": "排休假員工", "詳細資訊": f"員工 {a['employeeId']} 在休假日 {a['date']} 被排班"})
        
        if a["date"] not in (emp.get("availableDates", []) or provided["schedulePeriod"]["dates"]):
             violations.append({"日期": a["date"], "員工ID": a["employeeId"], "違規類型": "超出可上日期", "詳細資訊": f"員工 {a['employeeId']} 在不可上日的 {a['date']} 被排班"})

        if a["shift"] not in (emp.get("availableShifts", []) or ["A", "B", "C"]):
            violations.append({"日期": a["date"], "員工ID": a["employeeId"], "違規類型": "超出可上班別", "詳細資訊": f"員工 {a['employeeId']} 被排入不可上的班別 {a['shift']}"})

    # 2. Check segments per day
    for (eid, d), day_assignments in assignments_by_day.items():
        if len(day_assignments) > 3: # Allow 3 for penalization, check for > 3
            violations.append({"日期": d, "員工ID": eid, "違規類型": "每日超過3段班", "詳細資訊": f"員工 {eid} 在 {d} 被排了 {len(day_assignments)} 個崗位"})

    # 3. Check segments per shift
    for (eid, d, s), shift_assignments in assignments_by_shift.items():
        if len(shift_assignments) > 1:
            violations.append({"日期": d, "員工ID": eid, "違規類型": "單一班別多崗位", "詳細資訊": f"員工 {eid} 在 {d} 的 {s} 班被排了 {len(shift_assignments)} 個崗位"})
            
    return violations


def check_soft_constraints(result, provided, audit_by_key):
    violations = []
    
    # --- Create a complete list of assignments for this function's scope ---
    solver_assignments = result["finalAssignments"]
    admin_assignments = []
    emps_by_id = {e["id"]: e for e in provided["employees"]}
    for h in provided.get("headNurseAdminAssignments", []):
        eid = h["employeeId"]
        emp_name = emps_by_id.get(eid, {}).get("name", eid)
        admin_assignments.append({
            "date": h["date"], "shift": h["shift"], "shiftAlias": h["shift"],
            "post": "行政", "employeeId": eid, "employeeName": emp_name
        })
    assignments = solver_assignments + admin_assignments
    
    custom_rules = provided.get("customRules", [])
    employees = provided.get("employees", [])
    
    # --- Pre-computation of metrics from final assignments ---
    emp_metrics = defaultdict(lambda: {
        "total_shifts": 0, "total_hours": 0, "weekend_days": set(),
        "shift_counts": defaultdict(int), "special_clinic_counts": defaultdict(int),
        "work_days": set(), "shifts_by_date": defaultdict(list)
    })
    
    date_to_weekday = {d: datetime.strptime(d, "%Y/%m/%d").strftime("%A") for d in provided["schedulePeriod"]["dates"]}
    demand_map = {(w["date"], w["shiftAlias"], w["post"]): w for w in provided["weeklyDemand"]}
    shift_hours_map = provided.get("shiftHoursMap", {})
    def get_shift_hours(s_alias):
        return shift_hours_map.get(s_alias, 8.0)

    for a in assignments:
        eid = a["employeeId"]
        emp_metrics[eid]["work_days"].add(a["date"])
        emp_metrics[eid]["total_shifts"] += 1
        emp_metrics[eid]["total_hours"] += get_shift_hours(a["shiftAlias"])
        emp_metrics[eid]["shifts_by_date"].setdefault(a["date"], []).append(a)
        
        if date_to_weekday.get(a["date"]) in ("Saturday", "Sunday"):
            emp_metrics[eid]["weekend_days"].add(a["date"])
            
        emp_metrics[eid]["shift_counts"].setdefault(a["shift"], 0)
        emp_metrics[eid]["shift_counts"][a["shift"]] += 1
        
        key = (a["date"], a["shiftAlias"], a["post"])
        demand_info = demand_map.get(key, {})
        if "特殊" in demand_info.get("postType", ""):
            emp_metrics[eid]["special_clinic_counts"].setdefault(demand_info["postType"], 0)
            emp_metrics[eid]["special_clinic_counts"][demand_info["postType"]] += 1

    # --- 1. Check for built-in violations (Manpower Gap, Split Shift, Overstaffing) ---
    for item in audit_by_key:
        if item.get("gap", 0) > 0:
            d, s, p = item["key"] .split("|")
            violations.append({"日期": d, "員工ID": "N/A", "違規類型": "人力缺口", "詳細資訊": f"崗位 {p} 在 {d} 的 {s} 班缺少 {item['gap']} 人"})
        if item.get("over", 0) > 0:
            d, s, p = item["key"] .split("|")
            violations.append({"日期": d, "員工ID": "N/A", "違規類型": "人力過剩", "詳細資訊": f"崗位 {p} 在 {d} 的 {s} 班多出 {item['over']} 人"})
    
    for eid, metrics in emp_metrics.items():
        for d, day_assignments in metrics["shifts_by_date"].items():
            shifts = {a["shift"] for a in day_assignments}
            if 'A' in shifts and 'C' in shifts:
                violations.append({"日期": d, "員工ID": eid, "違規類型": "早晚分隔班", "詳細資訊": f"員工 {eid} 在 {d} 被安排了 A 班和 C 班"})

    # --- 2. Check for violations based on active custom rules ---
    for rule in custom_rules:
        rule_type = rule["rule_type"]
        param1 = rule["param1"]
        param2 = rule["param2"]
        threshold_str = rule.get("param3", "0")
        threshold = int(float(threshold_str)) if threshold_str and threshold_str != 'nan' else 0
        target_eid = param1

        # --- Fairness Rules ---
        if rule_type == "fair_total_hours":
            report_threshold = threshold if threshold > 0 else 16
            all_hours = [m["total_hours"] for m in emp_metrics.values()]
            avg = sum(all_hours) / len(all_hours) if all_hours else 0
            for eid, metrics in emp_metrics.items():
                if abs(metrics["total_hours"] - avg) > report_threshold:
                    violations.append({"日期": "整月", "員工ID": eid, "違規類型": "[公平性] 總工時差異", "詳細資訊": f"員工 {eid} 總工時為 {metrics['total_hours']:.1f} 小時 (平均為 {avg:.1f} 小時)"})
        
        elif rule_type == "fair_weekend_offs":
            report_threshold = threshold if threshold > 0 else 1
            all_weekends = [len(m["weekend_days"]) for m in emp_metrics.values()]
            avg = sum(all_weekends) / len(all_weekends) if all_weekends else 0
            for eid, metrics in emp_metrics.items():
                if abs(len(metrics["weekend_days"]) - avg) > report_threshold:
                    violations.append({"日期": "整月", "員工ID": eid, "違規類型": "[公平性] 週末排班差異", "詳細資訊": f"員工 {eid} 週末上班 {len(metrics['weekend_days'])} 天 (平均為 {avg:.1f} 天)"})

        elif rule_type == "fair_special_clinics":
            clinic_type = param1
            report_threshold = threshold if threshold > 0 else 2
            all_counts = [m["special_clinic_counts"].get(clinic_type, 0) for m in emp_metrics.values()]
            avg = sum(all_counts) / len(all_counts) if all_counts else 0
            for eid, metrics in emp_metrics.items():
                count = metrics["special_clinic_counts"].get(clinic_type, 0)
                if abs(count - avg) > report_threshold:
                    violations.append({"日期": "整月", "員工ID": eid, "違規類型": f"[公平性] {clinic_type} 診次差異", "詳細資訊": f"員工 {eid} 上 {clinic_type} {count} 次 (平均為 {avg:.1f} 次)"})

        elif rule_type == "fair_shift_types":
            report_threshold = threshold if threshold > 0 else 3
            for s_type in ("A", "B", "C"):
                all_counts = [m["shift_counts"].get(s_type, 0) for m in emp_metrics.values()]
                avg = sum(all_counts) / len(all_counts) if all_counts else 0
                for eid, metrics in emp_metrics.items():
                    count = metrics["shift_counts"].get(s_type, 0)
                    if abs(count - avg) > report_threshold:
                        violations.append({"日期": "整月", "員工ID": eid, "違規類型": f"[公平性] {s_type}班次差異", "詳細資訊": f"員工 {eid} 上 {s_type} 班 {count} 次 (平均為 {avg:.1f} 次)"})

        # --- Welfare & Cost Rules ---
        elif rule_type == "satisfy_preferred_leave":
            preferred_leaves = {(norm_date(l["date"]), l["employeeId"]) for l in provided["leaveRequests"] if "偏好" in l.get("preset", "")}
            for d, eid in preferred_leaves:
                if d in emp_metrics[eid]["work_days"]:
                    violations.append({"日期": d, "員工ID": eid, "違規類型": "[福祉] 偏好休假未滿足", "詳細資訊": f"員工 {eid} 在偏好休假日 {d} 仍被排班"})

        elif rule_type == "avoid_high_fatigue":
            fatigue_threshold = int(param1)
            consecutive_limit = int(float(param2))
            for eid, metrics in emp_metrics.items():
                sorted_work_days = sorted(list(metrics["work_days"]))
                for i in range(len(sorted_work_days) - consecutive_limit):
                    is_fatigue_streak = True
                    for j in range(consecutive_limit + 1):
                        day = sorted_work_days[i+j]
                        # FIX: Add a default empty dict {} to the get() call to prevent crash if the key (e.g., an Admin shift) is not in demand_map.
                        # Also add 'or [0]' to handle cases where the employee has no shifts on that day, preventing max() on an empty list.
                        day_fatigue = max([demand_map.get((a["date"], a["shiftAlias"], a["post"]), {}).get("fatigueIndex", 0) for a in metrics["shifts_by_date"].get(day, [])] or [0])
                        if day_fatigue < fatigue_threshold:
                            is_fatigue_streak = False
                            break
                    if is_fatigue_streak:
                        violations.append({"日期": sorted_work_days[i], "員工ID": eid, "違規類型": "[福祉] 連續高疲勞班", "詳細資訊": f"員工 {eid} 從 {sorted_work_days[i]} 開始連續 {consecutive_limit+1} 天高疲勞班"})

        elif rule_type == "senior_coverage":
            senior_skill = param1
            try:
                required_seniors = int(float(param2))
            except (ValueError, TypeError):
                # This rule was already skipped in the solver, so just skip the check here too.
                continue
            
            if required_seniors <= 0:
                continue

            shifts_to_check = set((w["date"], w["shiftAlias"]) for w in provided["weeklyDemand"])
            for d, s_alias in shifts_to_check:
                s = pick_shift(s_alias)
                if s not in ("A", "B", "C"): continue
                
                seniors_on_shift = sum(1 for a in assignments if a["date" ] == d and a["shift"] == s and senior_skill in emps_by_id.get(a["employeeId"], {}).get("skills", []))
                
                if seniors_on_shift < required_seniors:
                    violations.append({"日期": d, "員工ID": "N/A", "違規類型": "[營運] 資深人員覆蓋不足", "詳細資訊": f"在 {d} 的 {s} 班，資深人員排班數 {seniors_on_shift} 少於要求的 {required_seniors} 人"})

        elif rule_type == "penalize_overtime":
            for eid, emp in emps_by_id.items():
                target_hours = emp.get("targetHours", 0)
                if target_hours > 0 and emp_metrics[eid]["total_hours"] > target_hours:
                    violations.append({"日期": "整月", "員工ID": eid, "違規類型": "[成本] 員工加班", "詳細資訊": f"員工 {eid} 總工時 {emp_metrics[eid]['total_hours']:.1f} 小時，超過目標的 {target_hours} 小時"})
        
        elif rule_type == "penalize_triple_shifts":
            for eid, metrics in emp_metrics.items():
                for d, day_assignments in metrics["shifts_by_date"].items():
                    if len({a["shift"] for a in day_assignments}) >= 3:
                        violations.append({"日期": d, "員工ID": eid, "違規類型": "連續三時段", "詳細資訊": f"員工 {eid} 在 {d} 被安排了 A, B, C 三個班"})

        # --- Work Pattern Rules ---
        for eid, metrics in emp_metrics.items():
            if target_eid != "ALL" and eid != target_eid:
                continue

            sorted_dates = sorted(provided["schedulePeriod"]["dates"])
            
            if rule_type == "consecutive_days_max":
                try:
                    limit = int(float(param2))
                except (ValueError, TypeError):
                    continue
                for i in range(len(sorted_dates) - limit):
                    if all(d in metrics["work_days"] for d in sorted_dates[i:i+limit+1]):
                        violations.append({"日期": sorted_dates[i], "員工ID": eid, "違規類型": "[勞基] 最大連續工作超標", "詳細資訊": f"員工 {eid} 從 {sorted_dates[i]} 開始連續工作超過 {limit} 天"})

            elif rule_type == "consecutive_days_min":
                try:
                    limit = int(float(param2))
                except (ValueError, TypeError):
                    continue
                work_streaks = []
                current_streak = 0
                for d in sorted_dates:
                    if d in metrics["work_days"]:
                        current_streak += 1
                    else:
                        if current_streak > 0:
                            work_streaks.append(current_streak)
                        current_streak = 0
                if current_streak > 0:
                    work_streaks.append(current_streak)
                
                for streak in work_streaks:
                    if 0 < streak < limit:
                        violations.append({"日期": "整月", "員工ID": eid, "違規類型": "[營運] 最小連續工作不足", "詳細資訊": f"員工 {eid} 出現了時長為 {streak} 天的工作段，少於要求的 {limit} 天"})

            elif rule_type in ("weekly_hours_max", "weekly_hours_min"):
                try:
                    limit = float(param2)
                except (ValueError, TypeError):
                    continue
                weeks = defaultdict(list)
                for d in sorted_dates:
                    weeks[datetime.strptime(d, "%Y/%m/%d").isocalendar()[1]].append(d)
                
                for week_num, week_dates in weeks.items():
                    hours_in_week = sum(get_shift_hours(a["shiftAlias"]) for d in week_dates for a in metrics["shifts_by_date"].get(d, []))
                    
                    if rule_type == "weekly_hours_max" and hours_in_week > limit:
                        violations.append({"日期": f"第 {week_num} 週", "員工ID": eid, "違規類型": "[勞基] 每週最大工時超標", "詳細資訊": f"員工 {eid} 在第 {week_num} 週工作了 {hours_in_week:.1f} 小時，超過 {param2} 小時"})
                    
                    if rule_type == "weekly_hours_min" and hours_in_week < limit:
                        violations.append({"日期": f"第 {week_num} 週", "員工ID": eid, "違規類型": "[營運] 每週最小工時不足", "詳細資訊": f"員工 {eid} 在第 {week_num} 週工作了 {hours_in_week:.1f} 小時，少於 {param2} 小時"})

    return violations


def generate_soft_constraint_report(soft_violations, total_demand, total_assignments, result, provided, audit_by_key):
    report_lines = []
    
    # --- Final Fix: Create a definitive complete assignment list inside this function ---
    solver_assignments = result["finalAssignments"]
    admin_assignments = []
    emps_by_id = {e["id"]: e for e in provided["employees"]}
    for h in provided.get("headNurseAdminAssignments", []):
        eid = h["employeeId"]
        emp_name = emps_by_id.get(eid, {}).get("name", eid)
        admin_assignments.append({
            "date": h["date"], "shift": h["shift"], "shiftAlias": h["shift"],
            "post": "行政", "employeeId": eid, "employeeName": emp_name
        })
    assignments = solver_assignments + admin_assignments

    # --- Pre-computation for detailed analysis ---
    violations_by_type = defaultdict(list)
    for v in soft_violations:
        violations_by_type[v["違規類型"]].append(v)

    emp_metrics = defaultdict(lambda: {
        "total_shifts": 0, "total_hours": 0, "weekend_days": set(), "special_clinic_counts": defaultdict(int),
        "work_days": set(), "shifts_by_date": defaultdict(list)
    })
    dates = provided["schedulePeriod"]["dates"]
    date_to_weekday = {d: datetime.strptime(d, "%Y/%m/%d").strftime("%A") for d in dates}
    demand_map = {(w["date"], w["shiftAlias"], w["post"]): w for w in provided["weeklyDemand"]}
    shift_hours_map = provided.get("shiftHoursMap", {})
    def get_shift_hours(s_alias):
        return shift_hours_map.get(s_alias, 8.0)

    for a in assignments:
        eid = a["employeeId"]
        emp_metrics[eid]["total_shifts"] += 1
        emp_metrics[eid]["total_hours"] += get_shift_hours(a["shiftAlias"])
        emp_metrics[eid]["work_days"].add(a["date"])
        emp_metrics[eid]["shifts_by_date"][a["date"]].append(a)
        if date_to_weekday.get(a["date"]) in ("Saturday", "Sunday"):
            emp_metrics[eid]["weekend_days"].add(a["date"])
        key = (a["date"], a["shiftAlias"], a["post"])
        demand_info = demand_map.get(key, {})
        if "特殊" in demand_info.get("postType", ""):
            emp_metrics[eid]["special_clinic_counts"][demand_info["postType"]] += 1

    # --- Build Report ---
    report_lines.append("軟性限制符合性分析報告")
    report_lines.append("="*30)
    
    # Correctly get total gap and overstaff count from audit data
    total_gap_count = sum(item.get("gap", 0) for item in audit_by_key)
    total_overstaff_count = sum(item.get("over", 0) for item in audit_by_key)
    split_shifts = len(violations_by_type.get("早晚分隔班", []))
    
    # Overall assessment
    if total_gap_count > 0:
        report_lines.append("總體評估: 品質不佳，存在人力缺口，需優先處理。")
    elif split_shifts > 5 or len(violations_by_type.get("[營運] 資深人員覆蓋不足", [])) > 0:
        report_lines.append("總體評估: 品質中等，為滿足人力需求在營運品質上做出較多妥協。" )
    else:
        report_lines.append("總體評估: 品質良好，人力與核心營運目標大致滿足。")
    
    # --- Section 1: Core Manpower & Quality ---
    report_lines.append("\n--- 核心人力與品質指標 ---")
    manpower_fulfillment_rate = (total_demand - total_gap_count) / total_demand if total_demand > 0 else 1.0
    report_lines.append(f"1. 人力滿足率: {manpower_fulfillment_rate:.2%} (缺口: {total_gap_count} 人次, 過剩: {total_overstaff_count} 人次)")
    
    senior_gaps = len(violations_by_type.get("[營運] 資深人員覆蓋不足", []))
    report_lines.append(f"2. 資深人員覆蓋: {senior_gaps} 個班次未達標")

    # --- Section 2: Fairness Analysis ---
    report_lines.append("\n--- 公平性指標分析 ---")
    if emp_metrics:
        all_hours = [m["total_hours"] for m in emp_metrics.values()] if emp_metrics else [0]
        report_lines.append(f"1. 總工時: 最低 {min(all_hours):.1f}h, 最高 {max(all_hours):.1f}h, 平均 {sum(all_hours)/len(all_hours):.1f}h")
        
        all_weekends = [len(m["weekend_days"]) for m in emp_metrics.values()] if emp_metrics else [0]
        report_lines.append(f"2. 週末上班天數: 最低 {min(all_weekends)} 天, 最高 {max(all_weekends)} 天, 平均 {sum(all_weekends)/len(all_weekends):.1f} 天")
    
    # --- Section 3: Employee Welfare ---
    report_lines.append("\n--- 員工福祉指標 ---")
    report_lines.append(f"1. 早晚分隔班 (A+C): {split_shifts} 人次")
    report_lines.append(f"2. 連續三時段 (A+B+C): {len(violations_by_type.get('連續三時段', []))} 人次")
    report_lines.append(f"3. 連續高疲勞班: {len(violations_by_type.get('[福祉] 連續高疲勞班', []))} 次")
    report_lines.append(f"4. 偏好休假未滿足: {len(violations_by_type.get('[福祉] 偏好休假未滿足', []))} 人次")
    report_lines.append(f"5. 員工加班: {len(violations_by_type.get('[成本] 員工加班', []))} 人次")

    # --- Section 3.5: Head Nurse Analysis ---
    head_nurse_ids = {e["id"] for e in provided["employees"] if "護理長" in e.get("skills", [])}
    if head_nurse_ids:
        report_lines.append("\n--- 護理長排班分析 ---")
        ratio_rule = next((r for r in provided.get("customRules", []) if r['rule_type'] == 'nursing_head_support_ratio'), None)
        
        emps_by_id = {e["id"]: e for e in provided["employees"]}

        for hn_id in sorted(list(head_nurse_ids)):
            if hn_id not in emps_by_id: continue
            
            emp_name = emps_by_id[hn_id].get("name", hn_id)
            metrics = emp_metrics.get(hn_id)

            if not metrics or not metrics.get("total_shifts"):
                # Fallback for nurses pre-assigned but not in final metrics (e.g., only OFF days)
                total_pre_assignments = sum(1 for pa in provided.get("preAssignments", []) if pa["employeeId"] == hn_id) + \
                                        sum(1 for pa in provided.get("headNurseAdminAssignments", []) if pa["employeeId"] == hn_id)
                if total_pre_assignments == 0:
                    report_lines.append(f"- {emp_name} ({hn_id}): 本週期無排班")
                    continue
                else: # Has pre-assignments but they were all OFFs or similar
                    total_shifts = 0
                    support_shifts = 0
            else:
                # New Logic: Base total shifts on pre-assignments for accurate ratio denominator
                total_shifts = sum(1 for pa in provided.get("preAssignments", []) if pa["employeeId"] == hn_id) + \
                               sum(1 for pa in provided.get("headNurseAdminAssignments", []) if pa["employeeId"] == hn_id)
                support_shifts = sum(1 for a in assignments if a["employeeId"] == hn_id and a["post"] != "行政")

            actual_ratio = support_shifts / total_shifts if total_shifts > 0 else 0

            report_lines.append(f"- {emp_name} ({hn_id}):")
            report_lines.append(f"  - 總班數: {total_shifts} 班 (支援 {support_shifts} 班, 行政 {total_shifts - support_shifts} 班)")
            report_lines.append(f"  - 實際支援佔比: {actual_ratio:.1%}")

            if ratio_rule:
                target_eid = ratio_rule.get("param1")
                if target_eid == "ALL" or target_eid == hn_id:
                    try:
                        # FIX: Correctly parse and display the float ratio
                        target_ratio_float = float(ratio_rule.get("param2", "0"))
                        report_lines.append(f"  - 目標支援佔比: {target_ratio_float:.1%} (來自軟性限制，參數值為 {ratio_rule.get('param2')})")
                    except (ValueError, TypeError):
                        pass
            
            fixed_admin_count = sum(1 for pa in provided.get("headNurseAdminAssignments", []) if pa["employeeId"] == hn_id)
            flexible_support_count = sum(1 for pa in provided.get("preAssignments", []) if pa["employeeId"] == hn_id and pa.get("is_support_allowed"))
            
            report_lines.append(f"  - 預排固定行政班: {fixed_admin_count} 次 (護理長人力=N/空白)")
            report_lines.append(f"  - 預排機動支援班: {flexible_support_count} 次 (護理長人力=Y)")

    # --- Section 4: Soft Constraint Analysis ---
    report_lines.append("\n" + "="*30)
    report_lines.append("\n--- 軟性限制逐項分析 ---")

    internal_to_chinese_map = {
        "penalize_day_of_week": "懲罰星期幾", "penalize_employee_post": "懲罰員工崗位",
        "penalize_employee_shift": "懲罰員工班別", "prefer_employee_post": "偏好員工崗位",
        "consecutive_days_max": "最大連續工作天數", "consecutive_days_min": "最小連續工作天數",
        "weekly_hours_max": "每週最大工時", "weekly_hours_min": "每週最小工時",
        "fair_total_hours": "總工時公平", "fair_weekend_offs": "週末休假公平",
        "fair_special_clinics": "特殊診次公平", "fair_shift_types": "班別類型公平",
        "satisfy_preferred_leave": "滿足休假偏好", "promote_consecutive_offs": "促進連續休假",
        "avoid_high_fatigue": "避免連續高疲勞班", "senior_coverage": "資深人員覆蓋",
        "penalize_overtime": "最小化加班成本",
        "promote_consecutive_shifts": "促進每日連續兩段班",
        "penalize_triple_shifts": "避免三段班",
        "nursing_head_support_ratio": "護理長支援佔比",
    }
    rule_to_violation_type = {
        "fair_total_hours": "[公平性] 總工時差異", "fair_weekend_offs": "[公平性] 週末排班差異",
        "fair_special_clinics": "[公平性] 特殊診次差異",
        "fair_shift_types": "[公平性] 班次差異",
        "satisfy_preferred_leave": "[福祉] 偏好休假未滿足", "avoid_high_fatigue": "[福祉] 連續高疲勞班",
        "senior_coverage": "[營運] 資深人員覆蓋不足", "penalize_overtime": "[成本] 員工加班",
        "penalize_triple_shifts": "連續三時段",
        "consecutive_days_max": "[勞基] 最大連續工作超標", "consecutive_days_min": "[營運] 最小連續工作不足",
        "weekly_hours_max": "[勞基] 每週最大工時超標", "weekly_hours_min": "[營運] 每週最小工時不足",
    }

    active_rules = provided.get("customRules", [])
    if not active_rules:
        report_lines.append("- 未啟用任何軟性限制規則。")
    else:
        for rule in active_rules:
            rule_type = rule["rule_type"]
            chinese_name = internal_to_chinese_map.get(rule_type, rule_type)
            if not chinese_name:
                continue

            # --- New Detailed Analysis Logic ---
            report_line = f"- {chinese_name}: "
            
            # 1. Check for rules with specific violation counts
            violation_key = rule_to_violation_type.get(rule_type)
            if violation_key:
                violation_count = 0
                if "診次差異" in violation_key:
                    v_key = f"[公平性] {rule['param1']} 診次差異"
                    violation_count = len(violations_by_type.get(v_key, []))
                elif "班次差異" in violation_key:
                    for s_type in ("A", "B", "C"):
                        v_key = f"[公平性] {s_type}班次差異"
                        violation_count += len(violations_by_type.get(v_key, []))
                else:
                    violation_count = len(violations_by_type.get(violation_key, []))
                
                if violation_count > 0:
                    report_line += f"{violation_count} 項違規"
                else:
                    report_line += "完全符合"
            
            # 2. Check for rules that are simple penalties/rewards by counting occurrences
            else:
                count = 0
                if rule_type == "penalize_day_of_week":
                    day_to_check = rule["param1"]
                    if day_to_check != "ALL":
                        count = sum(1 for a in assignments if date_to_weekday.get(a["date"], "").lower() == day_to_check.lower())
                    report_line += f"觸發 {count} 次"
                
                elif rule_type == "penalize_employee_post":
                    count = sum(1 for a in assignments if a["employeeId"] == rule["param1"] and a["post"] == rule["param2"])
                    report_line += f"觸發 {count} 次"
                
                elif rule_type == "penalize_employee_shift":
                    count = sum(1 for a in assignments if a["employeeId"] == rule["param1"] and a["shift"] == rule["param2"])
                    report_line += f"觸發 {count} 次"

                elif rule_type == "prefer_employee_post":
                    count = sum(1 for a in assignments if a["employeeId"] == rule["param1"] and a["post"] == rule["param2"])
                    report_line += f"觸發 {count} 次獎勵"

                elif rule_type == "promote_consecutive_offs":
                    for eid in emp_metrics:
                        work_days = emp_metrics[eid]["work_days"]
                        for i in range(len(dates) - 2):
                            if dates[i] in work_days and dates[i+1] not in work_days and dates[i+2] not in work_days:
                                count += 1
                    report_line += f"觸發 {count} 次獎勵"

                elif rule_type == "promote_consecutive_shifts":
                    for eid, metrics in emp_metrics.items():
                        for d, day_assignments in metrics["shifts_by_date"].items():
                            shifts = {a['shift'] for a in day_assignments}
                            if ('A' in shifts and 'B' in shifts) or ('B' in shifts and 'C' in shifts):
                                count += 1
                    report_line += f"觸發 {count} 次獎勵"
                
                elif rule_type == "nursing_head_support_ratio":
                    eid = rule["param1"]
                    if eid in emp_metrics:
                        total = emp_metrics[eid]["total_shifts"]
                        support = sum(1 for d_a in emp_metrics[eid]["shifts_by_date"].values() for a in d_a if a["post"] != "行政")
                        ratio = support / total if total > 0 else 0
                        report_line += f"員工 {eid} 支援率 {ratio:.1%} (共 {total} 班，支援 {support} 班)"
                    else:
                        report_line += f"員工 {eid} 無排班"

                else:
                    report_line += "(已納入最佳化評分)"
            
            report_lines.append(report_line)

    # --- Section 5: Employee Total Hours ---
    report_lines.append("\n" + "="*30)
    report_lines.append("\n--- 員工總工時列表 ---")
    
    emps_by_id = {e["id"]: e for e in provided["employees"]}
    sorted_emp_ids = sorted(emp_metrics.keys())
    
    for eid in sorted_emp_ids:
        metrics = emp_metrics[eid]
        emp_name = emps_by_id.get(eid, {}).get("name", eid)
        report_lines.append(f"- {emp_name} ({eid}): {metrics['total_hours']:.1f} 小時")

    # --- Detailed Lists ---
    report_lines.append("\n" + "="*30)
    for v_type in sorted(violations_by_type.keys()):
        report_lines.append(f"\n--- {v_type} 詳細清單 ({len(violations_by_type[v_type])} 項) ---")
        for v in violations_by_type[v_type]:
            report_lines.append(f"- {v['詳細資訊']} (日期: {v['日期' ]}, 員工: {v['員工ID']})")
    
    return "\n".join(report_lines)


def create_schedule_chart(assignments, provided, out_path="schedule_chart.png"):
    if not MATPLOTLIB_AVAILABLE:
        print("Matplotlib not found, skipping chart generation.")
        return None

    emps = provided["employees"]
    dates = provided["schedulePeriod"]["dates"]
    
    emp_names = [f"{e['name']}/{e['id']}" for e in emps]
    emp_ids = [e['id'] for e in emps]
    
    fig, ax = plt.subplots(figsize=(20, len(emp_names) * 0.5))
    
    # Use a font that supports Chinese characters
    plt.rcParams['font.sans-serif'] = ['Meiryo', 'Microsoft JhengHei', 'SimHei', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False

    shift_colors = {'A': 'skyblue', 'B': 'lightgreen', 'C': 'lightcoral'}
    shift_order = {'A': 0, 'B': 1, 'C': 2}
    
    for i, eid in enumerate(emp_ids):
        for j, date in enumerate(dates):
            day_assignments = [a for a in assignments if a['employeeId'] == eid and a['date'] == date]
            if day_assignments:
                # New logic: Draw bars in 3 fixed slots for A, B, C shifts
                bar_width = 1.0 / 3.0
                for a in day_assignments:
                    shift = a['shift']
                    if shift in shift_order:
                        shift_pos = shift_order[shift]
                        ax.barh(i, bar_width, left=j + shift_pos * bar_width, height=0.6, 
                                color=shift_colors.get(shift, 'grey'), 
                                edgecolor="black")

    ax.set_yticks(range(len(emp_names)))
    ax.set_yticklabels(emp_names)
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([d.split('/')[-1] for d in dates], rotation=90)
    ax.set_xlabel("日期")
    ax.set_ylabel("員工")
    ax.set_title("排班甘特圖")
    ax.set_xlim(-0.5, len(dates) - 0.5)
    ax.invert_yaxis()
    plt.tight_layout()
    
    plt.savefig(out_path)
    plt.close()
    return out_path


def analyze_shift_eligibility(provided, target_date, target_shift_alias, target_post):
    """
    Analyzes the eligibility of all employees for a specific shift.
    Returns a structured dictionary with analysis results.
    """
    employees = provided["employees"]
    weekly = provided["weeklyDemand"]
    leave = provided.get("leaveRequests", [])

    # Find the specific demand entry
    demand_entry = None
    for r in weekly:
        if norm_date(r.get("date")) == norm_date(target_date) and \
           pick_shift(r.get("shiftAlias")) == pick_shift(target_shift_alias) and \
           r.get("post") == target_post:
            demand_entry = r
            break
    
    if not demand_entry:
        return {"error": "Could not find a matching demand entry."}

    required_skills = demand_entry.get("skillsRequired", [])
    
    hard_off = {
        (norm_date(l.get("date")), str(l.get("employeeId") or "").strip())
        for l in leave
        if str(l.get("preset", "") or l.get("預定班別", "")).upper() == "OFF"
    }
    
    potential_candidates = []
    failed_employees = []
    for e in employees:
        eid = e['id']
        name = e['name']
        reasons = []

        if (norm_date(target_date), eid) in hard_off:
            reasons.append("正在休假 (OFF)")
        if norm_date(target_date) not in e.get("availableDates", []):
            reasons.append(f"日期不可上 (可上日期未包含本日)")
        if pick_shift(target_shift_alias) not in e.get("availableShifts", []):
            reasons.append(f"班別不符 (可上班別: {e.get('availableShifts')})")
        if not eligible_ok(e.get("eligiblePosts"), target_post):
            reasons.append(f"崗位資格不符 (可上崗位: {e.get('eligiblePosts')})")
        if not skills_ok(e.get("skills"), required_skills):
            reasons.append(f"缺少需求技能 (擁有: {e.get('skills')}, 需求: {required_skills})")

        if not reasons:
            potential_candidates.append({"id": eid, "name": name})
        else:
            failed_employees.append({"id": eid, "name": name, "reasons": reasons})

    return {
        "demand": demand_entry,
        "candidates": potential_candidates,
        "failures": failed_employees
    }


def generate_gap_analysis_report(provided, gaps):
    """
    Generates a detailed analysis report for all manpower gaps.
    """
    report_lines = []
    report_lines.append("本報告針對所有出現人力缺口的崗位，逐一分析原因並提供建議。")
    
    for gap_item in gaps:
        d, s, p = gap_item["key"].split("|")
        
        report_lines.append("\n" + "="*50)
        report_lines.append(f"崗位分析: {d} {s}班 {p}")
        report_lines.append(f"  - 需求人數: {gap_item['demand']}, 缺口人數: {gap_item['gap']}")
        report_lines.append("="*50)

        analysis = analyze_shift_eligibility(provided, d, s, p)

        if analysis.get("error"):
            report_lines.append(f"  - 分析錯誤: {analysis['error']}")
            continue

        # --- Analysis Section ---
        report_lines.append("\n--- 硬性限制分析 (為何多數員工無法排班) ---")
        for emp in analysis["failures"]:
            report_lines.append(f"- {emp['name']} ({emp['id']}): {'; '.join(emp['reasons'])}")

        # --- Conclusion and Suggestion Section ---
        report_lines.append("\n--- 結論與建議 ---")
        candidates = analysis["candidates"]
        if not candidates:
            report_lines.append(">> 結論: 沒有任何員工符合該崗位的基本排班要求 (硬性限制)。")
            report_lines.append(">> 建議:")
            report_lines.append("   1. 請檢查「人員資料庫」，確認是否有足夠員工擁有此崗位的「可上崗位」資格與「技能標籤」。")
            report_lines.append("   2. 請檢查「員工預排班表」，確認是否過多符合資格的員工在當天集中排休(OFF)。")
            report_lines.append("   3. 請檢查員工的「可上日期」與「可上班別」設定是否過於嚴格。")
        else:
            candidate_names = [f"{c['name']}({c['id']})" for c in candidates]
            report_lines.append(f">> 結論: 系統找到 {len(candidates)} 位符合資格的潛在人選，但最終未指派。")
            report_lines.append(f">> 潛在人選名單: {', '.join(candidate_names)}")
            report_lines.append(">> 原因: 這通常是因為指派這些人選會違反某個權重較高的「軟性限制」(例如最大連續工作天數、班別公平性等)，")
            report_lines.append("   求解器權衡後，寧可接受人力缺口，也不願違反這些更高分的懲罰。")
            report_lines.append(">> 建議:")
            report_lines.append("   1. (短期) 手動調整：從「潛在人選名單」中，挑選一位員工手動加入班表，以解決燃眉之急。")
            report_lines.append("   2. (長期) 放寬規則：前往「軟性限制」工作表，適度「降低」部分公平性或福祉規則的權重(weight)，")
            report_lines.append("      給予求解器更大的彈性空間來優先滿足人力。")
            
    return report_lines


def debug_schedule(provided, target_date, target_shift_alias, target_post):
    """
    Analyzes and prints the eligibility of each employee for a specific shift.
    """
    print(f"--- Debugging Schedule for: Date={target_date}, Shift={target_shift_alias}, Post={target_post} ---")
    
    analysis = analyze_shift_eligibility(provided, target_date, target_shift_alias, target_post)

    if analysis.get("error"):
        print(f"\n[ERROR] {analysis['error']}")
        return

    demand_info = analysis["demand"]
    required_skills = demand_info.get("skillsRequired", [])
    print(f"\nDemand Requirements:")
    print(f"  - Post: {demand_info['post']}")
    print(f"  - Required Skills: {required_skills if required_skills else 'None'}")
    print("-" * 30)

    print("\n--- Analyzing Employee Eligibility ---")
    for emp in analysis["failures"]:
        print(f"[FAIL] {emp['name']} ({emp['id']}): {'; '.join(emp['reasons'])}")
    for emp in analysis["candidates"]:
        print(f"[PASS] {emp['name']} ({emp['id']}) is a potential candidate.")

    print("\n--- Conclusion ---")
    if not analysis["candidates"]:
        print("No employees met all hard constraints. This is the reason for the manpower gap.")
    else:
        candidate_names = [c['id'] for c in analysis['candidates']]
        print(f"Found {len(candidate_names)} potential candidates: {candidate_names}")
        print("The gap is likely caused by high-penalty SOFT constraints (e.g., max consecutive work days, fairness rules, etc.).")
        print("Check the '软性限制符合性查核' sheet in output.xlsx for violations related to these employees.")


# Import the missing functions from schedule_cpsat
from .schedule_cpsat import eligible_ok, skills_ok

def write_output_excel(out_path, result, provided):
    """Write complete output to Excel with all 5 sheets like the original run.py"""
    # Build the final schedule grid and get the single source of truth for all assignments
    rows_for_sheet, complete_assignments = build_rows(result["finalAssignments"], provided)
    rows_df = pd.DataFrame(rows_for_sheet)
    
    # Use the complete list for all subsequent reports and checks
    bykey = pd.DataFrame(result["audit"]["byKey"])
    detailed_report_lines = build_daily_analysis_report(provided, complete_assignments)
    detailed_report_df = pd.DataFrame(detailed_report_lines, columns=['每日分析'])

    # Perform compliance checks
    hard_violations = check_hard_constraints(complete_assignments, provided)
    soft_violations = check_soft_constraints(result, provided, result["audit"]["byKey"])
    
    hard_violations_df = pd.DataFrame(hard_violations)
    soft_violations_df = pd.DataFrame(soft_violations)

    # Generate report and chart
    report_text = generate_soft_constraint_report(soft_violations, result["audit"]["summary"]["totalDemand"], len(complete_assignments), result, provided, result["audit"]["byKey"])
    chart_path = create_schedule_chart(complete_assignments, provided)

    # Generate Gap Analysis Report if gaps exist
    gaps = [item for item in result["audit"]["byKey"] if item.get("gap", 0) > 0]
    gap_analysis_df = pd.DataFrame()
    if gaps:
        gap_report_lines = generate_gap_analysis_report(provided, gaps)
        gap_analysis_df = pd.DataFrame(gap_report_lines, columns=['人力缺口分析與建議'])

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        rows_df.to_excel(w, sheet_name="排班結果表", index=False)
        
        if not gap_analysis_df.empty:
            gap_analysis_df.to_excel(w, sheet_name="人力缺口分析與建議", index=False)

        detailed_report_df.to_excel(w, sheet_name="合併報表", index=False)
        if not bykey.empty:
            bykey.to_excel(w, sheet_name="排班審核明細", index=False)
        
        hard_violations_df.to_excel(w, sheet_name="硬性限制符合性查核", index=False)
        soft_violations_df.to_excel(w, sheet_name="軟性限制符合性查核", index=False)
        
        report_df = pd.DataFrame([line.split(': ', 1) if ': ' in line else [line, ''] for line in report_text.split('\n')], columns=['項目', '內容'])
        report_df.to_excel(w, sheet_name="分析報告與圖表", index=False, header=False)

        if chart_path and os.path.exists(chart_path):
            try:
                from openpyxl.drawing.image import Image
                wb = w.book
                ws = wb["分析報告與圖表"]
                img = Image(chart_path)
                ws.add_image(img, f'A{len(report_df) + 3}')
            except ImportError:
                logger.warning("openpyxl.drawing.image not available, skipping chart insertion")
            except Exception as e:
                logger.warning(f"Error inserting chart: {e}")
