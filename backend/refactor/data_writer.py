#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Writer Module for CP-SAT Scheduling System
Handles writing results to various output formats (Excel, Google Sheets)
"""

import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import logging
from typing import Dict, List, Optional, Union, Any
import os

# Configure logging
logger = logging.getLogger(__name__)

class DataWriter:
    """
    Abstract base class for data writers
    """
    
    def write_schedule_results(self, df: pd.DataFrame) -> bool:
        """Write schedule results"""
        raise NotImplementedError

class GoogleSheetsDataWriter(DataWriter):
    """
    Data writer for Google Sheets
    """
    
    def __init__(self, spreadsheet_url: str, credentials_path: str = None):
        self.spreadsheet_url = spreadsheet_url
        self.credentials_path = credentials_path or "service-account-creds.json"
        self._spreadsheet = None
        self._authenticate_and_connect()
    
    def _authenticate_and_connect(self):
        """Authenticate with Google Sheets and connect to spreadsheet"""
        # CRITICAL: Import os locally to avoid UnboundLocalError when executed via exec()
        import os as _os_writer
        try:
            if not _os_writer.path.exists(self.credentials_path):
                raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
            
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=scope
            )
            
            gc = gspread.authorize(creds)
            self._spreadsheet = gc.open_by_url(self.spreadsheet_url)
            logger.info(f"Successfully connected to Google Sheet for writing: {self.spreadsheet_url}")
            
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets for writing: {e}")
            raise

    def _get_or_create_worksheet(self, sheet_name: str) -> gspread.Worksheet:
        """Get existing worksheet or create new one"""
        try:
            # Try to get existing worksheet
            worksheet = self._spreadsheet.worksheet(sheet_name)
            logger.info(f"Found existing worksheet: {sheet_name}")
            return worksheet
        except gspread.WorksheetNotFound:
            # Create new worksheet
            worksheet = self._spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            logger.info(f"Created new worksheet: {sheet_name}")
            return worksheet
    
    def _clear_worksheet(self, worksheet: gspread.Worksheet):
        """Clear all content from worksheet"""
        try:
            worksheet.clear()
            logger.debug(f"Cleared worksheet: {worksheet.title}")
        except Exception as e:
            logger.warning(f"Error clearing worksheet {worksheet.title}: {e}")
    
    def write_schedule_results(self, df: pd.DataFrame) -> bool:
        """Write schedule results to Google Sheets"""
        try:
            worksheet = self._get_or_create_worksheet("排班結果表")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, df, include_index=False)
            logger.info("Schedule results written to Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Error writing schedule results to Google Sheets: {e}")
            return False
    
    def write_complete_output(self, result, provided) -> bool:
        """Write complete output with all sheets to Google Sheets"""
        try:
            from .schedule_helpers import build_rows, build_daily_analysis_report, check_hard_constraints, check_soft_constraints, generate_soft_constraint_report, create_schedule_chart, generate_gap_analysis_report
            
            # Build the final schedule grid and get complete assignments
            rows_for_sheet, complete_assignments = build_rows(result["finalAssignments"], provided)
            rows_df = pd.DataFrame(rows_for_sheet)
            
            # Generate daily analysis report
            detailed_report_lines = build_daily_analysis_report(provided, complete_assignments)
            detailed_report_df = pd.DataFrame(detailed_report_lines, columns=['每日分析'])
            
            # Perform compliance checks
            hard_violations = check_hard_constraints(complete_assignments, provided)
            soft_violations = check_soft_constraints(result, provided, result["audit"]["byKey"])
            
            hard_violations_df = pd.DataFrame(hard_violations)
            soft_violations_df = pd.DataFrame(soft_violations)
            
            # Generate gap analysis if gaps exist
            gaps = [item for item in result["audit"]["byKey"] if item.get("gap", 0) > 0]
            gap_analysis_df = pd.DataFrame()
            if gaps:
                gap_report_lines = generate_gap_analysis_report(provided, gaps)
                gap_analysis_df = pd.DataFrame(gap_report_lines, columns=['人力缺口分析與建議'])
            
            # Generate analysis report
            report_text = generate_soft_constraint_report(
                soft_violations, 
                result["audit"]["summary"]["totalDemand"], 
                len(complete_assignments), 
                result, 
                provided, 
                result["audit"]["byKey"]
            )
            
            # Generate chart
            chart_path = create_schedule_chart(complete_assignments, provided)
            
            # Write all sheets to Google Sheets
            # 1. Schedule results
            worksheet = self._get_or_create_worksheet("排班結果表")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, rows_df, include_index=False)
            
            # 2. Gap analysis (if exists)
            if not gap_analysis_df.empty:
                worksheet = self._get_or_create_worksheet("人力缺口分析與建議")
                self._clear_worksheet(worksheet)
                set_with_dataframe(worksheet, gap_analysis_df, include_index=False)
            
            # 3. Daily analysis
            worksheet = self._get_or_create_worksheet("合併報表")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, detailed_report_df, include_index=False)
            
            # 4. Audit details
            bykey_df = pd.DataFrame(result["audit"]["byKey"])
            if not bykey_df.empty:
                worksheet = self._get_or_create_worksheet("排班審核明細")
                self._clear_worksheet(worksheet)
                set_with_dataframe(worksheet, bykey_df, include_index=False)
            
            # 5. Hard constraints
            worksheet = self._get_or_create_worksheet("硬性限制符合性查核")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, hard_violations_df, include_index=False)
            
            # 6. Soft constraints
            worksheet = self._get_or_create_worksheet("軟性限制符合性查核")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, soft_violations_df, include_index=False)
            
            # 7. Analysis report
            report_df = pd.DataFrame([line.split(': ', 1) if ': ' in line else [line, ''] for line in report_text.split('\n')], columns=['項目', '內容'])
            worksheet = self._get_or_create_worksheet("分析報告與圖表")
            self._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, report_df, include_index=False)
            
            logger.info("Complete output written to Google Sheets with all sheets")
            return True
            
        except Exception as e:
            logger.error(f"Error writing complete output to Google Sheets: {e}")
            return False

class ExcelDataWriter(DataWriter):
    """
    Data writer for Excel files
    """
    
    def __init__(self, output_path: str):
        self.output_path = output_path
    
    def write_schedule_results(self, df: pd.DataFrame) -> bool:
        """Write schedule results to Excel"""
        try:
            df.to_excel(self.output_path, index=False, sheet_name="排班結果表")
            logger.info("Schedule results written to Excel")
            return True
        except Exception as e:
            logger.error(f"Error writing schedule results to Excel: {e}")
            return False
    
    def write_complete_output(self, result, provided) -> bool:
        """Write complete output with all 5 sheets like the original run.py"""
        try:
            from .schedule_helpers import write_output_excel
            write_output_excel(self.output_path, result, provided)
            logger.info("Complete output written to Excel with all sheets")
            return True
        except Exception as e:
            logger.error(f"Error writing complete output to Excel: {e}")
            return False

def create_data_writer(output_type: str, **kwargs) -> DataWriter:
    """
    Factory function to create appropriate data writer
    
    Args:
        output_type: 'excel' or 'google_sheets'
        **kwargs: Additional arguments for the specific writer
    
    Returns:
        DataWriter instance
    """
    if output_type.lower() == 'excel':
        if 'output_path' not in kwargs:
            raise ValueError("output_path is required for Excel data writer")
        return ExcelDataWriter(kwargs['output_path'])
    
    elif output_type.lower() in ['google_sheets', 'google', 'sheets']:
        if 'spreadsheet_url' not in kwargs:
            raise ValueError("spreadsheet_url is required for Google Sheets data writer")
        return GoogleSheetsDataWriter(
            kwargs['spreadsheet_url'],
            kwargs.get('credentials_path')
        )
    
    else:
        raise ValueError(f"Unsupported output type: {output_type}")


def write_all_results_to_excel(output_path: str, results_data: Dict[str, Any]) -> bool:
    """
    Write all results to Excel file with multiple sheets
    
    Args:
        output_path: Path to output Excel file
        results_data: Dictionary containing all result dataframes and information
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Write schedule results
            if "schedule_results" in results_data:
                results_data["schedule_results"].to_excel(writer, sheet_name="排班結果表", index=False)
            
            # Write gap analysis if exists
            if "gap_analysis" in results_data and not results_data["gap_analysis"].empty:
                results_data["gap_analysis"].to_excel(writer, sheet_name="人力缺口分析與建議", index=False)
            
            # Write daily analysis
            if "daily_analysis" in results_data:
                results_data["daily_analysis"].to_excel(writer, sheet_name="合併報表", index=False)
            
            # Write audit details
            if "audit_details" in results_data and not results_data["audit_details"].empty:
                results_data["audit_details"].to_excel(writer, sheet_name="排班審核明細", index=False)
            
            # Write hard constraints
            if "hard_constraints" in results_data:
                results_data["hard_constraints"].to_excel(writer, sheet_name="硬性限制符合性查核", index=False)
            
            # Write soft constraints
            if "soft_constraints" in results_data:
                results_data["soft_constraints"].to_excel(writer, sheet_name="軟性限制符合性查核", index=False)
            
            # Write analysis report
            if "analysis_report" in results_data:
                report_text = results_data["analysis_report"]
                report_df = pd.DataFrame([line.split(': ', 1) if ': ' in line else [line, ''] for line in report_text.split('\n')], columns=['項目', '內容'])
                report_df.to_excel(writer, sheet_name="分析報告與圖表", index=False, header=False)
                
                # Add chart if available
                # CRITICAL: Import os locally to avoid UnboundLocalError when executed via exec()
                import os as _os_writer_chart
                if "chart_path" in results_data and results_data["chart_path"] and _os_writer_chart.path.exists(results_data["chart_path"]):
                    try:
                        from openpyxl.drawing.image import Image
                        wb = writer.book
                        ws = wb["分析報告與圖表"]
                        img = Image(results_data["chart_path"])
                        ws.add_image(img, f'A{len(report_df) + 3}')
                    except ImportError:
                        logger.warning("openpyxl.drawing.image not available, skipping chart insertion")
                    except Exception as e:
                        logger.warning(f"Error inserting chart: {e}")
        
        logger.info(f"All results written to Excel: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing all results to Excel: {e}")
        return False


