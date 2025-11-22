"""
Script to trigger a sync from Google Sheets to populate schedules
"""
import sys
import os

# Add backend to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from app import create_app, db
from app.models import ScheduleDefinition
from app.services.google_sheets_sync_service import GoogleSheetsSyncService
from flask import current_app

def trigger_sync():
    """Trigger sync for all active schedule definitions"""
    
    app = create_app()
    with app.app_context():
        print("=" * 80)
        print("TRIGGERING SYNC FROM GOOGLE SHEETS")
        print("=" * 80)
        print()
        
        # Get all active schedule definitions
        schedule_defs = ScheduleDefinition.query.filter_by(is_active=True).all()
        
        if not schedule_defs:
            print("❌ No active schedule definitions found")
            return False
        
        print(f"Found {len(schedule_defs)} active schedule definition(s):")
        for sd in schedule_defs:
            print(f"   - {sd.scheduleName} (ID: {sd.scheduleDefID})")
        print()
        
        # Get credentials path
        creds_path = app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
        if not os.path.isabs(creds_path) and not os.path.exists(creds_path):
            # Try to find it in project root
            project_root = os.path.dirname(backend_dir)
            project_creds = os.path.join(project_root, 'service-account-creds.json')
            if os.path.exists(project_creds):
                creds_path = project_creds
        
        print(f"Using credentials: {creds_path}")
        print()
        
        # Create sync service
        sync_service = GoogleSheetsSyncService(creds_path)
        
        # Sync each schedule
        for schedule_def in schedule_defs:
            print(f"{'=' * 80}")
            print(f"Syncing: {schedule_def.scheduleName}")
            print(f"{'=' * 80}")
            
            try:
                result = sync_service.sync_schedule_data(
                    schedule_def_id=schedule_def.scheduleDefID,
                    sync_type='on_demand',
                    triggered_by=None,
                    force=True  # Force sync to fetch from Google Sheets
                )
                
                if result.get('success'):
                    rows_synced = result.get('rows_synced', 0)
                    users_synced = result.get('users_synced', 0)
                    print(f"✅ Sync successful!")
                    print(f"   Rows synced: {rows_synced}")
                    print(f"   Users synced: {users_synced}")
                    
                    if result.get('skipped'):
                        print(f"   ⚠️  Sync was skipped (data is fresh)")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"❌ Sync failed: {error}")
                    
            except Exception as e:
                print(f"❌ Error syncing {schedule_def.scheduleName}: {e}")
                import traceback
                print(traceback.format_exc())
        
        print(f"\n{'=' * 80}")
        print("SYNC COMPLETE")
        print(f"{'=' * 80}")
        print("\n📋 NEXT STEPS:")
        print("   1. Run: python diagnose_schedule_linking.py")
        print("   2. Verify schedules are stored with correct user_id")
        print("   3. Test in frontend - each user should see only their schedule")
        print(f"{'=' * 80}")
        
        return True

if __name__ == '__main__':
    success = trigger_sync()
    sys.exit(0 if success else 1)


