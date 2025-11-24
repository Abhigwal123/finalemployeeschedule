#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Provider Module for CP-SAT Scheduling System
Provides abstraction layer for reading data from various sources (Excel, Google Sheets)
"""

import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
import logging
from typing import Dict, List, Optional, Union
import os
import sys

# Configure logging
logger = logging.getLogger(__name__)

class DataProvider:
    """
    Abstract base class for data providers
    """
    
    def get_employee_data(self) -> pd.DataFrame:
        """Get employee data as DataFrame"""
        raise NotImplementedError
    
    def get_demand_data(self) -> pd.DataFrame:
        """Get demand data as DataFrame"""
        raise NotImplementedError
    
    def get_pre_assignments_data(self) -> pd.DataFrame:
        """Get pre-assignments data as DataFrame"""
        raise NotImplementedError
    
    def get_rules_data(self) -> pd.DataFrame:
        """Get rules data as DataFrame"""
        raise NotImplementedError
    
    def get_shift_definitions_data(self) -> pd.DataFrame:
        """Get shift definitions data as DataFrame"""
        raise NotImplementedError


class ExcelDataProvider(DataProvider):
    """
    Data provider for Excel files
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._xls = None
        self._load_excel_file()
    
    def _load_excel_file(self):
        """Load Excel file and cache it"""
        try:
            self._xls = pd.ExcelFile(self.file_path)
            logger.info(f"Successfully loaded Excel file: {self.file_path}")
        except FileNotFoundError:
            logger.error(f"Excel file not found: {self.file_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            raise
    
    def _find_sheet_name(self, keyword: str) -> Optional[str]:
        """Find sheet name by keyword"""
        for name in self._xls.sheet_names:
            if keyword in name:
                return name
        return None
    
    def get_employee_data(self) -> pd.DataFrame:
        """Get employee data from Excel"""
        # Try English sheet name first, then Chinese
        sheet_name = self._find_sheet_name("Employees") or self._find_sheet_name("人員資料庫")
        if not sheet_name:
            raise ValueError("Employee data sheet not found. Look for sheet containing 'Employees' or '人員資料庫'")
        
        df = pd.read_excel(self._xls, sheet_name)
        logger.info(f"Loaded employee data from sheet: {sheet_name}")
        return df
    
    def get_demand_data(self) -> pd.DataFrame:
        """Get demand data from Excel"""
        # Try English sheet name first, then Chinese
        sheet_name = self._find_sheet_name("Demand") or self._find_sheet_name("每月人力需求表")
        if not sheet_name:
            raise ValueError("Demand data sheet not found. Look for sheet containing 'Demand' or '每月人力需求表'")
        
        df = pd.read_excel(self._xls, sheet_name)
        logger.info(f"Loaded demand data from sheet: {sheet_name}")
        return df
    
    def get_pre_assignments_data(self) -> pd.DataFrame:
        """Get pre-assignments data from Excel"""
        # Try English sheet name first, then Chinese
        sheet_name = self._find_sheet_name("Pre_Assignments") or self._find_sheet_name("員工預排班表")
        if sheet_name:
            df = pd.read_excel(self._xls, sheet_name)
            df.columns = df.columns.str.strip()
            logger.info(f"Loaded pre-assignments data from sheet: {sheet_name}")
        else:
            df = pd.DataFrame(columns=["日期", "員工ID", "班別"])
            logger.info("No pre-assignments sheet found, using empty DataFrame")
        return df
    
    def get_rules_data(self) -> pd.DataFrame:
        """Get rules data from Excel"""
        # Try English sheet name first, then Chinese
        sheet_name = self._find_sheet_name("Rules") or self._find_sheet_name("軟性限制")
        if sheet_name:
            try:
                df = pd.read_excel(self._xls, sheet_name)
                logger.info(f"Loaded rules data from sheet: {sheet_name}")
                return df
            except Exception as e:
                logger.warning(f"Error loading rules sheet: {e}")
                return pd.DataFrame()
        else:
            logger.info("No rules sheet found, using empty DataFrame")
            return pd.DataFrame()
    
    def get_shift_definitions_data(self) -> pd.DataFrame:
        """Get shift definitions data from Excel"""
        # Try English sheet name first, then Chinese
        sheet_name = self._find_sheet_name("Shift_Definitions") or self._find_sheet_name("班別定義表")
        if sheet_name:
            try:
                df = pd.read_excel(self._xls, sheet_name)
                logger.info(f"Loaded shift definitions data from sheet: {sheet_name}")
                return df
            except Exception as e:
                logger.warning(f"Error loading shift definitions sheet: {e}")
                return pd.DataFrame()
        else:
            logger.info("No shift definitions sheet found, using empty DataFrame")
            return pd.DataFrame()


class GoogleSheetsDataProvider(DataProvider):
    """
    Data provider for Google Sheets
    """
    
    def __init__(self, spreadsheet_url: str, credentials_path: str = None):
        self.spreadsheet_url = spreadsheet_url
        self.credentials_path = credentials_path or "service-account-creds.json"
        self._spreadsheet = None
        self._authenticate_and_connect()
    
    def _authenticate_and_connect(self):
        """Authenticate with Google Sheets and connect to spreadsheet"""
        # CRITICAL: Import os locally to avoid UnboundLocalError when executed via exec()
        import os as _os_provider
        try:
            if not _os_provider.path.exists(self.credentials_path):
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
            logger.info(f"Successfully connected to Google Sheet: {self.spreadsheet_url}")
            
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets: {e}")
            raise
    
    def _find_worksheet(self, keyword: str) -> Optional[gspread.Worksheet]:
        """Find worksheet by keyword"""
        try:
            worksheets = self._spreadsheet.worksheets()
            for ws in worksheets:
                if keyword in ws.title:
                    return ws
            return None
        except Exception as e:
            logger.error(f"Error finding worksheet with keyword '{keyword}': {e}")
            return None
    
    def get_employee_data(self) -> pd.DataFrame:
        """Get employee data from Google Sheets - always fetches fresh data"""
        try:
            # Ensure connection is still valid, reconnect if needed
            if self._spreadsheet is None:
                logger.warning("Spreadsheet connection lost, reconnecting...")
                self._authenticate_and_connect()
            
            ws = self._find_worksheet("人員資料庫")
            if not ws:
                raise ValueError("Employee data worksheet not found. Look for worksheet containing '人員資料庫'")
            
            # Always fetch fresh data from Google Sheets
            df = get_as_dataframe(ws, evaluate_formulas=True)
            df = df.dropna(how='all')
            logger.info(f"Loaded fresh employee data from worksheet: {ws.title} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.error(f"Error loading employee data: {e}")
            # Try to reconnect and retry once
            try:
                logger.info("Attempting to reconnect to Google Sheets...")
                self._authenticate_and_connect()
                ws = self._find_worksheet("人員資料庫")
                if ws:
                    df = get_as_dataframe(ws, evaluate_formulas=True)
                    df = df.dropna(how='all')
                    logger.info(f"Successfully loaded employee data after reconnection: {ws.title}")
                    return df
            except Exception as retry_error:
                logger.error(f"Reconnection failed: {retry_error}")
            raise
    
    def get_demand_data(self) -> pd.DataFrame:
        """Get demand data from Google Sheets - always fetches fresh data"""
        try:
            # Ensure connection is still valid
            if self._spreadsheet is None:
                logger.warning("Spreadsheet connection lost, reconnecting...")
                self._authenticate_and_connect()
            
            ws = self._find_worksheet("每月人力需求表")
            if not ws:
                raise ValueError("Demand data worksheet not found. Look for worksheet containing '每月人力需求表'")
            
            # Always fetch fresh data from Google Sheets
            df = get_as_dataframe(ws, evaluate_formulas=True)
            df = df.dropna(how='all')
            logger.info(f"Loaded fresh demand data from worksheet: {ws.title} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.error(f"Error loading demand data: {e}")
            # Try to reconnect and retry once
            try:
                logger.info("Attempting to reconnect to Google Sheets...")
                self._authenticate_and_connect()
                ws = self._find_worksheet("每月人力需求表")
                if ws:
                    df = get_as_dataframe(ws, evaluate_formulas=True)
                    df = df.dropna(how='all')
                    logger.info(f"Successfully loaded demand data after reconnection: {ws.title}")
                    return df
            except Exception as retry_error:
                logger.error(f"Reconnection failed: {retry_error}")
            raise
    
    def get_pre_assignments_data(self) -> pd.DataFrame:
        """Get pre-assignments data from Google Sheets"""
        ws = self._find_worksheet("員工預排班表")
        if ws:
            try:
                df = get_as_dataframe(ws, evaluate_formulas=True)
                df = df.dropna(how='all')
                df.columns = df.columns.str.strip()
                logger.info(f"Loaded pre-assignments data from worksheet: {ws.title}")
                return df
            except Exception as e:
                logger.warning(f"Error loading pre-assignments data: {e}")
                return pd.DataFrame(columns=["日期", "員工ID", "班別"])
        else:
            logger.info("No pre-assignments worksheet found, using empty DataFrame")
            return pd.DataFrame(columns=["日期", "員工ID", "班別"])
    
    def get_rules_data(self) -> pd.DataFrame:
        """Get rules data from Google Sheets"""
        ws = self._find_worksheet("軟性限制")
        if ws:
            try:
                df = get_as_dataframe(ws, evaluate_formulas=True)
                df = df.dropna(how='all')
                logger.info(f"Loaded rules data from worksheet: {ws.title}")
                return df
            except Exception as e:
                logger.warning(f"Error loading rules data: {e}")
                return pd.DataFrame()
        else:
            logger.info("No rules worksheet found, using empty DataFrame")
            return pd.DataFrame()
    
    def get_shift_definitions_data(self) -> pd.DataFrame:
        """Get shift definitions data from Google Sheets"""
        ws = self._find_worksheet("班別定義表")
        if ws:
            try:
                df = get_as_dataframe(ws, evaluate_formulas=True)
                df = df.dropna(how='all')
                logger.info(f"Loaded shift definitions data from worksheet: {ws.title}")
                return df
            except Exception as e:
                logger.warning(f"Error loading shift definitions data: {e}")
                return pd.DataFrame()
        else:
            logger.info("No shift definitions worksheet found, using empty DataFrame")
            return pd.DataFrame()


def create_data_provider(source_type: str, **kwargs) -> DataProvider:
    """
    Factory function to create appropriate data provider
    
    Args:
        source_type: 'excel' or 'google_sheets'
        **kwargs: Additional arguments for the specific provider
    
    Returns:
        DataProvider instance
    """
    if source_type.lower() == 'excel':
        if 'file_path' not in kwargs:
            raise ValueError("file_path is required for Excel data provider")
        return ExcelDataProvider(kwargs['file_path'])
    
    elif source_type.lower() in ['google_sheets', 'google', 'sheets']:
        if 'spreadsheet_url' not in kwargs:
            raise ValueError("spreadsheet_url is required for Google Sheets data provider")
        return GoogleSheetsDataProvider(
            kwargs['spreadsheet_url'],
            kwargs.get('credentials_path')
        )
    
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


# Backward compatibility functions
def get_employee_data(source_type: str, **kwargs) -> pd.DataFrame:
    """Get employee data from specified source"""
    provider = create_data_provider(source_type, **kwargs)
    return provider.get_employee_data()


def get_demand_data(source_type: str, **kwargs) -> pd.DataFrame:
    """Get demand data from specified source"""
    provider = create_data_provider(source_type, **kwargs)
    return provider.get_demand_data()


def get_pre_assignments_data(source_type: str, **kwargs) -> pd.DataFrame:
    """Get pre-assignments data from specified source"""
    provider = create_data_provider(source_type, **kwargs)
    return provider.get_pre_assignments_data()


def get_rules_data(source_type: str, **kwargs) -> pd.DataFrame:
    """Get rules data from specified source"""
    provider = create_data_provider(source_type, **kwargs)
    return provider.get_rules_data()


def get_shift_definitions_data(source_type: str, **kwargs) -> pd.DataFrame:
    """Get shift definitions data from specified source"""
    provider = create_data_provider(source_type, **kwargs)
    return provider.get_shift_definitions_data()