def write_all_results_to_google_sheets(spreadsheet_url: str, results_data: Dict[str, Any], credentials_path: str = None) -> bool:
    """
    Write all results to Google Sheets with multiple worksheets
    
    Args:
        spreadsheet_url: URL of the Google Sheet
        results_data: Dictionary containing all result dataframes and information
        credentials_path: Path to Google service account credentials file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create Google Sheets data writer
        writer = GoogleSheetsDataWriter(spreadsheet_url, credentials_path)
        
        # Write schedule results
        if "schedule_results" in results_data:
            worksheet = writer._get_or_create_worksheet("排班結果表")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["schedule_results"], include_index=False)
        
        # Write gap analysis if exists
        if "gap_analysis" in results_data and not results_data["gap_analysis"].empty:
            worksheet = writer._get_or_create_worksheet("人力缺口分析與建議")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["gap_analysis"], include_index=False)
        
        # Write daily analysis
        if "daily_analysis" in results_data:
            worksheet = writer._get_or_create_worksheet("合併報表")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["daily_analysis"], include_index=False)
        
        # Write audit details
        if "audit_details" in results_data and not results_data["audit_details"].empty:
            worksheet = writer._get_or_create_worksheet("排班審核明細")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["audit_details"], include_index=False)
        
        # Write hard constraints
        if "hard_constraints" in results_data:
            worksheet = writer._get_or_create_worksheet("硬性限制符合性查核")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["hard_constraints"], include_index=False)
        
        # Write soft constraints
        if "soft_constraints" in results_data:
            worksheet = writer._get_or_create_worksheet("軟性限制符合性查核")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, results_data["soft_constraints"], include_index=False)
        
        # Write analysis report
        if "analysis_report" in results_data:
            report_text = results_data["analysis_report"]
            report_df = pd.DataFrame([line.split(': ', 1) if ': ' in line else [line, ''] for line in report_text.split('\n')], columns=['項目', '內容'])
            worksheet = writer._get_or_create_worksheet("分析報告與圖表")
            writer._clear_worksheet(worksheet)
            set_with_dataframe(worksheet, report_df, include_index=False)
        
        logger.info(f"All results written to Google Sheets: {spreadsheet_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing all results to Google Sheets: {e}")
        return False