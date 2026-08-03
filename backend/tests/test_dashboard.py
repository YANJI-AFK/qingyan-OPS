import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
try:
    import db_service
    d = db_service.get_dashboard_stats()
    import json
    print(json.dumps(d, ensure_ascii=False, indent=2)[:3000])
except Exception:
    traceback.print_exc()
