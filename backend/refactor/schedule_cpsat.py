#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP-SAT Scheduling Module (Simplified)
Main scheduling logic decoupled from I/O operations
"""

import json
import re
import os
import sys
from datetime import datetime
from collections import defaultdict, OrderedDict
import pandas as pd
from ortools.sat.python import cp_model
from typing import Dict, List, Optional, Any, Tuple

# Import our data providers and utilities
from .data_provider import DataProvider
from .utils.logger import get_logger

# Try to import matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import fontManager
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Initialize logger
logger = get_logger(__name__)

# ---------------------- parsing helpers ----------------------
def norm_date(s: str) -> str:
    s = str(s or "").strip().replace("-", "/")
    
    # Try different date formats
    # Format 1: YYYY/MM/DD or YYYY/M/D
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}/{int(mo):02d}/{int(d):02d}"
    
    # Format 2: M/D/YYYY or MM/DD/YYYY (US format)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        mo, d, y = m.groups()
        return f"{y}/{int(mo):02d}/{int(d):02d}"
    
    # Format 3: D/M/YYYY or DD/MM/YYYY (European format)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}/{int(mo):02d}/{int(d):02d}"
    
    # If no format matches, return as is
    return s

def pick_shift(v: str) -> str:
    s = str(v or "").strip().upper().replace("'", "")
    if s in ("A", "B", "C"):
        return s
    if "早" in s:
        return "A"
    if "中" in s:
        return "B"
    if "晚" in s:
        return "C"
    return s

def split_csv(value):
    if pd.isna(value) or value is None:
        return []
    if isinstance(value, list):
        return value
    s = str(value).strip()
    if not s:
        return []
    s = s.replace("、", ",").replace("，", ",")
    s = re.sub(r'\\\[(.*?)\\]', r'\\1', s)
    s = s.replace('"', '').replace("'", "")
    return [x.strip() for x in s.split(",") if x.strip()]

def cat_of_post(post: str) -> str:
    p = str(post or "").lower()
    if "二線" in p or "back" in p or "second" in p:
        return "二線"
    if "藥" in p or "pharm" in p:
        return "藥局"
    if "護" in p or "nurse" in p:
        return "護"
    if "櫃" in p or "前台" in p or "desk" in p or "front" in p:
        return "櫃"
    return "櫃"

def skills_ok(emp_skills, req):
    if not req:
        return True
    have = {str(x).lower() for x in (emp_skills or [])}
    need = {str(x).lower() for x in (req or [])}
    return not need.isdisjoint(have)

def eligible_ok(eligible_posts, post):
    if not eligible_posts:
        return True
    p = str(post or "").lower()
    return any(str(ep).lower() in p or p in str(ep).lower() for ep in eligible_posts)

# ---------------------- Data Processing ----------------------
def process_input_data(data_provider: DataProvider) -> Dict[str, Any]:
    """Process input data from any data provider into the format expected by the solver"""
    logger.info("Processing input data...")
    
    # Load data from provider
    emp_df = data_provider.get_employee_data()
    dem_df = data_provider.get_demand_data()
    pre_df = data_provider.get_pre_assignments_data()
    rules_df = data_provider.get_rules_data()
    shift_def_df = data_provider.get_shift_definitions_data()
    
    # Default penalties
    penalties = {
        "ineligible_post": 1000,
        "skill_mismatch": 2000,
        "skill_preference_mismatch": 200,
        "consecutive_shift": 100,
        "split_shift": 5000,
        "unmet_demand": 100000,
        "over_staffing": 100000,
    }
    custom_rules = []
    
    # Process rules if available - Enhanced logic from original run.py
    if not rules_df.empty:
        try:
            # Check if it's the new format by looking for 'rule_type' or '規則類型'
            if any('rule_type' in str(col) or '規則類型' in str(col) for col in rules_df.columns):
                # Chinese to English mapping for custom rule types
                rule_type_map = {
                    "懲罰星期幾": "penalize_day_of_week",
                    "懲罰員工崗位": "penalize_employee_post",
                    "懲罰員工班別": "penalize_employee_shift",
                    "偏好員工崗位": "prefer_employee_post",
                    "最大連續工作天數": "consecutive_days_max",
                    "最小連續工作天數": "consecutive_days_min",
                    "每週最大工時": "weekly_hours_max",
                    "每週最小工時": "weekly_hours_min",
                    # Fairness and new welfare rules
                    "總工時公平": "fair_total_hours",
                    "週末休假公平": "fair_weekend_offs",
                    "特殊診次公平": "fair_special_clinics",
                    "班別類型公平": "fair_shift_types",
                    "滿足休假偏好": "satisfy_preferred_leave",
                    "促進連續休假": "promote_consecutive_offs",
                    "避免連續高疲勞班": "avoid_high_fatigue",
                    "資深人員覆蓋": "senior_coverage",
                    "最小化加班成本": "penalize_overtime",
                    "促進每日連續兩段班": "promote_consecutive_shifts",
                    "避免三段班": "penalize_triple_shifts",
                    "懲罰人力過剩": "over_staffing",
                    "懲罰人力缺口": "unmet_demand",
                    "護理長支援佔比": "nursing_head_support_ratio",
                }
                
                for i, r in rules_df.iterrows():
                    rule_type_input = str(r.get("rule_type") or r.get("規則類型") or r.get("規則類型 (rule_type)") or "").replace('\xa0', ' ').strip()
                    weight = r.get("weight") or r.get("權重") or r.get("權重 (weight)")

                    if not rule_type_input or pd.isna(weight) or int(weight) < 0: # Allow 0 weight to disable
                        continue
                    
                    rule_type_internal = rule_type_map.get(rule_type_input, rule_type_input).lower()

                    # Separate core penalties from other custom rules
                    if rule_type_internal in ("over_staffing", "unmet_demand"):
                        penalties[rule_type_internal] = int(weight)
                    else:
                        custom_rules.append({
                            "rule_type": rule_type_internal,
                            "param1": str(r.get("param1") or r.get("參數1") or r.get("參數1 (param1)") or ""),
                            "param2": str(r.get("param2") or r.get("參數2") or r.get("參數2 (param2)") or ""),
                            "param3": str(r.get("param3") or r.get("參數3") or r.get("閾值") or r.get("閾值 (param3)") or "0"),
                            "weight": int(weight),
                        })
            # Fallback to old key-value format
            else:
                for _, r in rules_df.iterrows():
                    rule = str(r.get("key") or r.get("規則") or "").strip().lower()
                    weight = r.get("weight") or r.get("權重")
                    if rule and pd.notna(weight):
                        penalties[rule] = int(weight)
        except Exception as e:
            logger.warning(f"Error parsing rules data: {e}. Using default penalties.")
    else:
        logger.info("No rules data found. Using default penalties.")

    # Process employees
    employees = []
    for _, r in emp_df.iterrows():
        eid = str(r.get("員工ID") or "").strip()
        if not eid:
            continue
        employees.append({
            "id": eid,
            "name": r.get("姓名") or eid,
            "eligiblePosts": split_csv(r.get("可任崗位")),
            "skills": split_csv(r.get("技能標籤")),
            "availableShifts": [pick_shift(s) for s in split_csv(r.get("可上班別"))] or ["A", "B", "C"],
            "availableDates": [norm_date(d) for d in split_csv(r.get("可上日期"))],
            "startDate": norm_date(r.get("可開始上班日期")) if pd.notna(r.get("可開始上班日期")) else None,
            "targetHours": int(r.get("目標月總工時") or 0),
        })

    # Process weekly demand
    weekly = []
    for _, r in dem_df.iterrows():
        d = norm_date(r.get("日期"))
        s = pick_shift(r.get("班別代號") or (r.get("baseShifts") or [None])[0])
        p = r.get("崗位")
        dem = int(r.get("需求人數") or 0)
        req_sk = split_csv(r.get("需求技能") or [])
        if not d or not s or not p:
            continue
        weekly.append({
            "date": d,
            "post": p,
            "shiftAlias": s,
            "baseShifts": [s],
            "skillsRequired": req_sk,
            "demand": dem,
            "postType": str(r.get("崗位類型") or "一般"),
            "fatigueIndex": int(r.get("疲勞指數") or 1),
        })

    # Process leave requests and pre-assignments
    leaveRequests = []
    preAssignments = []
    headNurseAdminAssignments = []

    # Identify head nurses
    head_nurse_ids = {str(e.get("id")) for e in employees if "護理長" in e.get("skills", [])}

    for _, r in pre_df.iterrows():
        d = norm_date(r.get("日期"))
        eid = str(r.get("員工ID") or "").strip()
        preset = str(r.get("班別") or r.get("預定班別") or "").strip()
        
        if not (eid and d and preset):
            continue

        if "OFF" in preset.upper() or "偏好" in preset:
            leaveRequests.append({"date": d, "employeeId": eid, "preset": preset})
        elif eid in head_nurse_ids:
            is_flexible_support = str(r.get("護理長人力") or "N").strip().upper() == "Y"
            if is_flexible_support:
                preAssignments.append({
                    "date": d, 
                    "employeeId": eid, 
                    "shift": pick_shift(preset),
                    "is_support_allowed": True 
                })
            else:
                headNurseAdminAssignments.append({
                    "date": d, 
                    "employeeId": eid, 
                    "shift": pick_shift(preset)
                })
        else:
            preAssignments.append({
                "date": d, 
                "employeeId": eid, 
                "shift": pick_shift(preset),
                "is_support_allowed": False
            })

    # Process dates with flexible date parsing
    date_set = sorted({w["date"] for w in weekly})
    for e in employees:
        if e.get("startDate"):
            try:
                # Try different date formats for parsing
                start_date = pd.to_datetime(e["startDate"], format='%Y/%m/%d')
            except ValueError:
                try:
                    start_date = pd.to_datetime(e["startDate"], format='%m/%d/%Y')
                except ValueError:
                    start_date = pd.to_datetime(e["startDate"], format='%d/%m/%Y')
            
            all_dates_dt = []
            for d in date_set:
                try:
                    all_dates_dt.append(pd.to_datetime(d, format='%Y/%m/%d'))
                except ValueError:
                    try:
                        all_dates_dt.append(pd.to_datetime(d, format='%m/%d/%Y'))
                    except ValueError:
                        all_dates_dt.append(pd.to_datetime(d, format='%d/%m/%Y'))
            
            e["availableDates"] = [d.strftime('%Y/%m/%d') for d in all_dates_dt if d >= start_date]
        elif not e["availableDates"]:
            e["availableDates"] = list(date_set)

    # Process shift hours map
    shift_hours_map = {}
    if not shift_def_df.empty:
        try:
            for _, r in shift_def_df.iterrows():
                shift_alias = str(r.get("班別代號") or "").strip()
                hours = float(r.get("總時數(小時)") or 0)
                if shift_alias and hours > 0:
                    shift_hours_map[shift_alias] = hours
        except Exception as e:
            logger.warning(f"Error processing shift definitions: {e}")

    logger.info(f"Processed {len(employees)} employees, {len(weekly)} demand entries")
    
    return {
        "schedulePeriod": {"dates": date_set},
        "employees": employees,
        "weeklyDemand": weekly,
        "leaveRequests": leaveRequests,
        "preAssignments": preAssignments,
        "headNurseAdminAssignments": headNurseAdminAssignments,
        "penalties": penalties,
        "customRules": custom_rules,
        "shiftHoursMap": shift_hours_map,
    }

# ---------------------- CP-SAT solve ----------------------
def solve_cpsat(provided: Dict[str, Any], time_limit: float = 90.0) -> Dict[str, Any]:
    """Main CP-SAT solving function - Complete version from original run.py"""
    logger.info(f"Starting CP-SAT solving with time limit: {time_limit}s")
    
    dates = provided["schedulePeriod"]["dates"]
    employees = provided["employees"]
    weekly = provided["weeklyDemand"]
    leave = provided.get("leaveRequests", [])
    preAssignments = provided.get("preAssignments", [])
    headNurseAdminAssignments = provided.get("headNurseAdminAssignments", [])
    penalties_config = provided.get("penalties", {})
    custom_rules = provided.get("customRules", [])
    shift_hours_map = provided.get("shiftHoursMap", {})
    num_employees = len(employees)

    def get_shift_hours(s_alias):
        # Multiply by 100 and convert to int to avoid float issues in CP-SAT
        return int(shift_hours_map.get(s_alias, 8.0) * 100)

    # --- New constants and helpers for advanced rules ---
    
    # Group dates by ISO week number
    weeks = defaultdict(list)
    for d in dates:
        weeks[datetime.strptime(d, "%Y/%m/%d").isocalendar().week].append(d)
    
    # Get penalty values with defaults from the config dict
    p_split_shift = penalties_config.get("split_shift", 5000)
    # Ensure meeting demand is the highest priority by multiplying its penalty
    p_unmet_demand = penalties_config.get("unmet_demand", 100000) * 10000
    p_over_staffing = penalties_config.get("over_staffing", 100000) * 10000

    # index sets
    E = employees # Use the full list directly

    DSP = []  # list of (date, shift, post)
    demand = []
    skills_req = []
    post_types = []
    fatigue_indices = []
    demand_map = {} # New: For quick lookup
    for r in weekly:
        d = norm_date(r.get("date"))
        s = pick_shift((r.get("baseShifts") or [None])[0] or r.get("shiftAlias") or r.get("shift") or "")
        p = r.get("post")
        dem = int(r.get("demand") or 0)
        if not d or not s or not p:
            continue
        DSP.append((d, s, p))
        demand.append(dem)
        skills_req.append(r.get("skillsRequired") or [])
        post_types.append(r.get("postType", "一般"))
        fatigue_indices.append(r.get("fatigueIndex", 1))
        demand_map[(d, s, p)] = r # New: Populate the map

    # availability & preferences
    avail_date = {}
    avail_shift = {}
    for e in E:
        eid = str(e.get("id") or e.get("employeeId") or "").strip()
        avail_date[eid] = set(e.get("availableDates") or dates)
        avail_shift[eid] = set(pick_shift(s) for s in (e.get("availableShifts") or ["A", "B", "C"]))
    
    hard_off = {
        (norm_date(l.get("date")), str(l.get("employeeId") or "").strip())
        for l in leave
        if str(l.get("preset", "")).upper() == "OFF"
    }
    preferred_leave = {
        (norm_date(l.get("date")), str(l.get("employeeId") or "").strip())
        for l in leave
        if "偏好" in str(l.get("preset", ""))
    }

    model = cp_model.CpModel()

    # decision x[e,k] : employee e assigned to DSP[k]
    x = {}
    penalties = []

    # Pre-calculate weekday for each date to speed up rule matching
    date_to_weekday = {d: datetime.strptime(d, "%Y/%m/%d").strftime("%A") for d in dates}

    for ei, e in enumerate(E):
        eid = str(e.get("id") or e.get("employeeId") or "").strip()
        for k, (d, s, p) in enumerate(DSP):
            # Hard constraints first
            demand_key = (d, s, p)
            current_demand = demand_map.get(demand_key, {})
            
            if not eligible_ok(e.get("eligiblePosts"), p):
                x[(ei, k)] = None
                continue
            if not skills_ok(e.get("skills"), current_demand.get("skillsRequired", [])):
                x[(ei, k)] = None
                continue
            if (d, eid) in hard_off:
                x[(ei, k)] = None
                continue
            if d not in avail_date[eid]:
                x[(ei, k)] = None
                continue
            if pick_shift(s) not in avail_shift[eid]:
                x[(ei, k)] = None
                continue
            
            var = model.NewBoolVar(f"x_e{ei}_k{k}")
            x[(ei, k)] = var

            # --- New: Penalize for not meeting preferred skill ---
            required_skills = current_demand.get("skillsRequired", [])
            if len(required_skills) > 1:
                primary_skill = required_skills[0]
                emp_skills = e.get("skills", [])
                if primary_skill not in emp_skills:
                    p_skill_pref = penalties_config.get("skill_preference_mismatch", 200)
                    penalties.append(p_skill_pref * var)
            
            # Penalties from custom rules (simple ones)
            for rule in custom_rules:
                if rule["rule_type"] in ("penalize_day_of_week", "penalize_employee_post", "penalize_employee_shift", "prefer_employee_post"):
                    match = False
                    rule_type = rule["rule_type"]
                    param1 = rule["param1"]
                    param2 = rule["param2"]
                    weight = rule["weight"]

                    if rule_type == "penalize_day_of_week":
                        if date_to_weekday.get(d, "").lower() == param1.lower():
                            match = True
                    elif rule_type == "penalize_employee_post":
                        if eid == param1 and p == param2:
                            match = True
                    elif rule_type == "penalize_employee_shift":
                        if eid == param1 and pick_shift(s) == param2:
                            match = True
                    elif rule_type == "prefer_employee_post":
                        # This is a preference, so it's a negative penalty (a reward)
                        if eid == param1 and p == param2:
                            penalties.append(-weight * var)
                    
                    if match:
                        penalties.append(weight * var)
                else:
                    # This is an advanced rule that will be handled later
                    continue

    # --- Hard Constraints for Pre-Assignments ---
    emp_id_map = {str(e.get("id") or e.get("employeeId") or ""): i for i, e in enumerate(E)}
    head_nurse_ids = {str(e.get("id")) for e in E if "護理長" in e.get("skills", [])}

    # --- CORRECTED Head Nurse Logic: Direct Constraint per Pre-Assignment ---

    # For flexible/support shifts ('Y'), the nurse MUST be assigned to exactly ONE post.
    for pa in preAssignments:
        eid = pa["employeeId"]
        if eid not in emp_id_map or not pa.get("is_support_allowed"): continue
        ei = emp_id_map[eid]

        # Find all possible posts for this employee on this specific date and shift type
        possible_posts_vars = [
            var for (e_idx, k), var in x.items() 
            if e_idx == ei and DSP[k][0] == pa["date"] and DSP[k][1] == pa["shift"] and var is not None
        ]
        
        if possible_posts_vars:
            # Change to <= 1: The head nurse CAN be assigned to at most one post.
            # This makes the assignment optional. The solver will only assign if it helps reduce penalties (i.e., fills a gap).
            model.Add(cp_model.LinearExpr.Sum(possible_posts_vars) <= 1)

    # For fixed admin shifts ('N'/blank), the nurse CANNOT be assigned to any post by the solver.
    for h in headNurseAdminAssignments:
        eid = h["employeeId"]
        if eid not in emp_id_map: continue
        ei = emp_id_map[eid]
        
        # Find all possible posts for this employee on this specific date and shift type
        forbidden_posts_vars = [
            var for (e_idx, k), var in x.items() 
            if e_idx == ei and DSP[k][0] == h["date"] and DSP[k][1] == h["shift"] and var is not None
        ]
        
        if forbidden_posts_vars:
            # Add a hard constraint: the sum of assignments for this shift must be 0.
            model.Add(cp_model.LinearExpr.Sum(forbidden_posts_vars) == 0)

    # For any other regular staff pre-assignment, they must also work exactly one post.
    for pa in preAssignments:
        eid = pa["employeeId"]
        if eid in head_nurse_ids or eid not in emp_id_map: continue
        ei = emp_id_map[eid]
        
        all_vars_for_shift = [
            var for (e_idx, k), var in x.items() 
            if e_idx == ei and DSP[k][0] == pa["date"] and DSP[k][1] == pa["shift"] and var is not None
        ]
        if all_vars_for_shift:
            model.Add(cp_model.LinearExpr.Sum(all_vars_for_shift) == 1)


    # over/under for coverage
    over = [model.NewIntVar(0, 1000, f"over_{k}") for k in range(len(DSP))]
    under = [model.NewIntVar(0, 1000, f"under_{k}") for k in range(len(DSP))]

    for k, (d, s, p) in enumerate(DSP):
        assigned = [x[(ei, k)] for ei in range(len(E)) if x.get((ei, k)) is not None]
        sum_assigned = cp_model.LinearExpr.Sum(assigned) if assigned else 0
        dem = demand[k]
        if assigned:
            model.Add(sum_assigned - dem - over[k] + under[k] == 0)
        else:
            model.Add(0 - dem - over[k] + under[k] == 0)

    # --- Aux variables for fairness and advanced rules ---
    is_working = {}
    shifts_per_employee = [[] for _ in E]
    weekend_shifts_per_employee = [[] for _ in E]
    special_clinic_shifts = defaultdict(lambda: [[] for _ in E])
    shift_type_counts = {'A': [[] for _ in E], 'B': [[] for _ in E], 'C': [[] for _ in E]}

    for ei, e in enumerate(E):
        for d_idx, d in enumerate(dates):
            per_day = [x[(ei, k)] for k, (dd, ss, pp) in enumerate(DSP) if dd == d and x.get((ei, k)) is not None]
            is_working[ei, d] = model.NewBoolVar(f"is_working_e{ei}_d{d_idx}")
            if per_day:
                model.Add(cp_model.LinearExpr.Sum(per_day) >= 1).OnlyEnforceIf(is_working[ei, d])
                model.Add(cp_model.LinearExpr.Sum(per_day) == 0).OnlyEnforceIf(is_working[ei, d].Not())
                model.Add(cp_model.LinearExpr.Sum(per_day) <= 3) # Allow 3 shifts for penalization
            else:
                model.Add(is_working[ei, d] == 0)

            for s_type in ("A", "B", "C"):
                same_shift = [x[(ei, k)] for k, (dd, ss, pp) in enumerate(DSP) if dd == d and pick_shift(ss) == s_type and x.get((ei, k)) is not None]
                if same_shift:
                    model.Add(cp_model.LinearExpr.Sum(same_shift) <= 1)

        for k, (d, s, p) in enumerate(DSP):
            var = x.get((ei, k))
            if var is None: continue
            shifts_per_employee[ei].append(var)
            if date_to_weekday.get(d, "") in ("Saturday", "Sunday"):
                weekend_shifts_per_employee[ei].append(var)
            
            ptype = post_types[k]
            if "特殊" in ptype:
                special_clinic_shifts[ptype][ei].append(var)
            
            shift_type_counts[pick_shift(s)][ei].append(var)

    # --- Shift Pattern Rules (Split, Consecutive) ---
    rule_prom_consecutive = next((r for r in custom_rules if r['rule_type'] == 'promote_consecutive_shifts'), None)
    rule_pen_triple = next((r for r in custom_rules if r['rule_type'] == 'penalize_triple_shifts'), None)

    for ei, e in enumerate(E):
        for d_idx, d in enumerate(dates):
            vars_a = [v for k, v in x.items() if k[0] == ei and DSP[k[1]][0] == d and pick_shift(DSP[k[1]][1]) == 'A' and v is not None]
            vars_b = [v for k, v in x.items() if k[0] == ei and DSP[k[1]][0] == d and pick_shift(DSP[k[1]][1]) == 'B' and v is not None]
            vars_c = [v for k, v in x.items() if k[0] == ei and DSP[k[1]][0] == d and pick_shift(DSP[k[1]][1]) == 'C' and v is not None]

            if not vars_a and not vars_b and not vars_c:
                continue

            on_a = model.NewBoolVar(f'on_a_e{ei}_d{d_idx}')
            on_b = model.NewBoolVar(f'on_b_e{ei}_d{d_idx}')
            on_c = model.NewBoolVar(f'on_c_e{ei}_d{d_idx}')

            model.Add(cp_model.LinearExpr.Sum(vars_a) >= 1).OnlyEnforceIf(on_a)
            model.Add(cp_model.LinearExpr.Sum(vars_a) == 0).OnlyEnforceIf(on_a.Not())
            model.Add(cp_model.LinearExpr.Sum(vars_b) >= 1).OnlyEnforceIf(on_b)
            model.Add(cp_model.LinearExpr.Sum(vars_b) == 0).OnlyEnforceIf(on_b.Not())
            model.Add(cp_model.LinearExpr.Sum(vars_c) >= 1).OnlyEnforceIf(on_c)
            model.Add(cp_model.LinearExpr.Sum(vars_c) == 0).OnlyEnforceIf(on_c.Not())

            # Penalize split shifts (A+C)
            on_ac = model.NewBoolVar(f'on_ac_e{ei}_d{d_idx}')
            model.AddBoolAnd([on_a, on_c]).OnlyEnforceIf(on_ac)
            model.AddBoolOr([on_a.Not(), on_c.Not()]).OnlyEnforceIf(on_ac.Not())
            penalties.append(p_split_shift * on_ac)

            # Reward consecutive shifts (A+B or B+C) if rule is active
            if rule_prom_consecutive:
                on_ab = model.NewBoolVar(f'on_ab_e{ei}_d{d_idx}')
                model.AddBoolAnd([on_a, on_b]).OnlyEnforceIf(on_ab)
                model.AddBoolOr([on_a.Not(), on_b.Not()]).OnlyEnforceIf(on_ab.Not())
                # A promotion is a reward, so we subtract the weight (negative penalty)
                penalties.append(-rule_prom_consecutive['weight'] * on_ab)

                on_bc = model.NewBoolVar(f'on_bc_e{ei}_d{d_idx}')
                model.AddBoolAnd([on_b, on_c]).OnlyEnforceIf(on_bc)
                model.AddBoolOr([on_b.Not(), on_c.Not()]).OnlyEnforceIf(on_bc.Not())
                # A promotion is a reward, so we subtract the weight (negative penalty)
                penalties.append(-rule_prom_consecutive['weight'] * on_bc)

            # Penalize triple shifts (A+B+C) if rule is active
            if rule_pen_triple:
                on_abc = model.NewBoolVar(f'on_abc_e{ei}_d{d_idx}')
                model.AddBoolAnd([on_a, on_b, on_c]).OnlyEnforceIf(on_abc)
                model.AddBoolOr([on_a.Not(), on_b.Not(), on_c.Not()]).OnlyEnforceIf(on_abc.Not())
                penalties.append(rule_pen_triple['weight'] * on_abc)

    # --- Process advanced custom rules ---
    for rule in custom_rules:
        rule_type = rule["rule_type"]
        param1 = rule["param1"]
        param2 = rule["param2"]
        weight = rule["weight"]

        # --- Fairness Rules ---
        def add_fairness_penalty(variables_per_employee, rule_weight):
            if not any(variables_per_employee): return
            total_sum = cp_model.LinearExpr.Sum([cp_model.LinearExpr.Sum(v) for v in variables_per_employee if v])
            avg_val_num = total_sum 
            avg_val_den = num_employees
            
            for emp_vars in variables_per_employee:
                if not emp_vars: continue
                deviation = model.NewIntVar(-1000 * avg_val_den, 1000 * avg_val_den, f"dev_{rule_type}_{len(penalties)}")
                model.Add(cp_model.LinearExpr.Sum(emp_vars) * avg_val_den - avg_val_num == deviation)
                
                abs_deviation = model.NewIntVar(0, 1000 * avg_val_den, f"abs_dev_{rule_type}_{len(penalties)}")
                model.AddAbsEquality(abs_deviation, deviation)
                penalties.append(rule_weight * abs_deviation)

        if rule_type == "fair_total_hours":
            total_hours_per_employee = []
            for ei in range(num_employees):
                hour_terms = []
                for k, (d, s, p) in enumerate(DSP):
                    var = x.get((ei, k))
                    if var is not None:
                        hour_terms.append(var * get_shift_hours(s))
                total_hours_per_employee.append(cp_model.LinearExpr.Sum(hour_terms))

            total_hours_sum = cp_model.LinearExpr.Sum(total_hours_per_employee)
            avg_val_num = total_hours_sum
            avg_val_den = num_employees

            for emp_total_hours in total_hours_per_employee:
                deviation = model.NewIntVar(-1000 * avg_val_den, 1000 * avg_val_den, f"dev_{rule_type}_{len(penalties)}")
                model.Add(emp_total_hours * avg_val_den - avg_val_num == deviation)
                
                abs_deviation = model.NewIntVar(0, 1000 * avg_val_den, f"abs_dev_{rule_type}_{len(penalties)}")
                model.AddAbsEquality(abs_deviation, deviation)
                penalties.append(weight * abs_deviation)

        elif rule_type == "fair_weekend_offs":
            add_fairness_penalty(weekend_shifts_per_employee, weight)
        elif rule_type == "fair_special_clinics":
            add_fairness_penalty(special_clinic_shifts[param1], weight)
        elif rule_type == "fair_shift_types":
            for s_type in ("A", "B", "C"):
                add_fairness_penalty(shift_type_counts[s_type], weight)

        # --- Welfare & Cost Rules ---
        elif rule_type == "satisfy_preferred_leave":
            for d_idx, d in enumerate(dates):
                for ei, e in enumerate(E):
                    eid = str(e.get("id" ) or e.get("employeeId") or "").strip()
                    if (d, eid) in preferred_leave:
                        penalties.append(weight * is_working[ei, d])
        
        elif rule_type == "promote_consecutive_offs":
            for ei in range(num_employees):
                for i in range(len(dates) - 2):
                    # work -> rest -> rest
                    promo = model.NewBoolVar(f"promo_off_e{ei}_d{i}")
                    model.AddBoolAnd([is_working[ei, dates[i]], is_working[ei, dates[i+1]].Not(), is_working[ei, dates[i+2]].Not()]).OnlyEnforceIf(promo)
                    # A promotion is a reward, so we subtract the weight (negative penalty)
                    penalties.append(-weight * promo)

        elif rule_type == "avoid_high_fatigue":
            fatigue_threshold = int(param1)
            consecutive_limit = int(float(param2))
            for ei in range(num_employees):
                for i in range(len(dates) - consecutive_limit):
                    high_fatigue_days = []
                    for j in range(consecutive_limit + 1):
                        d = dates[i+j]
                        is_high_fatigue_day = model.NewBoolVar(f"hfd_e{ei}_d{i}_j{j}")
                        high_fatigue_shifts_on_day = [x[(ei, k)] for k, (dd,s,p) in enumerate(DSP) if dd == d and fatigue_indices[k] >= fatigue_threshold and x.get((ei,k))]
                        if high_fatigue_shifts_on_day:
                            model.Add(cp_model.LinearExpr.Sum(high_fatigue_shifts_on_day) >= 1).OnlyEnforceIf(is_high_fatigue_day)
                            model.Add(cp_model.LinearExpr.Sum(high_fatigue_shifts_on_day) == 0).OnlyEnforceIf(is_high_fatigue_day.Not())
                            high_fatigue_days.append(is_high_fatigue_day)
                        else:
                            high_fatigue_days.append(model.NewConstant(0))
                    
                    violation = model.NewBoolVar(f"fatigue_vio_e{ei}_d{i}")
                    model.AddBoolAnd(high_fatigue_days).OnlyEnforceIf(violation)
                    penalties.append(weight * violation)

        elif rule_type == "senior_coverage":
            senior_skill = param1
            try:
                required_seniors = int(float(param2)) # Use float first to handle "1.0"
            except (ValueError, TypeError):
                logger.warning(f"Warning: '資深人員覆蓋' rule parameter2 (required count) '{param2}' is not a valid number, skipping this rule.")
                continue
            
            if required_seniors <= 0:
                continue

            for d in dates:
                for s_type in ("A", "B", "C"):
                    seniors_on_shift = []
                    for ei, e in enumerate(E):
                        if senior_skill in e.get("skills", []):
                            shifts_for_senior = [x[(ei, k)] for k, (dd, ss, pp) in enumerate(DSP) if dd == d and pick_shift(ss) == s_type and x.get((ei, k))]
                            if shifts_for_senior:
                                is_senior_working = model.NewBoolVar(f"senior_e{ei}_d{d}_s{s_type}")
                                model.Add(cp_model.LinearExpr.Sum(shifts_for_senior) >= 1).OnlyEnforceIf(is_senior_working)
                                model.Add(cp_model.LinearExpr.Sum(shifts_for_senior) == 0).OnlyEnforceIf(is_senior_working.Not())
                                seniors_on_shift.append(is_senior_working)
                    
                    if seniors_on_shift:
                        under_coverage = model.NewIntVar(0, required_seniors, f"senior_under_d{d}_s{s_type}")
                        model.Add(required_seniors - cp_model.LinearExpr.Sum(seniors_on_shift) <= under_coverage)
                        penalties.append(weight * under_coverage)

        elif rule_type == "penalize_overtime":
            for ei, e in enumerate(E):
                target_h = e.get("targetHours", 0)
                if target_h > 0:
                    hour_terms = []
                    for k, (d, s, p) in enumerate(DSP):
                        var = x.get((ei, k))
                        if var is not None:
                            hour_terms.append(var * get_shift_hours(s))
                    
                    if not hour_terms: continue

                    total_hours = cp_model.LinearExpr.Sum(hour_terms)
                    over_hours = model.NewIntVar(0, 1000 * 100, f"overtime_e{ei}")
                    model.Add(total_hours - (target_h * 100) <= over_hours)
                    penalties.append(weight * over_hours)
        
        elif rule_type == "nursing_head_support_ratio":
            target_eid = param1
            try:
                # CRITICAL FIX: Correctly parse the ratio. int(float("0.5")) was becoming 0.
                target_ratio_float = float(param2)
                target_ratio_pct = int(target_ratio_float * 100) # Convert 0.5 to 50
            except (ValueError, TypeError):
                continue # Skip rule if param2 is not a valid number

            # --- CRITICAL FIX START ---
            # Pre-calculate the FIXED total number of shifts for each head nurse from the input data.
            # This is the correct denominator for the ratio calculation.
            hn_total_shifts_map = defaultdict(int)
            for pa in provided.get("preAssignments", []):
                if pa["employeeId"] in head_nurse_ids:
                    hn_total_shifts_map[pa["employeeId"]] += 1
            for pa in provided.get("headNurseAdminAssignments", []):
                if pa["employeeId"] in head_nurse_ids:
                    hn_total_shifts_map[pa["employeeId"]] += 1
            # --- CRITICAL FIX END ---

            for ei, e in enumerate(E):
                eid = str(e.get("id") or e.get("employeeId") or "").strip()
                if target_eid != "ALL" and eid != target_eid:
                    continue
                
                # This is the correct, fixed denominator.
                fixed_total_shifts = hn_total_shifts_map.get(eid, 0)
                if fixed_total_shifts == 0:
                    continue

                # This remains a variable representing shifts assigned by the solver.
                support_shifts_vars = [
                    v for k, v in x.items() 
                    if k[0] == ei and v is not None and DSP[k[1]][2] != "行政"
                ]
                support_shifts = cp_model.LinearExpr.Sum(support_shifts_vars)

                # Penalize deviation from target ratio using the FIXED total shifts.
                # The formula is now: deviation = support_shifts * 100 - target_ratio * FIXED_TOTAL
                deviation = model.NewIntVar(-100 * fixed_total_shifts, 100 * fixed_total_shifts, f"ratio_dev_e{ei}")
                model.Add(support_shifts * 100 - target_ratio_pct * fixed_total_shifts == deviation)

                abs_deviation = model.NewIntVar(0, 100 * fixed_total_shifts, f"abs_ratio_dev_e{ei}")
                model.AddAbsEquality(abs_deviation, deviation)
                penalties.append(weight * abs_deviation)

        # --- Existing advanced rules ---
        target_eid = param1
        for ei, e in enumerate(E):
            eid = str(e.get("id") or e.get("employeeId") or "").strip()
            if target_eid != "ALL" and eid != target_eid:
                continue

            if rule_type == "consecutive_days_max":
                try:
                    limit = int(float(param2))
                except (ValueError, TypeError):
                    continue
                for i in range(len(dates) - limit):
                    violation = model.NewBoolVar(f"consecutive_max_e{ei}_d{i}")
                    model.AddBoolAnd([is_working[ei, d] for d in dates[i:i+limit+1]]).OnlyEnforceIf(violation)
                    penalties.append(weight * violation)

            elif rule_type == "consecutive_days_min":
                try:
                    limit = int(float(param2))
                except (ValueError, TypeError):
                    continue
                for i in range(len(dates) - limit + 1):
                    for k in range(1, limit):
                        if i + k >= len(dates): continue
                        start_work = is_working[ei, dates[i]]
                        end_rest = is_working[ei, dates[i+k]].Not()
                        work_in_between = [is_working[ei, dates[i+j]] for j in range(1, k)]
                        
                        violation = model.NewBoolVar(f"consecutive_min_e{ei}_d{i}_k{k}")
                        model.AddBoolAnd([start_work, end_rest] + work_in_between).OnlyEnforceIf(violation)
                        penalties.append(weight * violation)

            elif rule_type == "weekly_hours_max":
                try:
                    limit = int(float(param2)) * 100
                except (ValueError, TypeError):
                    continue
                for week_dates in weeks.values():
                    hour_terms_in_week = []
                    for k, (d, s, p) in enumerate(DSP):
                        if d in week_dates:
                            var = x.get((ei, k))
                            if var is not None:
                                hour_terms_in_week.append(var * get_shift_hours(s))

                    if not hour_terms_in_week: continue
                    
                    total_hours = cp_model.LinearExpr.Sum(hour_terms_in_week)
                    over_hours = model.NewIntVar(0, 1000 * 100, f"over_hours_e{ei}_w{list(weeks.keys())[0]}")
                    model.Add(total_hours - limit <= over_hours)
                    penalties.append(weight * over_hours)

            elif rule_type == "weekly_hours_min":
                try:
                    limit = int(float(param2)) * 100
                except (ValueError, TypeError):
                    continue
                for week_dates in weeks.values():
                    hour_terms_in_week = []
                    for k, (d, s, p) in enumerate(DSP):
                        if d in week_dates:
                            var = x.get((ei, k))
                            if var is not None:
                                hour_terms_in_week.append(var * get_shift_hours(s))

                    if not hour_terms_in_week: continue

                    total_hours = cp_model.LinearExpr.Sum(hour_terms_in_week)
                    under_hours = model.NewIntVar(0, 1000 * 100, f"under_hours_e{ei}_w{list(weeks.keys())[0]}")
                    model.Add(limit - total_hours <= under_hours)
                    penalties.append(weight * under_hours)

    # objective: minimize penalties for unmet demand, over-staffing, and undesirable patterns
    objective_terms = []
    for u in under:
        objective_terms.append(p_unmet_demand * u)
    for o in over:
        objective_terms.append(p_over_staffing * o)
    objective_terms.extend(penalties)
    model.Minimize(cp_model.LinearExpr.Sum(objective_terms))

    # solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    # extract assignments
    finalAssignments = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (ei, k), var in x.items():
            if var is None: continue
            if solver.Value(var) == 1:
                e = E[ei]
                eid = str(e.get("id" ) or e.get("employeeId") or "").strip()
                name = e.get("name") or e.get("姓名") or eid
                d, s, p = DSP[k]
                finalAssignments.append(
                    {"date": d, "shift": pick_shift(s), "shiftAlias": s, "post": p, "employeeId": eid, "employeeName": name}
                )

    # Build rows for output using the helper function
    from .schedule_helpers import build_rows
    rowsForSheet, complete_assignments = build_rows(finalAssignments, provided)
    totalDemand = sum(demand)
    filled = len(finalAssignments)
    gap_val = (sum(int(solver.Value(u)) for u in under) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else totalDemand)
    byKey = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for k, (d, s, p) in enumerate(DSP):
            assigned = sum(solver.Value(x[ei, k]) for ei in range(len(E)) if x.get((ei, k)) is not None)
            byKey.append(
                {"key": f"{d}|{s}|{p}", "demand": demand[k], "preassigned": 0, "autoAssigned": int(assigned), "totalAssigned": int(assigned), "gap": int(solver.Value(under[k])), "over": int(solver.Value(over[k]))}
            )

    brand_name = "艾立斯科技智慧排班系統"
    if status == cp_model.OPTIMAL: summaryText = f"{brand_name}: 已找到最佳排班解"
    elif status == cp_model.FEASIBLE: summaryText = f"{brand_name}: 已找到可行排班解 (因時間限制而停止)"
    else: summaryText = f"{brand_name}: 找不到可行的排班解 (請檢查硬性限制衝突)"

    logger.info(f"CP-SAT solving completed. Status: {status}, Assignments: {len(finalAssignments)}")

    return {
        "finalAssignments": finalAssignments, "rowsForSheet": rowsForSheet,
        "audit": {"byKey": byKey, "summary": {"totalDemand": totalDemand, "filled": filled, "gap": gap_val, "summaryText": summaryText}},
        "summary": summaryText,
    }

def build_rows_simple(assignments, provided):
    """Simple function to build rows for output"""
    dates = list(OrderedDict((norm_date(d), None) for d in (provided.get("schedulePeriod", {}).get("dates") or [])).keys())
    emps = provided.get("employees") or []
    name_by_id = {str(e.get("id")): e.get("name", e.get("id")) for e in emps}

    by_emp = defaultdict(lambda: defaultdict(str))
    for a in assignments:
        eid = a["employeeId"]
        name = a.get("employeeName") or name_by_id.get(eid, eid)
        key = f"{name}/{eid}"
        cell = f'{a["shift"]} {a["post"]}'.strip()
        d = a["date"]
        by_emp[key][d] = (by_emp[key][d] + ("、" if by_emp[key][d] else "") + cell)

    if not dates:
        dates = sorted({a["date"] for a in assignments})

    rows = []
    def id_from_key(k):
        return k.split("/", 1)[1] if "/" in k else k

    sorted_keys = sorted(by_emp.keys(), key=lambda k: id_from_key(k))
    all_emp_keys = {f"{(e.get('name') or e.get('id'))}/{(e.get('id'))}" for e in emps}
    all_keys = sorted(list(set(sorted_keys) | all_emp_keys), key=lambda k: id_from_key(k))

    for key in all_keys:
        row = {"員工(姓名/ID)": key}
        for d in dates:
            row[d] = by_emp[key].get(d, "")
        rows.append(row)
        
    return rows
